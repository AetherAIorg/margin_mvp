"""Parser router: dispatch raw artifacts to a registered parser by type.

A single source can emit several artifact kinds (structured rows, prose docs).
Rather than one giant parse method, a connector registers one parser per
artifact_type and lets the router dispatch. Each parser returns a ParsedBundle
(the IR), whose records already carry `schema_version`, so every parsed record
is versioned regardless of which parser produced it.

This keeps `Source.parse` trivial (delegate to the router) and makes adding a
new artifact kind a registration, not a rewrite.
"""

from __future__ import annotations

from collections.abc import Callable

from .ir import IR_SCHEMA_VERSION, ParsedBundle
from .source import RawArtifact

Parser = Callable[[RawArtifact], ParsedBundle]


class ParserRouter:
    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {}

    def register(self, artifact_type: str, parser: Parser) -> None:
        if artifact_type in self._parsers:
            raise ValueError(f"parser already registered for {artifact_type!r}")
        self._parsers[artifact_type] = parser

    def registered_types(self) -> frozenset[str]:
        return frozenset(self._parsers)

    def parse(self, artifact: RawArtifact) -> ParsedBundle:
        parser = self._parsers.get(artifact.artifact_type)
        if parser is None:
            raise KeyError(
                f"no parser registered for artifact_type {artifact.artifact_type!r}; "
                f"registered: {sorted(self._parsers)}"
            )
        bundle = parser(artifact)
        _assert_versioned(bundle)
        return bundle


def _assert_versioned(bundle: ParsedBundle) -> None:
    """Guard the invariant that every parsed record is stamped with a schema
    version the consumer understands. Cheap, and it catches a parser that
    hand-builds records and forgets the stamp."""
    records = (
        *bundle.columns,
        *bundle.documents,
        *bundle.entities,
        *bundle.relations,
        *(c for e in bundle.entities for c in e.columns),
    )
    for r in records:
        version = getattr(r, "schema_version", None)
        if version != IR_SCHEMA_VERSION:
            raise ValueError(
                f"record {type(r).__name__} has schema_version {version!r}, "
                f"expected {IR_SCHEMA_VERSION!r}"
            )
