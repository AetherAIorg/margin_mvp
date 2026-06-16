from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.execution.finance_functions import FINANCIAL_FUNCTIONS, TRANSFORMATIONS
from app.models import Function, FunctionImplementation, Metric, MetricSpec
from app.queue import enqueue_parse
from app.storage import upload_bytes

from app.models import Artifact, Dataset, ParseJob
from app.parsers.csv_parser import sniff_csv_columns


def seed_functions(db) -> None:
    if db.scalar(select(Function).limit(1)):
        return
    for name, spec in {**FINANCIAL_FUNCTIONS, **TRANSFORMATIONS}.items():
        fn_type = spec.get("function_type", "transformation")
        fn = Function(
            name=name,
            function_type=fn_type,
            description=spec.get("description", ""),
            input_schema=spec.get("input_schema", {}),
            output_schema=spec.get("output_schema", {}),
            owner="Investment Analytics",
            status="approved",
        )
        db.add(fn)
        db.flush()
        db.add(
            FunctionImplementation(
                function_id=fn.id,
                runtime="python",
                code_location=f"app.execution.finance_functions.{name}",
                implementation_body=name,
                version="1.0",
                status="approved",
            )
        )
    db.commit()


def seed_canonical_metrics(db) -> None:
    if db.scalar(select(Metric).limit(1)):
        return
    xirr_fn = db.scalar(select(Function).where(Function.name == "compute_xirr"))
    metric = Metric(
        canonical_name="Fund-Level Net IRR",
        description="Net internal rate of return for a fund after fees and expenses, including terminal NAV.",
        domain="Investment Performance",
        entity="fund",
        grain="fund_id",
        owner="Investment Operations",
        status="approved",
        version="1.0",
    )
    db.add(metric)
    db.flush()
    db.add(
        MetricSpec(
            metric_id=metric.id,
            required_inputs={
                "cashflows": {
                    "columns": ["fund_id", "cashflow_date", "cashflow_amount", "cashflow_type"],
                    "required": True,
                },
                "nav": {
                    "columns": ["fund_id", "nav_amount", "nav_date"],
                    "required": False,
                },
            },
            transformation_plan=[
                "normalize_cashflow_signs",
                "apply_fee_adjustments",
                "add_terminal_nav",
                "compute_xirr",
            ],
            calculation_function_id=xirr_fn.id if xirr_fn else None,
            validation_rules=[
                "no_missing_dates",
                "at_least_one_positive_cashflow",
                "at_least_one_negative_cashflow",
            ],
            approved_by="Investment Operations",
            approved_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def ingest_demo_artifact(db, filepath: str, owner: str | None = None) -> None:
    import os

    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        content = f.read()
    existing = db.scalar(select(Artifact).where(Artifact.filename == filename))
    if existing:
        return
    from app.parsers import artifact_type_from_filename

    key = upload_bytes(content, "artifacts", filename)
    artifact = Artifact(
        filename=filename,
        artifact_type=artifact_type_from_filename(filename),
        owner=owner,
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


def seed_demo_artifacts(db, demo_dir: str) -> None:
    import os

    if not os.path.isdir(demo_dir):
        return
    for name in sorted(os.listdir(demo_dir)):
        path = os.path.join(demo_dir, name)
        if os.path.isfile(path) and not name.endswith(".csv"):
            ingest_demo_artifact(db, path, owner="Investment Operations")


def seed_demo_datasets(db, demo_dir: str) -> None:
    import os

    for name in ["fund_cashflows.csv", "fund_nav.csv"]:
        path = os.path.join(demo_dir, name)
        if not os.path.isfile(path):
            continue
        existing = db.scalar(select(Dataset).where(Dataset.filename == name))
        if existing:
            continue
        with open(path, "rb") as f:
            content = f.read()
        cols, row_count = sniff_csv_columns(content)
        key = upload_bytes(content, "datasets", name)
        db.add(Dataset(filename=name, storage_path=key, detected_columns=cols, row_count=row_count))
    db.commit()


def run_seed(demo_dir: str = "/demo/investment_ops_demo") -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_functions(db)
        seed_canonical_metrics(db)
        seed_demo_datasets(db, demo_dir)
        seed_demo_artifacts(db, demo_dir)
        print("Seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    demo = sys.argv[1] if len(sys.argv) > 1 else "/demo/investment_ops_demo"
    run_seed(demo)
