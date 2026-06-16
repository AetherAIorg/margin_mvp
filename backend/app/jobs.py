from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.discovery.engine import build_discovery, candidate_key
from app.llm.client import embed_text, label_formula
from app.models import (
    Artifact,
    FormulaImplementation,
    Issue,
    MetricCandidate,
    MetricCluster,
    MetricClusterMember,
    NormalizedFormula,
    ParseJob,
)
from app.normalizer.engine import normalize_formula
from app.parsers import parse_artifact
from app.storage import download_bytes


def run_parse_job(job_id: str, artifact_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(ParseJob, job_id)
        artifact = db.get(Artifact, artifact_id)
        if not job or not artifact:
            return
        job.status = "running"
        db.commit()

        content = download_bytes(artifact.storage_path)
        raw_impls = parse_artifact(artifact.filename, content)

        for raw in raw_impls:
            norm = normalize_formula(raw.label, raw.raw_formula, raw.nearby_context)
            llm_label = label_formula(raw.label, raw.raw_formula, artifact.artifact_type, norm.dimensions)

            impl = FormulaImplementation(
                artifact_id=artifact.id,
                language=artifact.artifact_type,
                raw_formula=raw.raw_formula,
                location=raw.location,
                extracted_name=llm_label.get("proposed_name", raw.label),
                source_tables={"refs": raw.source_refs} if raw.source_refs else None,
                input_columns={"columns": raw.input_columns} if raw.input_columns else None,
                referenced_functions={"functions": raw.referenced_functions} if raw.referenced_functions else None,
                nearby_context=raw.nearby_context,
                confidence_score=float(llm_label.get("confidence", 0.5)),
                is_deprecated=raw.is_deprecated,
                owner=raw.owner or artifact.owner,
            )
            db.add(impl)
            db.flush()

            embed = embed_text(f"{raw.label} {raw.raw_formula} {norm.metric_family}")
            normalized = NormalizedFormula(
                formula_implementation_id=impl.id,
                normalized_ast=norm.normalized_ast,
                function_family=norm.function_family,
                metric_family=norm.metric_family,
                dimensions=norm.dimensions,
                input_signature=norm.input_signature,
                semantic_tags=norm.semantic_tags,
                embedding=embed,
            )
            db.add(normalized)

            ck = candidate_key(llm_label.get("proposed_name", raw.label))
            existing = db.scalar(
                select(MetricCandidate).where(MetricCandidate.candidate_key == ck).limit(1)
            )
            if not existing:
                db.add(
                    MetricCandidate(
                        proposed_name=llm_label.get("proposed_name", raw.label),
                        metric_family=norm.metric_family,
                        entity=llm_label.get("entity"),
                        grain=llm_label.get("grain"),
                        description=llm_label.get("description"),
                        confidence_score=float(llm_label.get("confidence", 0.5)),
                        evidence={"artifact_id": artifact.id, "location": raw.location},
                        candidate_key=ck,
                    )
                )

        artifact.status = "parsed"
        artifact.object_count = len(raw_impls)
        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

        _rebuild_clusters_and_issues(db)
    except Exception as exc:
        db.rollback()
        job = db.get(ParseJob, job_id)
        if job:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()


def _rebuild_clusters_and_issues(db) -> None:
    db.query(Issue).delete()
    db.query(MetricClusterMember).delete()
    db.query(MetricCluster).delete()
    db.commit()

    artifacts = list(db.scalars(select(Artifact)))
    implementations = list(
        db.scalars(
            select(FormulaImplementation)
            .options(
                selectinload(FormulaImplementation.normalized),
                selectinload(FormulaImplementation.artifact),
            )
        )
    )
    view = build_discovery(artifacts, implementations)

    cluster_map: dict[str, MetricCluster] = {}
    for candidate in view.candidates:
        cluster = MetricCluster(
            cluster_name=candidate.display_name,
            metric_family=candidate.family,
            confidence_score=0.8,
        )
        db.add(cluster)
        db.flush()
        cluster_map[candidate.candidate_key] = cluster
        for impl in candidate.implementations:
            rel = "conflicting" if candidate.has_conflict else "similar"
            if impl.is_deprecated:
                rel = "deprecated"
            db.add(
                MetricClusterMember(
                    cluster_id=cluster.id,
                    formula_implementation_id=impl.id,
                    relationship_type=rel,
                    confidence_score=0.7,
                )
            )

    for issue in view.issues:
        cluster_id = cluster_map.get(issue.candidate_key or "").id if issue.candidate_key in cluster_map else None
        db.add(
            Issue(
                issue_type=issue.issue_type,
                severity=issue.severity,
                cluster_id=cluster_id,
                explanation=issue.explanation,
                affected_artifacts=issue.affected_artifacts,
                title=issue.title,
            )
        )
    db.commit()
