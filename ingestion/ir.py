"""The common intermediate representation (IR) for the ingestion layer.

This is the single source-agnostic shape that every connector normalizes into.
SharePoint, Postgres, Snowflake, REST APIs: they all differ at the edge, but the
moment their bytes are parsed they become one of these records. Nothing
downstream (the graph, the resolver) ever sees a connector-specific shape. That
decoupling is the entire point of this module, so treat these dataclasses as a
stable contract, not an implementation detail.

Design notes on the seams:
  - Every parsed record carries a `schema_version`. Parsers stamp it so that a
    consumer can evolve independently of producers and reject shapes it does not
    understand.
  - An `ObservedEntity` may carry its own `columns`. An entity is not only a
    thing that external columns describe; it can itself be a measured dataset
    with its own feed. Reference entities that carry their own data are a
    first-class generic case here, not a special path bolted on later.
  - Identity is expressed with plain string keys (uid, uri, the column triple).
    The IR never invents graph internals; it speaks the same keys the core
    ontology constrains on, so the load step is a mechanical MERGE.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Bump when the shape of any record below changes in a backward-incompatible
# way. Parsers stamp this onto every record; consumers may gate on it.
IR_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a bundle came from and when. Attached once per bundle and, at load
    time, folded into every edge as (source_ref, as_of, created_by)."""

    source_ref: str
    """Stable identifier for the origin, e.g. "postgres://warehouse/public" or
    a SharePoint site URL. Opaque to the core; meaningful to the connector."""

    fetched_at: str
    """ISO-8601 timestamp of when the raw artifact was pulled."""

    connector_version: str
    """Version string of the connector that produced this bundle. Becomes the
    `created_by` provenance on written edges so a re-parse can be attributed."""


@dataclass(frozen=True, slots=True)
class ObservedColumn:
    """A physical column seen in some source system. Maps to a :Column node and
    is the primary input to the resolver (column -> Metric)."""

    system: str
    table: str
    name: str
    dtype: str | None = None
    sample_values: tuple[str, ...] = ()
    has_dictionary: bool = False
    """True if the source shipped a data dictionary / description for this
    column. When False the resolver must infer meaning, which is the whole
    reason the resolver exists."""

    schema_version: str = IR_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ObservedDocument:
    """A qualitative prose artifact seen in some source. Maps to a :Document."""

    uri: str
    title: str | None = None
    text: str = ""
    as_of: str | None = None

    describes: tuple[str, ...] = ()
    """Entity uids this document describes. The loader creates a
    (:Document)-[:DESCRIBES]->(:Entity) edge for each, so a connector can express
    doc-to-entity linkage in the IR instead of wiring it downstream."""

    defines: tuple[str, ...] = ()
    """Metric keys whose canonical definition lives in this document. The loader
    creates a (:Metric)-[:DEFINED_IN]->(:Document) edge for each."""

    schema_version: str = IR_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ObservedEntity:
    """A thing being described. Maps to an :Entity node plus, optionally, a pack
    subtype label drawn from `candidate_labels`.

    `columns` lets an entity carry its own observed columns. Use it when the
    entity IS a measured dataset (it has its own feed), as opposed to being
    described by columns that live in some other table. Both cases are generic;
    this field is what keeps the second one first-class."""

    uid: str
    candidate_labels: tuple[str, ...] = ()
    """Zero or more proposed pack subtype labels (e.g. "Widget"). The write API
    validates these against the loaded pack allow-list; unknown labels are
    rejected rather than silently written."""

    attributes: dict[str, object] = field(default_factory=dict)
    columns: tuple[ObservedColumn, ...] = ()
    schema_version: str = IR_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ObservedRelation:
    """A structural triple between two entities: (subject)-[role]->(object).

    By default this becomes (:Entity)-[:RELATED_TO {role}]->(:Entity), the generic
    escape hatch. To emit a pack-specialized edge type instead (e.g. a domain's
    allow-listed SUBORDINATE_TO), set `rel_type`; the loader routes it through the
    write API, which validates it against the loaded pack's edge allow-list."""

    subject_uid: str
    role: str
    object_uid: str

    rel_type: str | None = None
    """Optional specialized relationship type. None means the generic RELATED_TO.
    A non-None value must be allow-listed by a loaded pack or the write is rejected."""

    attributes: dict[str, object] = field(default_factory=dict)
    schema_version: str = IR_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ParsedBundle:
    """The normalized output of `Source.parse`: the IR itself.

    A bundle is additive and idempotent to load. Fields default empty so a
    connector that only produces documents (or only columns) constructs a valid
    bundle without ceremony."""

    provenance: Provenance
    columns: tuple[ObservedColumn, ...] = ()
    documents: tuple[ObservedDocument, ...] = ()
    entities: tuple[ObservedEntity, ...] = ()
    relations: tuple[ObservedRelation, ...] = ()

    def iter_columns(self) -> tuple[ObservedColumn, ...]:
        """All columns in the bundle: the free-standing ones plus those an
        entity carries on itself. Consumers (the resolver, the loader) should
        use this so entity-owned columns are never missed."""
        owned = tuple(c for e in self.entities for c in e.columns)
        return self.columns + owned
