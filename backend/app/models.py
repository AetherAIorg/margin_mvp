from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(260), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="uploaded", index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    object_count: Mapped[int] = mapped_column(Integer, default=0)

    implementations: Mapped[list["FormulaImplementation"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class FormulaImplementation(Base):
    __tablename__ = "formula_implementations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"), index=True)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_formula: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(260), nullable=False)
    extracted_name: Mapped[str] = mapped_column(String(220), nullable=False)
    source_tables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    input_columns: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    referenced_functions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    nearby_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    artifact: Mapped[Artifact] = relationship(back_populates="implementations")
    normalized: Mapped["NormalizedFormula | None"] = relationship(
        back_populates="formula_implementation", uselist=False, cascade="all, delete-orphan"
    )


class NormalizedFormula(Base):
    __tablename__ = "normalized_formulas"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    formula_implementation_id: Mapped[str] = mapped_column(
        ForeignKey("formula_implementations.id"), unique=True, index=True
    )
    normalized_ast: Mapped[dict] = mapped_column(JSONB, nullable=False)
    function_family: Mapped[str] = mapped_column(String(80), default="")
    metric_family: Mapped[str] = mapped_column(String(80), default="", index=True)
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)
    input_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    semantic_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    embedding = mapped_column(Vector(1536), nullable=True)

    formula_implementation: Mapped[FormulaImplementation] = relationship(back_populates="normalized")


class MetricCandidate(Base):
    __tablename__ = "metric_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    proposed_name: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    metric_family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    grain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidate_key: Mapped[str] = mapped_column(String(220), nullable=False, index=True)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    canonical_name: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(120), default="Investment Performance")
    entity: Mapped[str] = mapped_column(String(80), default="fund")
    grain: Mapped[str] = mapped_column(String(80), default="fund_id")
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="candidate", index=True)
    version: Mapped[str] = mapped_column(String(40), default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    specs: Mapped[list["MetricSpec"]] = relationship(back_populates="metric", cascade="all, delete-orphan")
    tags: Mapped[list["MetricTag"]] = relationship(back_populates="metric", cascade="all, delete-orphan")
    manifests: Mapped[list["MetricManifest"]] = relationship(back_populates="metric", cascade="all, delete-orphan")


class MetricManifest(Base):
    __tablename__ = "metric_manifests"

    digest: Mapped[str] = mapped_column(String(80), primary_key=True)
    metric_id: Mapped[str] = mapped_column(ForeignKey("metrics.id"), index=True)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    metric: Mapped[Metric] = relationship(back_populates="manifests")
    tags: Mapped[list["MetricTag"]] = relationship(back_populates="manifest")


class MetricTag(Base):
    __tablename__ = "metric_tags"
    __table_args__ = (UniqueConstraint("metric_id", "tag", name="uq_metric_tag"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    metric_id: Mapped[str] = mapped_column(ForeignKey("metrics.id"), index=True)
    tag: Mapped[str] = mapped_column(String(80), nullable=False)
    digest: Mapped[str] = mapped_column(ForeignKey("metric_manifests.digest"), index=True)
    published_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    status: Mapped[str] = mapped_column(String(40), default="published")

    metric: Mapped[Metric] = relationship(back_populates="tags")
    manifest: Mapped[MetricManifest] = relationship(back_populates="tags")


class MetricSpec(Base):
    __tablename__ = "metric_specs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    metric_id: Mapped[str] = mapped_column(ForeignKey("metrics.id"), index=True)
    required_inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    transformation_plan: Mapped[list] = mapped_column(JSONB, nullable=False)
    calculation_function_id: Mapped[str | None] = mapped_column(ForeignKey("functions.id"), nullable=True)
    validation_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metric: Mapped[Metric] = relationship(back_populates="specs")
    calculation_function: Mapped["Function | None"] = relationship()


class Function(Base):
    __tablename__ = "functions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    function_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="approved")
    version: Mapped[str] = mapped_column(String(40), default="1.0")

    implementations: Mapped[list["FunctionImplementation"]] = relationship(
        back_populates="function", cascade="all, delete-orphan"
    )


class FunctionImplementation(Base):
    __tablename__ = "function_implementations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    function_id: Mapped[str] = mapped_column(ForeignKey("functions.id"), index=True)
    runtime: Mapped[str] = mapped_column(String(40), nullable=False)
    code_location: Mapped[str | None] = mapped_column(String(260), nullable=True)
    source_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    implementation_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(40), default="1.0")
    status: Mapped[str] = mapped_column(String(40), default="approved")

    function: Mapped[Function] = relationship(back_populates="implementations")


class MetricCluster(Base):
    __tablename__ = "metric_clusters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    cluster_name: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    metric_family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    canonical_metric_id: Mapped[str | None] = mapped_column(ForeignKey("metrics.id"), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)

    members: Mapped[list["MetricClusterMember"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )


class MetricClusterMember(Base):
    __tablename__ = "metric_cluster_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("metric_clusters.id"), index=True)
    formula_implementation_id: Mapped[str] = mapped_column(
        ForeignKey("formula_implementations.id"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(40), default="similar")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)

    cluster: Mapped[MetricCluster] = relationship(back_populates="members")
    formula_implementation: Mapped[FormulaImplementation] = relationship()


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), default="medium")
    metric_id: Mapped[str | None] = mapped_column(ForeignKey("metrics.id"), nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("metric_clusters.id"), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    affected_artifacts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open")
    title: Mapped[str] = mapped_column(String(260), default="")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(260), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    detected_columns: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MetricRun(Base):
    __tablename__ = "metric_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    metric_id: Mapped[str] = mapped_column(ForeignKey("metrics.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    transformation_plan_used: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audit_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    errors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ParseJob(Base):
    __tablename__ = "parse_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    rq_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
