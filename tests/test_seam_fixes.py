"""Coverage for the foundation capabilities added to close downstream seams:
metric-attribute passthrough, pack namespace decoupling, IR-expressed specialized
edges, document DESCRIBES/DEFINED_IN links, the DOCUMENTED resolver tier, and
run_ingest bundle retention."""

import pytest

from graph import EdgeProvenance, GraphClient, InMemoryGraphStore, WriteValidationError
from ingestion import (
    InMemoryCheckpointer,
    ObservedColumn,
    ObservedDocument,
    ObservedEntity,
    ObservedRelation,
    ParsedBundle,
    Provenance,
    TokenBucket,
    run_ingest,
)
from ingestion.pipeline import load_bundle
from ingestion.connectors.synthetic import SyntheticSource, widgets_fixture
from packs import load_pack, pack_from_dict
from resolver import Resolver, Tier


def _client() -> GraphClient:
    c = GraphClient(InMemoryGraphStore())
    c.init_schema()
    return c


def _prov() -> Provenance:
    return Provenance("s", "2026-07-06", "v")


# -- seams 1 + 2: metric attributes + namespace ----------------------------- #

def test_pack_namespace_decoupled_from_name():
    c = _client()
    pack = pack_from_dict({
        "name": "my_display_name",
        "namespace": "mp",
        "metrics": [{"metric_key": "mp.thing", "unit": "u"}],
    })
    load_pack(c, pack)  # validates mp.* against namespace "mp", not the name
    assert c._store.get_node("Metric", {"metric_key": "mp.thing"}) is not None


def test_metric_key_outside_namespace_rejected():
    with pytest.raises(ValueError):
        pack_from_dict({
            "name": "mp", "metrics": [{"metric_key": "other.x"}]
        }).validate()


def test_arbitrary_metric_attributes_passthrough():
    c = _client()
    load_pack(c, pack_from_dict({
        "name": "mp",
        "metrics": [{"metric_key": "mp.x", "unit": "u",
                     "display_name": "The X", "annualization": "annual"}],
    }))
    node = c._store.get_node("Metric", {"metric_key": "mp.x"})
    assert node["display_name"] == "The X"
    assert node["annualization"] == "annual"


# -- seam 3: IR-expressed specialized edge type ----------------------------- #

def test_ir_relation_creates_pack_specialized_edge():
    c = _client()
    load_pack(c, pack_from_dict({
        "name": "mp", "entity_subtypes": ["Thing"], "edge_types": ["CONTAINS"],
    }))
    bundle = ParsedBundle(
        provenance=_prov(),
        entities=(ObservedEntity("a", ("Thing",)), ObservedEntity("b", ("Thing",))),
        relations=(ObservedRelation("a", "part", "b", rel_type="CONTAINS"),),
    )
    load_bundle(c, Resolver(c), bundle)
    assert c._store.out_neighbors("Entity", {"uid": "a"}, "CONTAINS")


def test_ir_relation_unlisted_edge_type_rejected():
    c = _client()
    load_pack(c, pack_from_dict({"name": "mp", "entity_subtypes": ["Thing"]}))
    bundle = ParsedBundle(
        provenance=_prov(),
        entities=(ObservedEntity("a", ("Thing",)), ObservedEntity("b", ("Thing",))),
        relations=(ObservedRelation("a", "part", "b", rel_type="NOT_ALLOWED"),),
    )
    with pytest.raises(WriteValidationError):
        load_bundle(c, Resolver(c), bundle)


# -- seam 4: document DESCRIBES / DEFINED_IN from the IR --------------------- #

def test_document_describes_and_defines_edges():
    c = _client()
    load_pack(c, pack_from_dict({
        "name": "mp", "entity_subtypes": ["Thing"],
        "metrics": [{"metric_key": "mp.x", "unit": "u"}],
    }))
    bundle = ParsedBundle(
        provenance=_prov(),
        entities=(ObservedEntity("e1", ("Thing",)),),
        documents=(ObservedDocument("doc://1", describes=("e1",), defines=("mp.x",)),),
    )
    load_bundle(c, Resolver(c), bundle)
    assert c._store.out_neighbors("Document", {"uri": "doc://1"}, "DESCRIBES")
    assert c._store.out_neighbors("Metric", {"metric_key": "mp.x"}, "DEFINED_IN")


# -- seam 6: resolver honors has_dictionary --------------------------------- #

def test_documented_column_short_circuits_the_funnel():
    c = _client()
    load_pack(c, pack_from_dict({"name": "mp", "metrics": [{"metric_key": "mp.x"}]}))
    r = Resolver(c)
    documented = r.resolve(ObservedColumn("s", "t", "no_alias_here", has_dictionary=True))
    assert documented.tier is Tier.DOCUMENTED
    assert len(r.queue) == 0  # not escalated
    undocumented = r.resolve(ObservedColumn("s", "t", "no_alias_here"))
    assert undocumented.tier is Tier.ESCALATED


# -- seam 5: run_ingest retains parsed bundles ------------------------------ #

def test_run_ingest_retains_bundles():
    c = _client()
    load_pack(c, pack_from_dict({"name": "widgets", "entity_subtypes": ["Widget"]}))
    source = SyntheticSource(widgets_fixture(), TokenBucket(rate=100),
                             clock=lambda: "2026-07-06T00:00:00+00:00")
    report = run_ingest(source, c, Resolver(c), InMemoryCheckpointer())
    assert report.bundles
    assert all(isinstance(b, ParsedBundle) for b in report.bundles)
