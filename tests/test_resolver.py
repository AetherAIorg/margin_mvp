"""The three-tier resolver funnel and its write-back loop."""

import pytest

from graph import EdgeProvenance, GraphClient, InMemoryGraphStore
from ingestion.ir import ObservedColumn
from packs import WIDGETS_PACK_PATH, load_pack_file
from resolver import EmbeddingSuggester, Resolver, Tier


def _client() -> GraphClient:
    c = GraphClient(InMemoryGraphStore())
    c.init_schema()
    load_pack_file(c, WIDGETS_PACK_PATH)
    return c


def _col(name: str) -> ObservedColumn:
    return ObservedColumn(system="sys", table="t", name=name)


def test_tier1_exact_alias_auto_links():
    r = Resolver(_client())
    out = r.resolve(_col("weight"))  # exact alias in the widgets pack
    assert out.tier is Tier.AUTO_LINKED
    assert out.metric_key == "widgets.weight"
    assert out.score == 1.0


def test_tier2_fuzzy_suggests_with_alternatives():
    r = Resolver(_client())
    out = r.resolve(_col("lenght"))  # typo near "length"
    assert out.tier is Tier.SUGGESTED
    assert out.metric_key == "widgets.length"
    assert 0.0 < out.score < 1.0
    assert out.alternatives  # top-k present for human confirmation


def test_tier3_escalates_and_queues():
    r = Resolver(_client())
    out = r.resolve(_col("xyzzy"))
    assert out.tier is Tier.ESCALATED
    assert out.metric_key is None
    assert len(r.queue) == 1
    assert r.queue.pending()[0].column.name == "xyzzy"


def test_confirm_writes_back_and_decays_to_tier1():
    c = _client()
    r = Resolver(c)
    col = _col("lenght")
    assert r.resolve(col).tier is Tier.SUGGESTED
    r.confirm(col, "widgets.length", EdgeProvenance("s", "2026-07-06", "human"))
    # the MEASURES edge exists...
    assert c._store.out_neighbors(
        "Column", {"system": "sys", "table": "t", "name": "lenght"}, "MEASURES"
    )
    # ...and the next same-named column now resolves at tier 1
    assert r.resolve(_col("lenght")).tier is Tier.AUTO_LINKED


def test_threshold_controls_tier2_vs_tier3():
    # A very high threshold pushes a fuzzy match down to escalation.
    r = Resolver(_client(), threshold=0.99)
    assert r.resolve(_col("lenght")).tier is Tier.ESCALATED


def test_embedding_suggester_is_a_stub_behind_the_interface():
    r = Resolver(_client(), suggester=EmbeddingSuggester())
    # tier 1 still works (no suggester needed)...
    assert r.resolve(_col("weight")).tier is Tier.AUTO_LINKED
    # ...but reaching the suggester raises NotImplementedError, proving the seam.
    with pytest.raises(NotImplementedError):
        r.resolve(_col("lenght"))
