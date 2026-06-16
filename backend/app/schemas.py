from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ArtifactOut(BaseModel):
    id: str
    filename: str
    artifact_type: str
    owner: str | None
    storage_path: str
    status: str
    uploaded_at: datetime
    object_count: int = 0


class ArtifactUploadResult(BaseModel):
    artifacts: list[ArtifactOut]
    parse_jobs: list[str]


class ParseJobOut(BaseModel):
    id: str
    artifact_id: str
    status: str
    rq_job_id: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class FormulaOut(BaseModel):
    id: str
    artifact_id: str
    language: str
    raw_formula: str
    location: str
    extracted_name: str
    confidence_score: float
    is_deprecated: bool
    owner: str | None
    artifact_filename: str | None = None
    dimensions: dict | None = None
    normalized_signature: str | None = None


class DiscoverySummaryOut(BaseModel):
    total_candidates: int
    total_artifacts: int
    total_implementations: int
    high_confidence_metrics: int
    formula_clusters: int
    families: list[dict[str, Any]]
    issue_counts: dict[str, int]


class MetricCandidateOut(BaseModel):
    id: str
    display_name: str
    family: str
    candidate_key: str
    implementation_count: int
    signature_count: int
    has_conflict: bool
    has_deprecated_reference: bool


class MetricCandidateDetailOut(MetricCandidateOut):
    implementations: list[FormulaOut]
    signatures: list[str]
    dimensions_summary: dict = Field(default_factory=dict)


class IssueOut(BaseModel):
    id: str | None = None
    issue_type: str
    title: str
    explanation: str
    severity: str = "medium"
    candidate_key: str | None = None
    implementation_ids: list[str] = Field(default_factory=list)
    affected_artifacts: list[str] = Field(default_factory=list)


class ClusterOut(BaseModel):
    id: str
    cluster_name: str
    metric_family: str
    member_count: int
    has_conflict: bool


class ClusterDetailOut(ClusterOut):
    members: list[FormulaOut]


class MetricSpecIn(BaseModel):
    required_inputs: dict
    transformation_plan: list[str]
    calculation_function_id: str | None = None
    validation_rules: list[str] | None = None


class MetricIn(BaseModel):
    canonical_name: str
    description: str = ""
    domain: str = "Investment Performance"
    entity: str = "fund"
    grain: str = "fund_id"
    owner: str | None = None
    spec: MetricSpecIn | None = None


class MetricSpecOut(BaseModel):
    id: str
    required_inputs: dict
    transformation_plan: list
    calculation_function_id: str | None
    validation_rules: list | None
    approved_by: str | None
    approved_at: datetime | None


class MetricOut(BaseModel):
    id: str
    canonical_name: str
    description: str
    domain: str
    entity: str
    grain: str
    owner: str | None
    status: str
    version: str
    tag_count: int = 0
    latest_tag: str | None = None
    latest_digest: str | None = None
    updated_at: datetime | None = None
    specs: list[MetricSpecOut] = Field(default_factory=list)


class MetricTagOut(BaseModel):
    id: str
    tag: str
    digest: str
    digest_short: str
    published_by: str | None
    published_at: datetime
    status: str


class MetricTagDetailOut(MetricTagOut):
    manifest: dict


class PublishTagIn(BaseModel):
    tag: str
    published_by: str = "Investment Operations"
    spec: MetricSpecIn | None = None


class MetricRunIn(BaseModel):
    dataset_id: str
    nav_dataset_id: str | None = None
    column_mapping: dict[str, str] | None = None
    tag: str | None = None


class MetricRunOut(BaseModel):
    id: str
    metric_id: str
    dataset_id: str
    status: str
    transformation_plan_used: list | None
    audit_log: dict | None
    warnings: list | None
    errors: list | None
    started_at: datetime
    finished_at: datetime | None


class FunctionOut(BaseModel):
    id: str
    name: str
    function_type: str
    description: str
    input_schema: dict
    output_schema: dict
    owner: str | None
    status: str
    version: str
    implementations: list[dict] = Field(default_factory=list)


class DatasetOut(BaseModel):
    id: str
    filename: str
    detected_columns: list[str] | None
    row_count: int
    uploaded_at: datetime


class ApproveMetricIn(BaseModel):
    approved_by: str
    spec_id: str | None = None


class SearchResult(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str
    snippet: str
    score: float
    href: str


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]
