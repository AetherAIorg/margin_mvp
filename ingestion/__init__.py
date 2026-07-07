"""Layer 2: the generic ingestion contract.

Every source implements `Source` (discover/fetch/parse) and normalizes into the
one common IR (`ir`). Cross-cutting infra: a single rate limiter, a parser
router, an idempotent-discovery checkpointer, and the pipeline that drives them.
"""

from .checkpoint import Checkpointer, InMemoryCheckpointer
from .ir import (
    IR_SCHEMA_VERSION,
    ObservedColumn,
    ObservedDocument,
    ObservedEntity,
    ObservedRelation,
    ParsedBundle,
    Provenance,
)
from .pipeline import IngestReport, load_bundle, run_ingest
from .ratelimit import RateLimiter, TokenBucket
from .router import ParserRouter
from .source import RawArtifact, Source, WorkItem

__all__ = [
    "Checkpointer",
    "InMemoryCheckpointer",
    "IR_SCHEMA_VERSION",
    "ObservedColumn",
    "ObservedDocument",
    "ObservedEntity",
    "ObservedRelation",
    "ParsedBundle",
    "Provenance",
    "IngestReport",
    "load_bundle",
    "run_ingest",
    "RateLimiter",
    "TokenBucket",
    "ParserRouter",
    "RawArtifact",
    "Source",
    "WorkItem",
]
