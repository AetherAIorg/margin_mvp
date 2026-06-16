"""Docker Registry-style manifest digest and tag publishing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Metric, MetricManifest, MetricSpec, MetricTag, now_utc


def canonical_manifest_json(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"))


def compute_manifest_digest(manifest: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_manifest_json(manifest).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_manifest_from_metric(metric: Metric, spec: MetricSpec) -> dict[str, Any]:
    return {
        "canonical_name": metric.canonical_name,
        "description": metric.description,
        "domain": metric.domain,
        "entity": metric.entity,
        "grain": metric.grain,
        "required_inputs": spec.required_inputs,
        "transformation_plan": spec.transformation_plan,
        "calculation_function_id": spec.calculation_function_id,
        "validation_rules": spec.validation_rules,
        "approved_by": spec.approved_by,
        "approved_at": spec.approved_at.isoformat() if spec.approved_at else None,
    }


def build_manifest_from_payload(metric: Metric, spec_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_name": metric.canonical_name,
        "description": metric.description,
        "domain": metric.domain,
        "entity": metric.entity,
        "grain": metric.grain,
        "required_inputs": spec_payload["required_inputs"],
        "transformation_plan": spec_payload["transformation_plan"],
        "calculation_function_id": spec_payload.get("calculation_function_id"),
        "validation_rules": spec_payload.get("validation_rules"),
        "approved_by": None,
        "approved_at": None,
    }


def get_or_create_manifest(db: Session, metric_id: str, manifest: dict[str, Any]) -> MetricManifest:
    digest = compute_manifest_digest(manifest)
    existing = db.get(MetricManifest, digest)
    if existing:
        return existing
    row = MetricManifest(digest=digest, metric_id=metric_id, manifest=manifest)
    db.add(row)
    db.flush()
    return row


def publish_tag(
    db: Session,
    metric: Metric,
    tag_name: str,
    manifest: dict[str, Any],
    published_by: str,
    status: str = "published",
) -> MetricTag:
    existing_tag = db.scalar(
        select(MetricTag).where(MetricTag.metric_id == metric.id, MetricTag.tag == tag_name)
    )
    if existing_tag:
        raise ValueError(f"Tag '{tag_name}' already exists for this metric")

    manifest_row = get_or_create_manifest(db, metric.id, manifest)
    tag_row = MetricTag(
        metric_id=metric.id,
        tag=tag_name,
        digest=manifest_row.digest,
        published_by=published_by,
        published_at=now_utc(),
        status=status,
    )
    db.add(tag_row)
    metric.version = tag_name
    metric.updated_at = datetime.now(timezone.utc)
    db.flush()
    return tag_row


def resolve_tag(db: Session, metric_id: str, tag: str | None) -> MetricTag | None:
    if tag:
        return db.scalar(
            select(MetricTag).where(MetricTag.metric_id == metric_id, MetricTag.tag == tag)
        )
    latest = db.scalar(
        select(MetricTag)
        .where(MetricTag.metric_id == metric_id, MetricTag.tag == "latest", MetricTag.status != "deprecated")
        .limit(1)
    )
    if latest:
        return latest
    return db.scalar(
        select(MetricTag)
        .where(MetricTag.metric_id == metric_id, MetricTag.status == "published")
        .order_by(MetricTag.published_at.desc())
        .limit(1)
    )


def tag_summary(db: Session, metric_id: str) -> dict[str, Any]:
    tags = list(
        db.scalars(
            select(MetricTag)
            .where(MetricTag.metric_id == metric_id)
            .order_by(MetricTag.published_at.desc())
        )
    )
    latest = next((t for t in tags if t.tag == "latest"), tags[0] if tags else None)
    return {
        "tag_count": len(tags),
        "latest_tag": latest.tag if latest else None,
        "latest_digest": latest.digest if latest else None,
    }


class ManifestSpecProxy:
    """Execution-time view of a frozen manifest (no DB MetricSpec row required)."""

    def __init__(self, manifest: dict[str, Any], calculation_function=None) -> None:
        self.id = manifest.get("spec_id", "manifest")
        self.required_inputs = manifest["required_inputs"]
        self.transformation_plan = manifest["transformation_plan"]
        self.calculation_function_id = manifest.get("calculation_function_id")
        self.validation_rules = manifest.get("validation_rules")
        self.approved_by = manifest.get("approved_by")
        self.approved_at = manifest.get("approved_at")
        self.calculation_function = calculation_function
