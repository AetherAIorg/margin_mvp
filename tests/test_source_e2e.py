"""The Source contract end to end via the synthetic connector:
discover -> fetch -> parse -> IR -> resolve -> load, plus idempotency and
crash-resume through the checkpointer."""

from graph import GraphClient, InMemoryGraphStore
from ingestion import InMemoryCheckpointer, TokenBucket, run_ingest
from ingestion.connectors.synthetic import SyntheticSource, widgets_fixture
from packs import WIDGETS_PACK_PATH, load_pack_file
from resolver import Resolver, Tier


class ManualClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def _setup():
    client = GraphClient(InMemoryGraphStore())
    client.init_schema()
    load_pack_file(client, WIDGETS_PACK_PATH)
    resolver = Resolver(client)
    clk = ManualClock()
    bucket = TokenBucket(rate=100, capacity=100, clock=clk.now, sleep=clk.sleep)
    source = SyntheticSource(
        widgets_fixture(), bucket, clock=lambda: "2026-07-06T00:00:00+00:00"
    )
    return client, resolver, source


def test_full_path_ingests_and_resolves():
    client, resolver, source = _setup()
    report = run_ingest(source, client, resolver, InMemoryCheckpointer())

    assert report.items_ingested == 2  # one rows table + one prose doc
    # the three fixture columns hit each tier exactly once
    assert len(report.by_tier(Tier.AUTO_LINKED)) == 1
    assert len(report.by_tier(Tier.SUGGESTED)) == 1
    assert len(report.by_tier(Tier.ESCALATED)) == 1

    # the document landed
    assert client._store.get_node("Document", {"uri": "doc://parts/overview"})


def test_entity_owned_column_links_metric_applies_to_entity():
    client, resolver, source = _setup()
    run_ingest(source, client, resolver, InMemoryCheckpointer())
    res = client.resolve_column("warehouse", "parts", "weight")
    assert res is not None
    metric_keys = [m["metric"]["metric_key"] for m in res["metrics"]]
    assert metric_keys == ["widgets.weight"]
    # the owning entity (the dataset itself) is APPLIES_TO-linked
    applies = [e["uid"] for m in res["metrics"] for e in m["applies_to"]]
    assert applies == ["warehouse.parts"]


def test_reingest_is_idempotent():
    client, resolver, source = _setup()
    run_ingest(source, client, resolver, InMemoryCheckpointer())
    cols_before = len(client._store.nodes_by_label("Column"))
    ents_before = len(client._store.nodes_by_label("Entity"))
    # fresh checkpointer forces a real re-run; writes must converge, not dup
    run_ingest(source, client, resolver, InMemoryCheckpointer())
    assert len(client._store.nodes_by_label("Column")) == cols_before
    assert len(client._store.nodes_by_label("Entity")) == ents_before


def test_checkpointer_prevents_double_ingest_on_resume():
    client, resolver, source = _setup()
    cp = InMemoryCheckpointer()
    run_ingest(source, client, resolver, cp)
    # same checkpointer -> everything already seen -> nothing re-ingested
    report2 = run_ingest(source, client, resolver, cp)
    assert report2.items_ingested == 0
    assert report2.items_skipped == 2


def test_source_satisfies_protocol():
    from ingestion import Source

    _, _, source = _setup()
    assert isinstance(source, Source)
