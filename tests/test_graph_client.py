"""Layer 1: idempotent MERGE and the multi-label write invariant."""

import pytest

from graph import EdgeProvenance, GraphClient, InMemoryGraphStore, WriteValidationError
from packs import WIDGETS_PACK_PATH, load_pack_file


def _client() -> GraphClient:
    c = GraphClient(InMemoryGraphStore())
    c.init_schema()
    return c


def test_double_upsert_is_a_no_op():
    c = _client()
    c.upsert_metric("shared.count", unit="count")
    c.upsert_metric("shared.count", unit="count")  # re-ingest
    metrics = c._store.nodes_by_label("Metric")
    assert len(metrics) == 1
    assert metrics[0]["metric_key"] == "shared.count"


def test_double_edge_upsert_is_a_no_op():
    c = _client()
    prov = EdgeProvenance("s", "2026-07-06", "test")
    c.upsert_column("sys", "t", "c")
    c.upsert_metric("shared.count")
    c.link_column_to_metric("sys", "t", "c", "shared.count", prov)
    c.link_column_to_metric("sys", "t", "c", "shared.count", prov)
    neighbors = c._store.out_neighbors("Column", {"system": "sys", "table": "t", "name": "c"}, "MEASURES")
    assert len(neighbors) == 1


def test_reingest_updates_props_without_duplicating():
    c = _client()
    c.upsert_column("sys", "t", "c", dtype="int")
    c.upsert_column("sys", "t", "c", dtype="float")  # same identity, new prop
    cols = c._store.nodes_by_label("Column")
    assert len(cols) == 1
    assert cols[0]["dtype"] == "float"


def test_allowed_subtype_label_is_written():
    c = _client()
    load_pack_file(c, WIDGETS_PACK_PATH)
    c.upsert_entity("e1", subtype_label="Widget")
    node = c._store.get_node("Entity", {"uid": "e1"})
    assert node["_labels"] == {"Entity", "Widget"}


def test_unlisted_subtype_label_is_rejected():
    c = _client()
    load_pack_file(c, WIDGETS_PACK_PATH)
    with pytest.raises(WriteValidationError):
        c.upsert_entity("e2", subtype_label="NotAPackType")


def test_base_entity_always_has_entity_label():
    c = _client()
    c.upsert_entity("e3")  # no subtype, no pack needed
    node = c._store.get_node("Entity", {"uid": "e3"})
    assert node["_labels"] == {"Entity"}


def test_unlisted_pack_edge_type_is_rejected():
    c = _client()
    prov = EdgeProvenance("s", "2026-07-06", "test")
    c.upsert_entity("a")
    c.upsert_entity("b")
    # RELATED_TO always allowed
    c.relate_entities("a", "b", role="peer", prov=prov)
    # a non-allow-listed specialized edge type is rejected
    with pytest.raises(WriteValidationError):
        c.relate_entities("a", "b", role="child", prov=prov, rel_type="CONTAINS")


def test_pack_registers_edge_type_allowlist():
    c = _client()
    load_pack_file(c, WIDGETS_PACK_PATH)  # declares CONTAINS
    prov = EdgeProvenance("s", "2026-07-06", "test")
    c.upsert_entity("a")
    c.upsert_entity("b")
    c.relate_entities("a", "b", role="child", prov=prov, rel_type="CONTAINS")
    neighbors = c._store.out_neighbors("Entity", {"uid": "a"}, "CONTAINS")
    assert len(neighbors) == 1
