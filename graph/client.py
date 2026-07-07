"""GraphClient: the thin Python API over the core ontology.

Calling code (connectors, the resolver, packs) uses only this. It never writes
Cypher and never touches the store's key layout directly. Responsibilities:

  - Compose the six node upserts and the eight spine edges from typed inputs.
  - Enforce the multi-label invariant: an Entity subtype label is written ONLY
    if a loaded pack allow-listed it; unknown labels raise, they are not silently
    written. Same for pack-specialized edge types.
  - Fold EdgeProvenance onto every edge (source_ref, as_of, created_by).
  - Provide the resolver's read path, `resolve_column`.

Idempotency comes for free: every write is an upsert on the identity key, so
re-ingesting the same facts converges rather than duplicating.
"""

from __future__ import annotations

from .model import (
    CORE_CONSTRAINTS,
    CoreLabel,
    EdgeProvenance,
    RelType,
)
from .store import GraphStore


def _clean(props: dict[str, object]) -> dict[str, object]:
    """Drop None-valued properties so nodes stay sparse and upserts converge."""
    return {k: v for k, v in props.items() if v is not None}


class WriteValidationError(ValueError):
    """Raised when a write violates the multi-label or edge allow-list invariant."""


class GraphClient:
    def __init__(self, store: GraphStore) -> None:
        self._store = store
        # Allow-lists registered by load_pack. Populated at pack-load time and
        # consulted on every write. Empty means "core only": no subtypes, only
        # the fixed spine edges plus the RELATED_TO escape hatch.
        self._entity_subtypes: set[str] = set()
        self._pack_edge_types: set[str] = set()

    # -- schema / pack registration --------------------------------------- #

    def init_schema(self) -> None:
        """Create the core identity constraints. Idempotent."""
        self._store.ensure_constraints(CORE_CONSTRAINTS)

    def register_allowlists(
        self, entity_subtypes: set[str], edge_types: set[str]
    ) -> None:
        """Called by the pack loader. Widens what writes may assert. Additive so
        multiple packs compose."""
        self._entity_subtypes |= set(entity_subtypes)
        self._pack_edge_types |= set(edge_types)

    @property
    def allowed_entity_subtypes(self) -> frozenset[str]:
        return frozenset(self._entity_subtypes)

    # -- node upserts ------------------------------------------------------ #

    def upsert_entity(
        self,
        uid: str,
        subtype_label: str | None = None,
        attributes: dict[str, object] | None = None,
    ) -> None:
        if subtype_label is not None and subtype_label not in self._entity_subtypes:
            raise WriteValidationError(
                f"entity subtype label {subtype_label!r} is not allow-listed by any "
                f"loaded pack; allowed: {sorted(self._entity_subtypes) or '(none)'}"
            )
        extra = (subtype_label,) if subtype_label else ()
        self._store.upsert_node(
            CoreLabel.ENTITY.value, {"uid": uid}, _clean(attributes or {}), extra
        )

    def upsert_metric(
        self,
        metric_key: str,
        formula: str | None = None,
        unit: str | None = None,
        numerator_def: str | None = None,
        denominator_def: str | None = None,
        provenance: str | None = None,
        attributes: dict[str, object] | None = None,
    ) -> None:
        props = {
            "formula": formula,
            "unit": unit,
            "numerator_def": numerator_def,
            "denominator_def": denominator_def,
            "provenance": provenance,
            **(attributes or {}),
        }
        self._store.upsert_node(
            CoreLabel.METRIC.value, {"metric_key": metric_key}, _clean(props)
        )

    def upsert_column(
        self,
        system: str,
        table: str,
        name: str,
        dtype: str | None = None,
        sample_values: tuple[str, ...] = (),
        has_dictionary: bool = False,
    ) -> None:
        self._store.upsert_node(
            CoreLabel.COLUMN.value,
            {"system": system, "table": table, "name": name},
            _clean(
                {
                    "dtype": dtype,
                    "sample_values": list(sample_values),
                    "has_dictionary": has_dictionary,
                }
            ),
        )

    def upsert_document(
        self,
        uri: str,
        title: str | None = None,
        text: str = "",
        as_of: str | None = None,
    ) -> None:
        self._store.upsert_node(
            CoreLabel.DOCUMENT.value,
            {"uri": uri},
            _clean({"title": title, "text": text, "as_of": as_of}),
        )

    def upsert_benchmark(
        self, benchmark_key: str, attributes: dict[str, object] | None = None
    ) -> None:
        self._store.upsert_node(
            CoreLabel.BENCHMARK.value,
            {"benchmark_key": benchmark_key},
            _clean(attributes or {}),
        )

    def upsert_party(
        self, uid: str, attributes: dict[str, object] | None = None
    ) -> None:
        self._store.upsert_node(
            CoreLabel.PARTY.value, {"uid": uid}, _clean(attributes or {})
        )

    # -- spine edges ------------------------------------------------------- #

    def _edge(
        self,
        rel: RelType | str,
        src_label: CoreLabel,
        src_key: dict[str, object],
        dst_label: CoreLabel,
        dst_key: dict[str, object],
        prov: EdgeProvenance,
        key_props: dict[str, object] | None = None,
    ) -> None:
        rel_name = rel.value if isinstance(rel, RelType) else rel
        set_props = {
            "source_ref": prov.source_ref,
            "as_of": prov.as_of,
            "created_by": prov.created_by,
        }
        self._store.upsert_edge(
            rel_name,
            src_label.value,
            src_key,
            dst_label.value,
            dst_key,
            key_props or {},
            set_props,
        )

    def link_column_to_metric(
        self,
        system: str,
        table: str,
        name: str,
        metric_key: str,
        prov: EdgeProvenance,
    ) -> None:
        self._edge(
            RelType.MEASURES,
            CoreLabel.COLUMN,
            {"system": system, "table": table, "name": name},
            CoreLabel.METRIC,
            {"metric_key": metric_key},
            prov,
        )

    def link_metric_to_entity(
        self, metric_key: str, entity_uid: str, prov: EdgeProvenance
    ) -> None:
        self._edge(
            RelType.APPLIES_TO,
            CoreLabel.METRIC,
            {"metric_key": metric_key},
            CoreLabel.ENTITY,
            {"uid": entity_uid},
            prov,
        )

    def link_metric_to_document(
        self, metric_key: str, uri: str, prov: EdgeProvenance
    ) -> None:
        self._edge(
            RelType.DEFINED_IN,
            CoreLabel.METRIC,
            {"metric_key": metric_key},
            CoreLabel.DOCUMENT,
            {"uri": uri},
            prov,
        )

    def link_metric_to_benchmark(
        self, metric_key: str, benchmark_key: str, prov: EdgeProvenance
    ) -> None:
        self._edge(
            RelType.BENCHMARKED_AGAINST,
            CoreLabel.METRIC,
            {"metric_key": metric_key},
            CoreLabel.BENCHMARK,
            {"benchmark_key": benchmark_key},
            prov,
        )

    def link_metric_computed_from(
        self, metric_key: str, source_metric_key: str, prov: EdgeProvenance
    ) -> None:
        self._edge(
            RelType.COMPUTED_FROM,
            CoreLabel.METRIC,
            {"metric_key": metric_key},
            CoreLabel.METRIC,
            {"metric_key": source_metric_key},
            prov,
        )

    def link_document_to_entity(
        self, uri: str, entity_uid: str, prov: EdgeProvenance
    ) -> None:
        self._edge(
            RelType.DESCRIBES,
            CoreLabel.DOCUMENT,
            {"uri": uri},
            CoreLabel.ENTITY,
            {"uid": entity_uid},
            prov,
        )

    def link_party_to_entity(
        self, party_uid: str, entity_uid: str, role: str, prov: EdgeProvenance
    ) -> None:
        # role is part of edge identity so one party can hold several roles.
        self._edge(
            RelType.HAS_ROLE,
            CoreLabel.PARTY,
            {"uid": party_uid},
            CoreLabel.ENTITY,
            {"uid": entity_uid},
            prov,
            key_props={"role": role},
        )

    def relate_entities(
        self,
        subject_uid: str,
        object_uid: str,
        role: str,
        prov: EdgeProvenance,
        rel_type: str = RelType.RELATED_TO.value,
    ) -> None:
        """Generic structural edge between two entities. RELATED_TO is always
        allowed; any other rel_type must be allow-listed by a loaded pack."""
        if rel_type != RelType.RELATED_TO.value and rel_type not in self._pack_edge_types:
            raise WriteValidationError(
                f"edge type {rel_type!r} is not allow-listed by any loaded pack"
            )
        self._edge(
            rel_type,
            CoreLabel.ENTITY,
            {"uid": subject_uid},
            CoreLabel.ENTITY,
            {"uid": object_uid},
            prov,
            key_props={"role": role},
        )

    # -- metric aliases (resolver tier-1 index + write-back) --------------- #

    def metric_aliases(self) -> dict[str, str]:
        """Return a case-folded {alias -> metric_key} index over all metrics.
        This is the resolver's tier-1 exact-match table, read from the graph so
        pack-seeded and write-back-learned aliases are treated identically."""
        index: dict[str, str] = {}
        for m in self._store.nodes_by_label(CoreLabel.METRIC.value):
            for alias in m.get("aliases", ()) or ():
                index[str(alias).casefold()] = m["metric_key"]
        return index

    def metric_terms(self) -> dict[str, list[str]]:
        """Return {metric_key -> matchable terms}: each metric's aliases plus the
        local (post-namespace) part of its key. Feeds the tier-2 suggester."""
        out: dict[str, list[str]] = {}
        for m in self._store.nodes_by_label(CoreLabel.METRIC.value):
            terms = {str(a).casefold() for a in (m.get("aliases") or ())}
            terms.add(m["metric_key"].split(".", 1)[-1].casefold())
            out[m["metric_key"]] = sorted(terms)
        return out

    def add_metric_alias(self, metric_key: str, alias: str) -> None:
        """Write-back: teach a metric a new column-name alias so future columns
        with that name auto-link at tier-1. Idempotent (unions into the set)."""
        node = self._store.get_node(CoreLabel.METRIC.value, {"metric_key": metric_key})
        current = list(node.get("aliases", []) if node else [])
        if alias not in current:
            current.append(alias)
        self._store.upsert_node(
            CoreLabel.METRIC.value, {"metric_key": metric_key}, {"aliases": current}
        )

    # -- read path --------------------------------------------------------- #

    def resolve_column(
        self, system: str, table: str, name: str
    ) -> dict[str, object] | None:
        """Read path for the resolver and callers: given a column's identity,
        return the column and the metrics it MEASURES, each with the entities the
        metric APPLIES_TO. Returns None if the column is not in the graph."""
        col_key = {"system": system, "table": table, "name": name}
        col = self._store.get_node(CoreLabel.COLUMN.value, col_key)
        if col is None:
            return None
        metrics: list[dict[str, object]] = []
        for metric, _edge in self._store.out_neighbors(
            CoreLabel.COLUMN.value, col_key, RelType.MEASURES.value
        ):
            entities = [
                ent
                for ent, _e in self._store.out_neighbors(
                    CoreLabel.METRIC.value,
                    {"metric_key": metric["metric_key"]},
                    RelType.APPLIES_TO.value,
                )
            ]
            metrics.append({"metric": metric, "applies_to": entities})
        return {"column": col, "metrics": metrics}
