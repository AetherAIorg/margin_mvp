"""The ingestion pipeline: the generic driver over any Source.

It knows nothing about any specific connector. It orchestrates the contract:

    discover -> (skip if already done) -> fetch -> parse -> IR
             -> load IR into the graph -> resolve columns to metrics

Discovery is made crash-safe by the checkpointer: an item already marked done is
skipped, so re-running after a crash never double-ingests. Loading is idempotent
regardless because every graph write is an upsert.

`load_bundle` is where the IR meets the graph. It is deliberately the only place
that translates observed records into node/edge writes, so the mapping lives in
one auditable spot. Entity-owned columns are handled here too: when a resolved
column belongs to an entity that carries it, the metric is linked APPLIES_TO
that entity, making "a reference entity with its own feed" a first-class path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from graph.client import GraphClient
from graph.model import EdgeProvenance, RelType
from resolver.funnel import Resolution, Resolver, Tier

from .checkpoint import Checkpointer, InMemoryCheckpointer
from .ir import ObservedColumn, ParsedBundle
from .source import Source


@dataclass(slots=True)
class IngestReport:
    items_ingested: int = 0
    items_skipped: int = 0
    resolutions: list[Resolution] = field(default_factory=list)
    bundles: list[ParsedBundle] = field(default_factory=list)
    """The parsed IR bundles, retained so a caller can perform post-load graph
    enrichment that needs the IR (edges the loader did not create, audits, etc.)."""

    def by_tier(self, tier: Tier) -> list[Resolution]:
        return [r for r in self.resolutions if r.tier is tier]


def _column_key(c: ObservedColumn) -> tuple[str, str, str]:
    return (c.system, c.table, c.name)


def load_bundle(
    client: GraphClient, resolver: Resolver, bundle: ParsedBundle
) -> list[Resolution]:
    """Write one IR bundle into the graph and resolve its columns. Idempotent.

    Returns the resolution outcome per column so the caller can act on tier-2
    suggestions and tier-3 escalations."""
    p = bundle.provenance
    prov = EdgeProvenance(
        source_ref=p.source_ref, as_of=p.fetched_at, created_by=p.connector_version
    )

    for doc in bundle.documents:
        client.upsert_document(doc.uri, title=doc.title, text=doc.text, as_of=doc.as_of)
        for entity_uid in doc.describes:
            client.link_document_to_entity(doc.uri, entity_uid, prov)
        for metric_key in doc.defines:
            client.link_metric_to_document(metric_key, doc.uri, prov)

    for col in bundle.columns:
        client.upsert_column(
            col.system, col.table, col.name, col.dtype, col.sample_values,
            col.has_dictionary,
        )

    # Track which columns an entity owns so resolved metrics can be linked
    # APPLIES_TO that entity.
    owner_of: dict[tuple[str, str, str], str] = {}
    for ent in bundle.entities:
        subtype = _pick_subtype(client, ent.candidate_labels)
        client.upsert_entity(ent.uid, subtype_label=subtype, attributes=ent.attributes)
        for col in ent.columns:
            client.upsert_column(
                col.system, col.table, col.name, col.dtype, col.sample_values,
                col.has_dictionary,
            )
            owner_of[_column_key(col)] = ent.uid

    for rel in bundle.relations:
        client.relate_entities(
            rel.subject_uid, rel.object_uid, rel.role, prov,
            rel_type=rel.rel_type or RelType.RELATED_TO.value,
        )

    resolutions: list[Resolution] = []
    for col in bundle.iter_columns():
        outcome = resolver.resolve(col)
        resolutions.append(outcome)
        if outcome.tier is Tier.AUTO_LINKED and outcome.metric_key:
            client.link_column_to_metric(
                col.system, col.table, col.name, outcome.metric_key, prov
            )
            owner = owner_of.get(_column_key(col))
            if owner is not None:
                client.link_metric_to_entity(outcome.metric_key, owner, prov)
    return resolutions


def _pick_subtype(
    client: GraphClient, candidate_labels: tuple[str, ...]
) -> str | None:
    """Choose the entity's pack subtype label: the first candidate the loaded
    packs allow-list. Unknown candidates are ignored (the base :Entity always
    applies), keeping ingestion resilient to a source proposing labels no pack
    knows yet."""
    allowed = client.allowed_entity_subtypes
    for label in candidate_labels:
        if label in allowed:
            return label
    return None


def run_ingest(
    source: Source,
    client: GraphClient,
    resolver: Resolver,
    checkpointer: Checkpointer | None = None,
) -> IngestReport:
    """Drive one Source end to end. Idempotent and crash-safe via the ledger."""
    checkpointer = checkpointer or InMemoryCheckpointer()
    report = IngestReport()
    for item in source.discover():
        if checkpointer.has_seen(item.source_ref, item.item_id):
            report.items_skipped += 1
            continue
        artifact = source.fetch(item)          # routes through the rate limiter
        bundle = source.parse(artifact)        # -> IR
        report.bundles.append(bundle)
        report.resolutions.extend(load_bundle(client, resolver, bundle))
        checkpointer.mark_done(item.source_ref, item.item_id)
        report.items_ingested += 1
    return report
