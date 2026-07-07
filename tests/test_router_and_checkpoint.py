"""Parser router dispatch + schema_version guard, and the checkpoint ledger."""

import pytest

from ingestion import InMemoryCheckpointer, ParserRouter
from ingestion.ir import (
    IR_SCHEMA_VERSION,
    ObservedDocument,
    ParsedBundle,
    Provenance,
)
from ingestion.source import RawArtifact


def _artifact(artifact_type: str) -> RawArtifact:
    return RawArtifact("id", "s", artifact_type, payload=None, fetched_at="2026-07-06")


def _prov() -> Provenance:
    return Provenance("s", "2026-07-06", "v")


def test_router_dispatches_by_type():
    router = ParserRouter()
    router.register(
        "prose",
        lambda a: ParsedBundle(_prov(), documents=(ObservedDocument("u", text="x"),)),
    )
    bundle = router.parse(_artifact("prose"))
    assert bundle.documents[0].uri == "u"


def test_router_unknown_type_raises():
    router = ParserRouter()
    with pytest.raises(KeyError):
        router.parse(_artifact("rows"))


def test_router_duplicate_registration_raises():
    router = ParserRouter()
    router.register("rows", lambda a: ParsedBundle(_prov()))
    with pytest.raises(ValueError):
        router.register("rows", lambda a: ParsedBundle(_prov()))


def test_router_rejects_unversioned_record():
    router = ParserRouter()
    bad_doc = ObservedDocument("u", schema_version="0.0-wrong")
    router.register("prose", lambda a: ParsedBundle(_prov(), documents=(bad_doc,)))
    with pytest.raises(ValueError):
        router.parse(_artifact("prose"))


def test_records_carry_current_schema_version():
    assert ObservedDocument("u").schema_version == IR_SCHEMA_VERSION


def test_checkpointer_marks_and_reports():
    cp = InMemoryCheckpointer()
    assert cp.has_seen("src", "item1") is False
    cp.mark_done("src", "item1")
    assert cp.has_seen("src", "item1") is True


def test_checkpointer_namespaces_by_source():
    cp = InMemoryCheckpointer()
    cp.mark_done("srcA", "item1")
    assert cp.has_seen("srcB", "item1") is False  # same id, different source


def test_checkpointer_mark_done_idempotent():
    cp = InMemoryCheckpointer()
    cp.mark_done("src", "item1")
    cp.mark_done("src", "item1")
    assert cp.has_seen("src", "item1") is True
