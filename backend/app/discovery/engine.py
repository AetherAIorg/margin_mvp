from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STOPWORDS = {"the", "a", "an", "of", "for", "and", "level", "metric", "measure"}


@dataclass
class CandidateView:
    id: str
    display_name: str
    family: str
    candidate_key: str
    implementation_count: int
    signature_count: int
    has_conflict: bool
    has_deprecated_reference: bool
    implementations: list[Any] = field(default_factory=list)
    dimensions_summary: dict = field(default_factory=dict)


@dataclass
class IssueView:
    issue_type: str
    title: str
    explanation: str
    severity: str
    candidate_key: str | None
    implementation_ids: list[str] = field(default_factory=list)
    affected_artifacts: list[str] = field(default_factory=list)


@dataclass
class DiscoveryView:
    total_candidates: int
    total_artifacts: int
    total_implementations: int
    high_confidence_metrics: int
    formula_clusters: int
    families: list[dict[str, Any]]
    candidates: list[CandidateView]
    issues: list[IssueView]
    issue_counts: dict[str, int]


def candidate_key(label: str) -> str:
    text = label.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = text.replace("xirr", "irr")
    parts = [part for part in text.split() if part and part not in STOPWORDS]
    return "_".join(parts) if parts else "unknown"


def display_name_from_key(key: str) -> str:
    return " ".join(word.capitalize() for word in key.split("_"))


def build_candidates(implementations: list[Any]) -> list[CandidateView]:
    grouped: dict[str, list[Any]] = {}
    for impl in implementations:
        key = impl.normalized.metric_family if hasattr(impl, "normalized") and impl.normalized else impl.extracted_name
        ck = candidate_key(impl.extracted_name)
        grouped.setdefault(ck, []).append(impl)

    candidates: list[CandidateView] = []
    for key, impls in sorted(grouped.items()):
        signatures = set()
        for impl in impls:
            if impl.normalized:
                signatures.add(impl.normalized.normalized_ast.get("signature", ""))
        family = impls[0].normalized.metric_family if impls[0].normalized else "OTHER"
        display = display_name_from_key(key)
        deprecated_labels = {impl.extracted_name.lower() for impl in impls if impl.is_deprecated}
        has_deprecated_ref = any(
            any(dep in (impl.raw_formula or "").lower() for dep in deprecated_labels)
            for impl in implementations
            if not impl.is_deprecated
        )
        dim_sets = [impl.normalized.dimensions for impl in impls if impl.normalized]
        dim_summary = {}
        for dim in ["time_basis", "basis", "nav_treatment", "fees", "entity", "status"]:
            values = {d.get(dim, "unknown") for d in dim_sets}
            dim_summary[dim] = list(values)
        candidates.append(
            CandidateView(
                id=key,
                display_name=display,
                family=family,
                candidate_key=key,
                implementation_count=len(impls),
                signature_count=len(signatures) or 1,
                has_conflict=len(signatures) > 1,
                has_deprecated_reference=has_deprecated_ref,
                implementations=impls,
                dimensions_summary=dim_summary,
            )
        )
    return candidates


def detect_dimension_conflicts(candidate: CandidateView) -> list[IssueView]:
    issues: list[IssueView] = []
    impls = candidate.implementations
    dims_list = [impl.normalized.dimensions for impl in impls if impl.normalized]

    def check_dim(dim: str, issue_type: str, title_prefix: str):
        values = {d.get(dim, "unknown") for d in dims_list if d.get(dim, "unknown") != "unknown"}
        if len(values) > 1:
            issues.append(
                IssueView(
                    issue_type=issue_type,
                    title=f"{title_prefix}: {candidate.display_name}",
                    explanation=f"Conflicting {dim} values: {', '.join(sorted(values))}",
                    severity="high",
                    candidate_key=candidate.candidate_key,
                    implementation_ids=[impl.id for impl in impls],
                    affected_artifacts=[impl.artifact.filename for impl in impls if impl.artifact],
                )
            )

    check_dim("time_basis", "CONFLICTING_TIME_BASIS", "Conflicting time basis")
    check_dim("basis", "CONFLICTING_FEE_TREATMENT", "Conflicting fee treatment")
    check_dim("basis", "GROSS_NET_MISMATCH", "Gross vs net mismatch")
    check_dim("status", "REALIZED_UNREALIZED_MISMATCH", "Realized vs unrealized mismatch")
    check_dim("entity", "INCONSISTENT_ENTITY_GRAIN", "Inconsistent entity grain")
    return issues


def build_issues(candidates: list[CandidateView], implementations: list[Any]) -> list[IssueView]:
    issues: list[IssueView] = []

    for candidate in candidates:
        if candidate.has_conflict:
            issues.append(
                IssueView(
                    issue_type="CONFLICTING_DEFINITION",
                    title=f"Conflicting definitions: {candidate.display_name}",
                    explanation=f"{candidate.signature_count} distinct formula signatures across {candidate.implementation_count} implementations.",
                    severity="high",
                    candidate_key=candidate.candidate_key,
                    implementation_ids=[impl.id for impl in candidate.implementations],
                )
            )
        issues.extend(detect_dimension_conflicts(candidate))

        missing_owner = all(not impl.owner for impl in candidate.implementations)
        if missing_owner:
            issues.append(
                IssueView(
                    issue_type="MISSING_OWNER",
                    title=f"Missing owner: {candidate.display_name}",
                    explanation="All implementations lack an assigned owner.",
                    severity="medium",
                    candidate_key=candidate.candidate_key,
                    implementation_ids=[impl.id for impl in candidate.implementations],
                )
            )

        missing_docs = [impl for impl in candidate.implementations if not impl.source_tables]
        if missing_docs:
            issues.append(
                IssueView(
                    issue_type="MISSING_SOURCE_DOCUMENTATION",
                    title=f"Missing source documentation: {candidate.display_name}",
                    explanation=f"{len(missing_docs)} implementation(s) have no source-data references.",
                    severity="medium",
                    candidate_key=candidate.candidate_key,
                    implementation_ids=[impl.id for impl in missing_docs],
                )
            )

    deprecated_impls = [impl for impl in implementations if impl.is_deprecated]
    for dep in deprecated_impls:
        referenced_by = [
            impl
            for impl in implementations
            if not impl.is_deprecated and dep.extracted_name.lower() in impl.raw_formula.lower()
        ]
        if referenced_by:
            issues.append(
                IssueView(
                    issue_type="DEPRECATED_FORMULA_REFERENCED",
                    title=f"Deprecated formula still referenced: {dep.extracted_name}",
                    explanation=f"Referenced by {len(referenced_by)} active implementation(s).",
                    severity="high",
                    candidate_key=candidate_key(dep.extracted_name),
                    implementation_ids=[dep.id, *[r.id for r in referenced_by]],
                    affected_artifacts=[impl.artifact.filename for impl in referenced_by if impl.artifact],
                )
            )

    return issues


def build_families(candidates: list[CandidateView]) -> list[dict[str, Any]]:
    families: dict[str, list[CandidateView]] = {}
    for candidate in candidates:
        families.setdefault(candidate.family, []).append(candidate)
    return [
        {
            "family": family,
            "candidate_count": len(items),
            "implementation_count": sum(c.implementation_count for c in items),
            "candidates": [
                {
                    "id": c.id,
                    "display_name": c.display_name,
                    "implementation_count": c.implementation_count,
                    "has_conflict": c.has_conflict,
                }
                for c in sorted(items, key=lambda item: item.display_name)
            ],
        }
        for family, items in sorted(families.items())
    ]


def build_discovery(artifacts: list[Any], implementations: list[Any]) -> DiscoveryView:
    candidates = build_candidates(implementations)
    issues = build_issues(candidates, implementations)
    issue_counts: dict[str, int] = {}
    for issue in issues:
        issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1
    high_conf = sum(1 for c in candidates if c.implementation_count >= 2 and not c.has_conflict)
    return DiscoveryView(
        total_candidates=len(candidates),
        total_artifacts=len(artifacts),
        total_implementations=len(implementations),
        high_confidence_metrics=high_conf,
        formula_clusters=len(candidates),
        families=build_families(candidates),
        candidates=candidates,
        issues=issues,
        issue_counts=issue_counts,
    )
