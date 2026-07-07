"""Optional integration test against a live Neo4j (docker compose up -d).

Skipped automatically when no database is reachable, so the default offline
suite is unaffected. When a DB is present it proves the real Cypher path:
constraints (including the Enterprise-only NODE KEY on Column), the multi-label
pattern, idempotent MERGE, edge provenance, and the resolve_column read path.
"""

import os

import pytest

from graph import GraphClient
from ingestion import InMemoryCheckpointer, TokenBucket, run_ingest
from ingestion.connectors.synthetic import SyntheticSource, widgets_fixture
from packs import WIDGETS_PACK_PATH, load_pack_file
from resolver import Resolver, Tier

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH = (
    os.environ.get("NEO4J_USER", "neo4j"),
    os.environ.get("NEO4J_PASSWORD", "password"),
)


@pytest.fixture()
def store():
    from graph import Neo4jGraphStore

    try:
        s = Neo4jGraphStore(NEO4J_URI, NEO4J_AUTH)
        with s._driver.session(database=s._database) as sess:
            sess.run("RETURN 1").single()
    except Exception as exc:  # noqa: BLE001 - any connectivity failure -> skip
        pytest.skip(f"no live Neo4j at {NEO4J_URI}: {exc}")
    with s._driver.session(database=s._database) as sess:
        sess.run("MATCH (n) DETACH DELETE n")
    yield s
    s.close()


def test_neo4j_full_path(store):
    client = GraphClient(store)
    client.init_schema()  # includes the NODE KEY constraint (Enterprise feature)
    load_pack_file(client, WIDGETS_PACK_PATH)
    resolver = Resolver(client)
    source = SyntheticSource(
        widgets_fixture(), TokenBucket(rate=100),
        clock=lambda: "2026-07-06T00:00:00+00:00",
    )

    report = run_ingest(source, client, resolver, InMemoryCheckpointer())
    assert report.items_ingested == 2
    assert len(report.by_tier(Tier.AUTO_LINKED)) == 1

    # multi-label persisted
    node = store.get_node("Entity", {"uid": "warehouse.parts"})
    assert node["_labels"] == {"Entity", "Widget"}

    # read path through real Cypher
    res = client.resolve_column("warehouse", "parts", "weight")
    assert [m["metric"]["metric_key"] for m in res["metrics"]] == ["widgets.weight"]
    assert [e["uid"] for m in res["metrics"] for e in m["applies_to"]] == [
        "warehouse.parts"
    ]

    # idempotent against real MERGE
    before = len(store.nodes_by_label("Column"))
    run_ingest(source, client, resolver, InMemoryCheckpointer())
    assert len(store.nodes_by_label("Column")) == before
