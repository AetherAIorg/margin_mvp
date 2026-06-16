from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.registry import (
    ManifestSpecProxy,
    build_manifest_from_metric,
    compute_manifest_digest,
    publish_tag,
    resolve_tag,
)


def test_compute_manifest_digest_is_stable():
    manifest = {"a": 1, "b": [2, 3], "c": {"d": "e"}}
    assert compute_manifest_digest(manifest) == compute_manifest_digest(manifest)
    assert compute_manifest_digest(manifest).startswith("sha256:")


def test_manifest_spec_proxy_exposes_plan():
    proxy = ManifestSpecProxy(
        {
            "required_inputs": {"x": {}},
            "transformation_plan": ["step_a"],
            "validation_rules": [],
        }
    )
    assert proxy.transformation_plan == ["step_a"]


@pytest.fixture()
def db():
    from app.database import SessionLocal
    from app.models import Function, Metric, MetricSpec

    session = SessionLocal()
    trans = session.begin()
    try:
        yield session
    finally:
        trans.rollback()
        session.close()


def _seed_metric(db, name: str = "Registry Test IRR") -> tuple:
    from app.models import Function, Metric, MetricSpec

    fn = Function(
        name=f"compute_xirr_{name.replace(' ', '_').lower()}",
        function_type="financial_calculation",
        description="XIRR",
        input_schema={},
        output_schema={},
        status="approved",
    )
    db.add(fn)
    db.flush()
    metric = Metric(
        canonical_name=name,
        description="Test metric",
        domain="Performance",
        entity="fund",
        grain="fund_id",
        status="approved",
        version="1.0",
    )
    db.add(metric)
    db.flush()
    spec = MetricSpec(
        metric_id=metric.id,
        required_inputs={"cashflows": {"columns": ["amount"], "required": True}},
        transformation_plan=["compute_xirr"],
        calculation_function_id=fn.id,
        validation_rules=["no_missing_dates"],
        approved_by="Ops",
        approved_at=datetime.now(timezone.utc),
    )
    db.add(spec)
    db.flush()
    return metric, spec


def test_publish_tag_creates_manifest_and_tag(db):
    metric, spec = _seed_metric(db)
    manifest = build_manifest_from_metric(metric, spec)
    tag = publish_tag(db, metric, "1.0", manifest, "Ops")
    db.flush()
    assert tag.tag == "1.0"
    assert tag.digest.startswith("sha256:")
    assert resolve_tag(db, metric.id, "1.0") is not None


def test_same_manifest_reuses_digest(db):
    metric, spec = _seed_metric(db, "Digest Reuse A")
    manifest = build_manifest_from_metric(metric, spec)
    t1 = publish_tag(db, metric, "1.0", manifest, "Ops")
    metric2, spec2 = _seed_metric(db, "Digest Reuse B")
    t2 = publish_tag(db, metric2, "1.0", manifest, "Ops")
    db.flush()
    assert t1.digest == t2.digest


def test_resolve_tag_prefers_latest(db):
    metric, spec = _seed_metric(db, "Latest Tag Test")
    m1 = build_manifest_from_metric(metric, spec)
    publish_tag(db, metric, "1.0", m1, "Ops")
    m2 = dict(m1)
    m2["transformation_plan"] = ["normalize", "compute_xirr"]
    publish_tag(db, metric, "1.1", m2, "Ops")
    publish_tag(db, metric, "latest", m2, "Ops")
    db.flush()
    resolved = resolve_tag(db, metric.id, None)
    assert resolved is not None
    assert resolved.tag == "latest"
