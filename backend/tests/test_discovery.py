from __future__ import annotations

import pytest
from app.discovery.engine import build_discovery, candidate_key
from dataclasses import dataclass


@dataclass
class FakeNorm:
    normalized_ast: dict
    metric_family: str
    dimensions: dict


@dataclass
class FakeArtifact:
    filename: str


@dataclass
class FakeImpl:
    id: str
    extracted_name: str
    raw_formula: str
    is_deprecated: bool
    owner: str | None
    source_tables: dict | None
    artifact: FakeArtifact
    normalized: FakeNorm


def test_build_discovery_conflicts():
    impls = [
        FakeImpl("1", "Fund Net IRR", "XIRR(net,dates)", False, "Ops", {"refs": ["t"]}, FakeArtifact("a.xlsx"),
                 FakeNorm({"signature": "a"}, "IRR", {"time_basis": "actual_date", "basis": "net", "nav_treatment": "included", "fees": "included", "entity": "fund", "status": "unknown"})),
        FakeImpl("2", "Fund Net IRR", "monthly_irr(cfs)", False, None, None, FakeArtifact("b.sql"),
                 FakeNorm({"signature": "b"}, "IRR", {"time_basis": "monthly", "basis": "net", "nav_treatment": "included", "fees": "included", "entity": "fund", "status": "unknown"})),
    ]
    view = build_discovery([], impls)
    assert view.total_candidates >= 1
    assert any(i.issue_type == "CONFLICTING_TIME_BASIS" for i in view.issues)


def test_candidate_key():
    assert "fund" in candidate_key("Fund-Level Net IRR")
