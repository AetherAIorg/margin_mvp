"""metric registry tags

Revision ID: 002
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _digest(manifest: dict) -> str:
    import hashlib

    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if "metric_manifests" not in existing:
        op.create_table(
            "metric_manifests",
            sa.Column("digest", sa.String(80), primary_key=True),
            sa.Column("metric_id", sa.String(), sa.ForeignKey("metrics.id")),
            sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_metric_manifests_metric_id", "metric_manifests", ["metric_id"])

    if "metric_tags" not in existing:
        op.create_table(
            "metric_tags",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("metric_id", sa.String(), sa.ForeignKey("metrics.id")),
            sa.Column("tag", sa.String(80), nullable=False),
            sa.Column("digest", sa.String(80), sa.ForeignKey("metric_manifests.digest")),
            sa.Column("published_by", sa.String(120)),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(40), server_default="published"),
            sa.UniqueConstraint("metric_id", "tag", name="uq_metric_tag"),
        )
        op.create_index("ix_metric_tags_metric_id", "metric_tags", ["metric_id"])
        op.create_index("ix_metric_tags_digest", "metric_tags", ["digest"])

    tag_count = conn.execute(sa.text("SELECT COUNT(*) FROM metric_tags")).scalar() or 0
    if tag_count:
        return

    metrics = conn.execute(sa.text("SELECT id, canonical_name, description, domain, entity, grain, version, status FROM metrics")).fetchall()
    for metric in metrics:
        spec = conn.execute(
            sa.text(
                "SELECT required_inputs, transformation_plan, calculation_function_id, "
                "validation_rules, approved_by, approved_at FROM metric_specs "
                "WHERE metric_id = :mid LIMIT 1"
            ),
            {"mid": metric.id},
        ).fetchone()
        if not spec:
            continue
        manifest = {
            "canonical_name": metric.canonical_name,
            "description": metric.description or "",
            "domain": metric.domain or "",
            "entity": metric.entity or "",
            "grain": metric.grain or "",
            "required_inputs": spec.required_inputs,
            "transformation_plan": spec.transformation_plan,
            "calculation_function_id": spec.calculation_function_id,
            "validation_rules": spec.validation_rules,
            "approved_by": spec.approved_by,
            "approved_at": spec.approved_at.isoformat() if spec.approved_at else None,
        }
        digest = _digest(manifest)
        now = datetime.now(timezone.utc)
        conn.execute(
            sa.text(
                "INSERT INTO metric_manifests (digest, metric_id, manifest, created_at) "
                "VALUES (:digest, :mid, :manifest, :now) ON CONFLICT DO NOTHING"
            ),
            {"digest": digest, "mid": metric.id, "manifest": json.dumps(manifest), "now": now},
        )
        version_tag = metric.version or "1.0"
        for tag_name in {version_tag, "latest"}:
            conn.execute(
                sa.text(
                    "INSERT INTO metric_tags (id, metric_id, tag, digest, published_by, published_at, status) "
                    "VALUES (:id, :mid, :tag, :digest, :pub, :now, :status) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "mid": metric.id,
                    "tag": tag_name,
                    "digest": digest,
                    "pub": spec.approved_by or "system",
                    "now": now,
                    "status": "published" if metric.status == "approved" else "draft",
                },
            )


def downgrade() -> None:
    op.drop_table("metric_tags")
    op.drop_table("metric_manifests")
