"""Layer 1: the core knowledge graph.

The fixed six-node ontology and resolver-spine edges (`model`), a storage seam
with in-memory and Neo4j backends (`store`), and the thin `GraphClient` that is
the only write/read API. No raw Cypher leaves the store.
"""

from .client import GraphClient, WriteValidationError
from .model import (
    CORE_CONSTRAINTS,
    Constraint,
    ConstraintKind,
    CoreLabel,
    EdgeProvenance,
    RelType,
)
from .store import GraphStore, InMemoryGraphStore, Neo4jGraphStore

__all__ = [
    "GraphClient",
    "WriteValidationError",
    "CORE_CONSTRAINTS",
    "Constraint",
    "ConstraintKind",
    "CoreLabel",
    "EdgeProvenance",
    "RelType",
    "GraphStore",
    "InMemoryGraphStore",
    "Neo4jGraphStore",
]
