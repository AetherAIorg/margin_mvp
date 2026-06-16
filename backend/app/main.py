from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import SessionLocal, get_db, init_db
from app.discovery.engine import build_discovery
from app.execution.engine import execute_metric_run
from app.llm.client import explain_formula_diff
from app.models import (
    Artifact,
    Dataset,
    FormulaImplementation,
    Function,
    Issue,
    Metric,
    MetricCluster,
    MetricRun,
    MetricSpec,
    NormalizedFormula,
    ParseJob,
)
from app.parsers.csv_parser import sniff_csv_columns
from app.parsers import artifact_type_from_filename
from app.queue import enqueue_parse
from app.schemas import (
    ApproveMetricIn,
    ArtifactOut,
    ArtifactUploadResult,
    ClusterDetailOut,
    ClusterOut,
    DatasetOut,
    DiscoverySummaryOut,
    FormulaOut,
    FunctionOut,
    IssueOut,
    MetricCandidateDetailOut,
    MetricCandidateOut,
    MetricIn,
    MetricOut,
    MetricRunIn,
    MetricRunOut,
    MetricSpecOut,
    ParseJobOut,
    SearchResponse,
    SearchResult,
)
from app.seed.run_seed import seed_canonical_metrics, seed_functions
from app.storage import download_bytes, upload_bytes


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_functions(db)
        seed_canonical_metrics(db)
    finally:
        db.close()
    yield


app = FastAPI(title="MetricGraph API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def formula_out(impl: FormulaImplementation) -> FormulaOut:
    norm = impl.normalized
    return FormulaOut(
        id=impl.id,
        artifact_id=impl.artifact_id,
        language=impl.language,
        raw_formula=impl.raw_formula,
        location=impl.location,
        extracted_name=impl.extracted_name,
        confidence_score=impl.confidence_score,
        is_deprecated=impl.is_deprecated,
        owner=impl.owner,
        artifact_filename=impl.artifact.filename if impl.artifact else None,
        dimensions=norm.dimensions if norm else None,
        normalized_signature=norm.normalized_ast.get("signature") if norm else None,
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/artifacts/upload", response_model=ArtifactUploadResult)
async def upload_artifacts(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    uploaded: list[ArtifactOut] = []
    jobs: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        content = await upload.read()
        try:
            artifact_type = artifact_type_from_filename(upload.filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        key = upload_bytes(content, "artifacts", upload.filename)
        artifact = Artifact(
            filename=upload.filename,
            artifact_type=artifact_type,
            storage_path=key,
            status="uploaded",
        )
        db.add(artifact)
        db.flush()
        job = ParseJob(artifact_id=artifact.id, status="queued")
        db.add(job)
        db.commit()
        rq_id = enqueue_parse(job.id, artifact.id)
        job.rq_job_id = rq_id
        db.commit()
        uploaded.append(
            ArtifactOut(
                id=artifact.id,
                filename=artifact.filename,
                artifact_type=artifact.artifact_type,
                owner=artifact.owner,
                storage_path=artifact.storage_path,
                status=artifact.status,
                uploaded_at=artifact.uploaded_at,
                object_count=artifact.object_count,
            )
        )
        jobs.append(job.id)
    return ArtifactUploadResult(artifacts=uploaded, parse_jobs=jobs)


@app.get("/api/artifacts", response_model=list[ArtifactOut])
def list_artifacts(db: Session = Depends(get_db)):
    artifacts = list(db.scalars(select(Artifact).order_by(Artifact.uploaded_at.desc())))
    return [
        ArtifactOut(
            id=a.id,
            filename=a.filename,
            artifact_type=a.artifact_type,
            owner=a.owner,
            storage_path=a.storage_path,
            status=a.status,
            uploaded_at=a.uploaded_at,
            object_count=a.object_count,
        )
        for a in artifacts
    ]


@app.get("/api/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_artifact(artifact_id: str, db: Session = Depends(get_db)):
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactOut(
        id=artifact.id,
        filename=artifact.filename,
        artifact_type=artifact.artifact_type,
        owner=artifact.owner,
        storage_path=artifact.storage_path,
        status=artifact.status,
        uploaded_at=artifact.uploaded_at,
        object_count=artifact.object_count,
    )


@app.get("/api/jobs/{job_id}", response_model=ParseJobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ParseJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ParseJobOut(
        id=job.id,
        artifact_id=job.artifact_id,
        status=job.status,
        rq_job_id=job.rq_job_id,
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@app.get("/api/formulas", response_model=list[FormulaOut])
def list_formulas(family: str | None = None, db: Session = Depends(get_db)):
    stmt = (
        select(FormulaImplementation)
        .options(
            selectinload(FormulaImplementation.normalized),
            selectinload(FormulaImplementation.artifact),
        )
        .order_by(FormulaImplementation.extracted_name)
    )
    if family:
        stmt = stmt.join(NormalizedFormula).where(NormalizedFormula.metric_family == family)
    return [formula_out(impl) for impl in db.scalars(stmt)]


@app.get("/api/discovery/summary", response_model=DiscoverySummaryOut)
def discovery_summary(db: Session = Depends(get_db)):
    artifacts = list(db.scalars(select(Artifact)))
    implementations = list(
        db.scalars(
            select(FormulaImplementation).options(
                selectinload(FormulaImplementation.normalized),
                selectinload(FormulaImplementation.artifact),
            )
        )
    )
    view = build_discovery(artifacts, implementations)
    return DiscoverySummaryOut(
        total_candidates=view.total_candidates,
        total_artifacts=view.total_artifacts,
        total_implementations=view.total_implementations,
        high_confidence_metrics=view.high_confidence_metrics,
        formula_clusters=view.formula_clusters,
        families=view.families,
        issue_counts=view.issue_counts,
    )


@app.get("/api/discovery/candidates", response_model=list[MetricCandidateOut])
def discovery_candidates(family: str | None = None, db: Session = Depends(get_db)):
    artifacts = list(db.scalars(select(Artifact)))
    implementations = list(
        db.scalars(
            select(FormulaImplementation).options(
                selectinload(FormulaImplementation.normalized),
                selectinload(FormulaImplementation.artifact),
            )
        )
    )
    view = build_discovery(artifacts, implementations)
    candidates = view.candidates
    if family:
        candidates = [c for c in candidates if c.family == family]
    return [
        MetricCandidateOut(
            id=c.id,
            display_name=c.display_name,
            family=c.family,
            candidate_key=c.candidate_key,
            implementation_count=c.implementation_count,
            signature_count=c.signature_count,
            has_conflict=c.has_conflict,
            has_deprecated_reference=c.has_deprecated_reference,
        )
        for c in candidates
    ]


@app.get("/api/discovery/candidates/{candidate_id}", response_model=MetricCandidateDetailOut)
def discovery_candidate_detail(candidate_id: str, db: Session = Depends(get_db)):
    artifacts = list(db.scalars(select(Artifact)))
    implementations = list(
        db.scalars(
            select(FormulaImplementation).options(
                selectinload(FormulaImplementation.normalized),
                selectinload(FormulaImplementation.artifact),
            )
        )
    )
    view = build_discovery(artifacts, implementations)
    candidate = next((c for c in view.candidates if c.id == candidate_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    signatures = sorted(
        {
            impl.normalized.normalized_ast.get("signature", "")
            for impl in candidate.implementations
            if impl.normalized
        }
    )
    return MetricCandidateDetailOut(
        id=candidate.id,
        display_name=candidate.display_name,
        family=candidate.family,
        candidate_key=candidate.candidate_key,
        implementation_count=candidate.implementation_count,
        signature_count=candidate.signature_count,
        has_conflict=candidate.has_conflict,
        has_deprecated_reference=candidate.has_deprecated_reference,
        implementations=[formula_out(impl) for impl in candidate.implementations],
        signatures=signatures,
        dimensions_summary=candidate.dimensions_summary,
    )


@app.get("/api/issues", response_model=list[IssueOut])
def list_issues(issue_type: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Issue).order_by(Issue.severity.desc())
    if issue_type:
        stmt = stmt.where(Issue.issue_type == issue_type)
    return [
        IssueOut(
            id=i.id,
            issue_type=i.issue_type,
            title=i.title,
            explanation=i.explanation,
            severity=i.severity,
            affected_artifacts=i.affected_artifacts or [],
        )
        for i in db.scalars(stmt)
    ]


@app.get("/api/clusters", response_model=list[ClusterOut])
def list_clusters(family: str | None = None, db: Session = Depends(get_db)):
    stmt = select(MetricCluster).options(selectinload(MetricCluster.members))
    if family:
        stmt = stmt.where(MetricCluster.metric_family == family)
    clusters = list(db.scalars(stmt))
    return [
        ClusterOut(
            id=c.id,
            cluster_name=c.cluster_name,
            metric_family=c.metric_family,
            member_count=len(c.members),
            has_conflict=any(m.relationship_type == "conflicting" for m in c.members),
        )
        for c in clusters
    ]


@app.get("/api/clusters/{cluster_id}", response_model=ClusterDetailOut)
def get_cluster(cluster_id: str, db: Session = Depends(get_db)):
    cluster = db.scalar(
        select(MetricCluster)
        .where(MetricCluster.id == cluster_id)
        .options(selectinload(MetricCluster.members))
    )
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    members = []
    for member in cluster.members:
        impl = db.scalar(
            select(FormulaImplementation)
            .where(FormulaImplementation.id == member.formula_implementation_id)
            .options(
                selectinload(FormulaImplementation.normalized),
                selectinload(FormulaImplementation.artifact),
            )
        )
        if impl:
            members.append(formula_out(impl))
    return ClusterDetailOut(
        id=cluster.id,
        cluster_name=cluster.cluster_name,
        metric_family=cluster.metric_family,
        member_count=len(cluster.members),
        has_conflict=any(m.relationship_type == "conflicting" for m in cluster.members),
        members=members,
    )


@app.get("/api/metrics", response_model=list[MetricOut])
def list_metrics(db: Session = Depends(get_db)):
    metrics = list(
        db.scalars(select(Metric).options(selectinload(Metric.specs)).order_by(Metric.canonical_name))
    )
    return [_metric_out(m) for m in metrics]


@app.post("/api/metrics", response_model=MetricOut)
def create_metric(payload: MetricIn, db: Session = Depends(get_db)):
    metric = Metric(
        canonical_name=payload.canonical_name,
        description=payload.description,
        domain=payload.domain,
        entity=payload.entity,
        grain=payload.grain,
        owner=payload.owner,
        status="candidate",
    )
    db.add(metric)
    db.flush()
    if payload.spec:
        db.add(
            MetricSpec(
                metric_id=metric.id,
                required_inputs=payload.spec.required_inputs,
                transformation_plan=payload.spec.transformation_plan,
                calculation_function_id=payload.spec.calculation_function_id,
                validation_rules=payload.spec.validation_rules,
            )
        )
    db.commit()
    db.refresh(metric)
    return _metric_out(metric)


@app.get("/api/metrics/{metric_id}", response_model=MetricOut)
def get_metric(metric_id: str, db: Session = Depends(get_db)):
    metric = db.scalar(select(Metric).where(Metric.id == metric_id).options(selectinload(Metric.specs)))
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    return _metric_out(metric)


def _metric_out(metric: Metric) -> MetricOut:
    return MetricOut(
        id=metric.id,
        canonical_name=metric.canonical_name,
        description=metric.description,
        domain=metric.domain,
        entity=metric.entity,
        grain=metric.grain,
        owner=metric.owner,
        status=metric.status,
        version=metric.version,
        specs=[
            MetricSpecOut(
                id=s.id,
                required_inputs=s.required_inputs,
                transformation_plan=s.transformation_plan,
                calculation_function_id=s.calculation_function_id,
                validation_rules=s.validation_rules,
                approved_by=s.approved_by,
                approved_at=s.approved_at,
            )
            for s in metric.specs
        ],
    )


@app.post("/api/metrics/{metric_id}/approve", response_model=MetricOut)
def approve_metric(metric_id: str, payload: ApproveMetricIn, db: Session = Depends(get_db)):
    metric = db.scalar(select(Metric).where(Metric.id == metric_id).options(selectinload(Metric.specs)))
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    metric.status = "approved"
    spec = metric.specs[0] if metric.specs else None
    if payload.spec_id:
        spec = next((s for s in metric.specs if s.id == payload.spec_id), spec)
    if spec:
        spec.approved_by = payload.approved_by
        spec.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(metric)
    return _metric_out(metric)


@app.get("/api/functions", response_model=list[FunctionOut])
def list_functions(db: Session = Depends(get_db)):
    functions = list(
        db.scalars(select(Function).options(selectinload(Function.implementations)).order_by(Function.name))
    )
    return [
        FunctionOut(
            id=f.id,
            name=f.name,
            function_type=f.function_type,
            description=f.description,
            input_schema=f.input_schema,
            output_schema=f.output_schema,
            owner=f.owner,
            status=f.status,
            version=f.version,
            implementations=[
                {
                    "id": impl.id,
                    "runtime": impl.runtime,
                    "code_location": impl.code_location,
                    "version": impl.version,
                    "status": impl.status,
                }
                for impl in f.implementations
            ],
        )
        for f in functions
    ]


@app.get("/api/functions/{function_id}", response_model=FunctionOut)
def get_function(function_id: str, db: Session = Depends(get_db)):
    fn = db.scalar(
        select(Function).where(Function.id == function_id).options(selectinload(Function.implementations))
    )
    if not fn:
        raise HTTPException(status_code=404, detail="Function not found")
    return FunctionOut(
        id=fn.id,
        name=fn.name,
        function_type=fn.function_type,
        description=fn.description,
        input_schema=fn.input_schema,
        output_schema=fn.output_schema,
        owner=fn.owner,
        status=fn.status,
        version=fn.version,
        implementations=[
            {
                "id": impl.id,
                "runtime": impl.runtime,
                "code_location": impl.code_location,
                "version": impl.version,
                "status": impl.status,
            }
            for impl in fn.implementations
        ],
    )


@app.get("/api/search", response_model=SearchResponse)
def search(q: str = "", db: Session = Depends(get_db)):
    results: list[SearchResult] = []
    terms = q.lower().strip()

    metrics = list(db.scalars(select(Metric)))
    for m in metrics:
        hay = f"{m.canonical_name} {m.description} {m.owner}".lower()
        if not terms or terms in hay:
            results.append(
                SearchResult(
                    id=m.id,
                    type="metric",
                    title=m.canonical_name,
                    subtitle=f"{m.domain} · {m.status} · owner {m.owner or 'none'}",
                    snippet=m.description[:200],
                    score=3.0 if terms and terms in m.canonical_name.lower() else 1.0,
                    href=f"/metrics/{m.id}",
                )
            )

    functions = list(db.scalars(select(Function)))
    for f in functions:
        hay = f"{f.name} {f.description}".lower()
        if not terms or terms in hay:
            results.append(
                SearchResult(
                    id=f.id,
                    type="function",
                    title=f.name,
                    subtitle=f.function_type,
                    snippet=f.description[:200],
                    score=2.0,
                    href=f"/functions/{f.id}",
                )
            )

    implementations = list(
        db.scalars(
            select(FormulaImplementation).options(
                selectinload(FormulaImplementation.artifact),
                selectinload(FormulaImplementation.normalized),
            )
        )
    )
    for impl in implementations:
        hay = f"{impl.extracted_name} {impl.raw_formula}".lower()
        if not terms or terms in hay:
            results.append(
                SearchResult(
                    id=impl.id,
                    type="formula",
                    title=impl.extracted_name,
                    subtitle=f"{impl.artifact.filename if impl.artifact else ''} · {impl.location}",
                    snippet=impl.raw_formula[:200],
                    score=1.5,
                    href=f"/discovery?candidate={impl.extracted_name}",
                )
            )

    if terms and settings.embedding_api_key:
        try:
            from app.llm.client import embed_text

            query_embed = embed_text(q)
            if query_embed:
                rows = db.execute(
                    text(
                        """
                        SELECT fi.id, fi.extracted_name, fi.raw_formula, a.filename,
                               1 - (nf.embedding <=> :embedding) AS score
                        FROM normalized_formulas nf
                        JOIN formula_implementations fi ON fi.id = nf.formula_implementation_id
                        JOIN artifacts a ON a.id = fi.artifact_id
                        WHERE nf.embedding IS NOT NULL
                        ORDER BY nf.embedding <=> :embedding
                        LIMIT 5
                        """
                    ),
                    {"embedding": str(query_embed)},
                )
                for row in rows:
                    results.append(
                        SearchResult(
                            id=row.id,
                            type="formula",
                            title=row.extracted_name,
                            subtitle=f"semantic match · {row.filename}",
                            snippet=row.raw_formula[:200],
                            score=float(row.score) * 5,
                            href=f"/discovery?candidate={row.extracted_name}",
                        )
                    )
        except Exception:
            pass

    results.sort(key=lambda r: r.score, reverse=True)
    return SearchResponse(query=q, total=len(results[:30]), results=results[:30])


@app.post("/api/datasets/upload", response_model=DatasetOut)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    content = await file.read()
    cols, row_count = sniff_csv_columns(content)
    key = upload_bytes(content, "datasets", file.filename)
    dataset = Dataset(filename=file.filename, storage_path=key, detected_columns=cols, row_count=row_count)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return DatasetOut(
        id=dataset.id,
        filename=dataset.filename,
        detected_columns=dataset.detected_columns,
        row_count=dataset.row_count,
        uploaded_at=dataset.uploaded_at,
    )


@app.get("/api/datasets", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    datasets = list(db.scalars(select(Dataset).order_by(Dataset.uploaded_at.desc())))
    return [
        DatasetOut(
            id=d.id,
            filename=d.filename,
            detected_columns=d.detected_columns,
            row_count=d.row_count,
            uploaded_at=d.uploaded_at,
        )
        for d in datasets
    ]


@app.post("/api/metrics/{metric_id}/run", response_model=MetricRunOut)
def run_metric(metric_id: str, payload: MetricRunIn, db: Session = Depends(get_db)):
    metric = db.scalar(
        select(Metric).where(Metric.id == metric_id).options(selectinload(Metric.specs))
    )
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    if not metric.specs:
        raise HTTPException(status_code=400, detail="Metric has no spec")
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    nav_dataset = db.get(Dataset, payload.nav_dataset_id) if payload.nav_dataset_id else None

    spec = metric.specs[0]
    for s in metric.specs:
        if s.approved_at:
            spec = s
            break

    run = MetricRun(metric_id=metric.id, dataset_id=dataset.id, status="running")
    db.add(run)
    db.commit()

    spec_with_fn = db.scalar(
        select(MetricSpec)
        .where(MetricSpec.id == spec.id)
        .options(selectinload(MetricSpec.calculation_function))
    )
    result = execute_metric_run(metric, spec_with_fn, dataset, nav_dataset, payload.column_mapping)

    run.status = result["status"]
    run.transformation_plan_used = spec.transformation_plan
    run.audit_log = result.get("audit_log")
    run.warnings = result.get("warnings")
    run.errors = result.get("errors")
    run.result_path = result.get("result_path")
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)

    return MetricRunOut(
        id=run.id,
        metric_id=run.metric_id,
        dataset_id=run.dataset_id,
        status=run.status,
        transformation_plan_used=run.transformation_plan_used,
        audit_log=run.audit_log,
        warnings=run.warnings,
        errors=run.errors,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@app.get("/api/runs/{run_id}", response_model=MetricRunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(MetricRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return MetricRunOut(
        id=run.id,
        metric_id=run.metric_id,
        dataset_id=run.dataset_id,
        status=run.status,
        transformation_plan_used=run.transformation_plan_used,
        audit_log=run.audit_log,
        warnings=run.warnings,
        errors=run.errors,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@app.get("/api/runs/{run_id}/results")
def get_run_results(run_id: str, db: Session = Depends(get_db)):
    run = db.get(MetricRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.result_path:
        return {"results": [], "audit_log": run.audit_log}
    content = download_bytes(run.result_path).decode("utf-8")
    import csv
    import io

    reader = csv.DictReader(io.StringIO(content))
    return {"results": list(reader), "audit_log": run.audit_log, "warnings": run.warnings}


@app.get("/api/formulas/diff")
def formula_diff(impl_a_id: str, impl_b_id: str, db: Session = Depends(get_db)):
    impl_a = db.scalar(
        select(FormulaImplementation)
        .where(FormulaImplementation.id == impl_a_id)
        .options(selectinload(FormulaImplementation.normalized))
    )
    impl_b = db.scalar(
        select(FormulaImplementation)
        .where(FormulaImplementation.id == impl_b_id)
        .options(selectinload(FormulaImplementation.normalized))
    )
    if not impl_a or not impl_b:
        raise HTTPException(status_code=404, detail="Implementation not found")
    a_data = {
        "location": impl_a.location,
        "formula": impl_a.raw_formula,
        "dimensions": impl_a.normalized.dimensions if impl_a.normalized else {},
    }
    b_data = {
        "location": impl_b.location,
        "formula": impl_b.raw_formula,
        "dimensions": impl_b.normalized.dimensions if impl_b.normalized else {},
    }
    explanation = explain_formula_diff(a_data, b_data)
    return {"explanation": explanation, "implementation_a": a_data, "implementation_b": b_data}
