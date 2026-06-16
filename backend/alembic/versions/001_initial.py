"""initial schema

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("filename", sa.String(260), nullable=False),
        sa.Column("artifact_type", sa.String(20), nullable=False),
        sa.Column("owner", sa.String(120), nullable=True),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("status", sa.String(40), server_default="uploaded"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("object_count", sa.Integer(), server_default="0"),
    )
    op.create_table(
        "functions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("function_type", sa.String(40), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("owner", sa.String(120)),
        sa.Column("status", sa.String(40), server_default="approved"),
        sa.Column("version", sa.String(40), server_default="1.0"),
    )
    op.create_table(
        "metrics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("canonical_name", sa.String(220), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("domain", sa.String(120)),
        sa.Column("entity", sa.String(80)),
        sa.Column("grain", sa.String(80)),
        sa.Column("owner", sa.String(120)),
        sa.Column("status", sa.String(40), server_default="candidate"),
        sa.Column("version", sa.String(40), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("filename", sa.String(260), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("detected_columns", sa.JSON()),
        sa.Column("row_count", sa.Integer(), server_default="0"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "formula_implementations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifacts.id")),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("raw_formula", sa.Text(), nullable=False),
        sa.Column("location", sa.String(260), nullable=False),
        sa.Column("extracted_name", sa.String(220), nullable=False),
        sa.Column("source_tables", sa.JSON()),
        sa.Column("input_columns", sa.JSON()),
        sa.Column("referenced_functions", sa.JSON()),
        sa.Column("nearby_context", sa.Text()),
        sa.Column("confidence_score", sa.Float(), server_default="0.5"),
        sa.Column("is_deprecated", sa.Boolean(), server_default="false"),
        sa.Column("owner", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "normalized_formulas",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("formula_implementation_id", sa.String(), sa.ForeignKey("formula_implementations.id"), unique=True),
        sa.Column("normalized_ast", sa.JSON(), nullable=False),
        sa.Column("function_family", sa.String(80)),
        sa.Column("metric_family", sa.String(80)),
        sa.Column("dimensions", sa.JSON()),
        sa.Column("input_signature", sa.JSON()),
        sa.Column("semantic_tags", sa.JSON()),
        sa.Column("embedding", Vector(1536)),
    )
    op.create_table(
        "metric_candidates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("proposed_name", sa.String(220), nullable=False),
        sa.Column("metric_family", sa.String(80), nullable=False),
        sa.Column("entity", sa.String(80)),
        sa.Column("grain", sa.String(80)),
        sa.Column("description", sa.Text()),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("evidence", sa.JSON()),
        sa.Column("candidate_key", sa.String(220), nullable=False),
    )
    op.create_table(
        "metric_specs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("metric_id", sa.String(), sa.ForeignKey("metrics.id")),
        sa.Column("required_inputs", sa.JSON(), nullable=False),
        sa.Column("transformation_plan", sa.JSON(), nullable=False),
        sa.Column("calculation_function_id", sa.String(), sa.ForeignKey("functions.id")),
        sa.Column("validation_rules", sa.JSON()),
        sa.Column("approved_by", sa.String(120)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "function_implementations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("function_id", sa.String(), sa.ForeignKey("functions.id")),
        sa.Column("runtime", sa.String(40), nullable=False),
        sa.Column("code_location", sa.String(260)),
        sa.Column("source_artifact_id", sa.String(), sa.ForeignKey("artifacts.id")),
        sa.Column("implementation_body", sa.Text()),
        sa.Column("version", sa.String(40)),
        sa.Column("status", sa.String(40)),
    )
    op.create_table(
        "metric_clusters",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("cluster_name", sa.String(220), nullable=False),
        sa.Column("metric_family", sa.String(80), nullable=False),
        sa.Column("canonical_metric_id", sa.String(), sa.ForeignKey("metrics.id")),
        sa.Column("confidence_score", sa.Float()),
    )
    op.create_table(
        "metric_cluster_members",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("cluster_id", sa.String(), sa.ForeignKey("metric_clusters.id")),
        sa.Column("formula_implementation_id", sa.String(), sa.ForeignKey("formula_implementations.id")),
        sa.Column("relationship_type", sa.String(40)),
        sa.Column("confidence_score", sa.Float()),
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("issue_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(40)),
        sa.Column("metric_id", sa.String(), sa.ForeignKey("metrics.id")),
        sa.Column("cluster_id", sa.String(), sa.ForeignKey("metric_clusters.id")),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("affected_artifacts", sa.JSON()),
        sa.Column("suggested_action", sa.Text()),
        sa.Column("status", sa.String(40)),
        sa.Column("title", sa.String(260)),
    )
    op.create_table(
        "metric_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("metric_id", sa.String(), sa.ForeignKey("metrics.id")),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id")),
        sa.Column("status", sa.String(40)),
        sa.Column("transformation_plan_used", sa.JSON()),
        sa.Column("result_path", sa.String(512)),
        sa.Column("audit_log", sa.JSON()),
        sa.Column("warnings", sa.JSON()),
        sa.Column("errors", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "parse_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifacts.id")),
        sa.Column("status", sa.String(40)),
        sa.Column("rq_job_id", sa.String(120)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for table in [
        "parse_jobs", "metric_runs", "issues", "metric_cluster_members",
        "metric_clusters", "function_implementations", "metric_specs",
        "metric_candidates", "normalized_formulas", "formula_implementations",
        "datasets", "metrics", "functions", "artifacts",
    ]:
        op.drop_table(table)
