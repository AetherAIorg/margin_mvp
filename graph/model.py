"""The fixed core ontology: the six node types and the resolver-spine edges that
every future domain pack shares.

This module is the schema contract for Layer 1. It defines WHAT exists in the
graph (node shapes, identity constraints, edge types) as structured Python data,
never as Cypher strings. The graph client (built later) turns these declarations
into MERGE statements and constraint DDL; calling code and packs read them to
validate writes. Keeping the schema as data, not embedded queries, is what lets
the write API enforce the multi-label and allow-list invariants generically.

Nothing in here names any industry. The core is deliberately empty of domain
meaning; packs add entity subtype labels and specialized edge types on top.

The invariant spine (domain-agnostic, the whole point):

    (Column)   -[:MEASURES]->            (Metric)
    (Metric)   -[:APPLIES_TO]->          (Entity)
    (Metric)   -[:DEFINED_IN]->          (Document)
    (Metric)   -[:BENCHMARKED_AGAINST]-> (Benchmark)
    (Metric)   -[:COMPUTED_FROM]->       (Metric)
    (Document) -[:DESCRIBES]->           (Entity)
    (Party)    -[:HAS_ROLE {role}]->     (Entity)
    (Entity)   -[:RELATED_TO {role}]->   (Entity)   generic escape hatch
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# --------------------------------------------------------------------------- #
# Labels                                                                       #
# --------------------------------------------------------------------------- #

class CoreLabel(str, Enum):
    """The six base node labels. Every asset node carries EXACTLY one of these as
    its base label. An Entity additionally carries an optional pack subtype label
    (the multi-label pattern), validated at write time against the loaded pack."""

    ENTITY = "Entity"
    METRIC = "Metric"
    COLUMN = "Column"
    DOCUMENT = "Document"
    BENCHMARK = "Benchmark"
    PARTY = "Party"


# --------------------------------------------------------------------------- #
# Edge (relationship) types                                                    #
# --------------------------------------------------------------------------- #

class RelType(str, Enum):
    """The fixed resolver-spine relationship types. Packs may register additional
    specialized edge types via the pack allow-list, but these are always present
    and always mean the same thing across every domain."""

    MEASURES = "MEASURES"                       # Column  -> Metric
    APPLIES_TO = "APPLIES_TO"                    # Metric  -> Entity
    DEFINED_IN = "DEFINED_IN"                    # Metric  -> Document
    BENCHMARKED_AGAINST = "BENCHMARKED_AGAINST"  # Metric  -> Benchmark
    COMPUTED_FROM = "COMPUTED_FROM"              # Metric  -> Metric
    DESCRIBES = "DESCRIBES"                      # Document-> Entity
    HAS_ROLE = "HAS_ROLE"                        # Party   -> Entity   {role}
    RELATED_TO = "RELATED_TO"                    # Entity  -> Entity   {role}


@dataclass(frozen=True, slots=True)
class EdgeProvenance:
    """Provenance carried on EVERY written edge. No edge is created without it, so
    any fact in the graph can be traced to the parser/resolver run that asserted
    it and the moment it was true."""

    source_ref: str
    as_of: str
    created_by: str
    """Version of the parser or resolver that wrote the edge, e.g.
    "synthetic-csv@0.1.0" or "resolver.exact@1.0"."""


# --------------------------------------------------------------------------- #
# Node property shapes                                                         #
# --------------------------------------------------------------------------- #
# These describe the properties each node type stores. They are payload shapes,
# not ORM rows: the client MERGEs on the identity key(s) and sets the rest. All
# writes are idempotent because MERGE keys on the constrained property.

@dataclass(frozen=True, slots=True)
class EntityNode:
    """The thing being described. Base :Entity label plus an optional pack subtype
    label. Identity: uid (unique)."""

    uid: str
    subtype_label: str | None = None
    """Second label added alongside :Entity, e.g. "Widget". MUST be in the loaded
    pack's entity-subtype allow-list or the write is rejected."""

    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetricNode:
    """Canonical definition of a measurement. Identity: metric_key (unique),
    namespaced as "<pack>.<name>" (e.g. "shared.count", "widgets.weight")."""

    metric_key: str
    formula: str | None = None
    unit: str | None = None
    numerator_def: str | None = None
    denominator_def: str | None = None
    provenance: str | None = None
    """Free-text provenance of the DEFINITION itself (where the canonical meaning
    came from), distinct from the per-edge EdgeProvenance."""

    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ColumnNode:
    """A physical column observed in a source system. Identity: NODE KEY on the
    composite (system, table, name)."""

    system: str
    table: str
    name: str
    dtype: str | None = None
    sample_values: tuple[str, ...] = ()
    has_dictionary: bool = False


@dataclass(frozen=True, slots=True)
class DocumentNode:
    """A qualitative prose artifact. Identity: uri (unique)."""

    uri: str
    title: str | None = None
    text: str = ""
    as_of: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkNode:
    """A relational/strategic reference point. Identity: benchmark_key (unique)."""

    benchmark_key: str
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PartyNode:
    """An actor with a role toward an entity. Identity: uid (unique)."""

    uid: str
    attributes: dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Identity constraints                                                         #
# --------------------------------------------------------------------------- #
# Declared as data so the client can emit the matching Neo4j DDL and the write
# API can reason about identity keys without parsing Cypher.

class ConstraintKind(str, Enum):
    UNIQUE = "UNIQUE"      # single-property uniqueness
    NODE_KEY = "NODE_KEY"  # composite key (all properties together are unique)


@dataclass(frozen=True, slots=True)
class Constraint:
    label: CoreLabel
    properties: tuple[str, ...]
    kind: ConstraintKind


CORE_CONSTRAINTS: tuple[Constraint, ...] = (
    Constraint(CoreLabel.ENTITY, ("uid",), ConstraintKind.UNIQUE),
    Constraint(CoreLabel.METRIC, ("metric_key",), ConstraintKind.UNIQUE),
    Constraint(CoreLabel.DOCUMENT, ("uri",), ConstraintKind.UNIQUE),
    Constraint(CoreLabel.BENCHMARK, ("benchmark_key",), ConstraintKind.UNIQUE),
    Constraint(CoreLabel.PARTY, ("uid",), ConstraintKind.UNIQUE),
    Constraint(CoreLabel.COLUMN, ("system", "table", "name"), ConstraintKind.NODE_KEY),
)
