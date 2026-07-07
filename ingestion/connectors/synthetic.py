"""A synthetic, NEUTRAL reference connector.

Its only job is to prove the Source contract end to end with zero network and no
domain specifics. It stands in for the two shapes real connectors take:

  - a REST/columnar API (rows), via `InMemoryRestStub` serving canned responses
    from memory, and
  - a document store (prose).

It implements the three-method `Source` contract, routes fetch through the
injected rate limiter (the single choke point), and dispatches parse through a
`ParserRouter` with one parser per artifact type. The rows parser emits an
ObservedEntity that OWNS its columns, exercising the "entity that is itself a
measured feed" case.

This is a fixture, not a template for a real integration beyond the shape. To
add a genuine source, implement `Source` the same way over live I/O. Do not add
any domain vocabulary here; "widget"/"part" are neutral placeholders.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from ..ir import (
    ObservedColumn,
    ObservedDocument,
    ObservedEntity,
    ParsedBundle,
    Provenance,
)
from ..ratelimit import RateLimiter
from ..router import ParserRouter
from ..source import RawArtifact, WorkItem


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryRestStub:
    """Stands in for a real REST/columnar API. Serves canned responses from
    memory so the connector's fetch path runs with no network. Real connectors
    talk to a live endpoint here instead."""

    def __init__(
        self,
        tables: dict[tuple[str, str], list[dict[str, object]]],
        documents: dict[str, dict[str, object]],
    ) -> None:
        self._tables = tables
        self._documents = documents

    def list_tables(self) -> list[tuple[str, str]]:
        return list(self._tables)

    def list_documents(self) -> list[str]:
        return list(self._documents)

    def get_rows(self, system: str, table: str) -> list[dict[str, object]]:
        return self._tables[(system, table)]

    def get_document(self, uri: str) -> dict[str, object]:
        return self._documents[uri]


class SyntheticSource:
    """Reference `Source` implementation over `InMemoryRestStub` fixtures."""

    connector_version = "synthetic@0.1.0"

    def __init__(
        self,
        api: InMemoryRestStub,
        rate_limiter: RateLimiter,
        source_ref: str = "synthetic://fixtures",
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._api = api
        self._rate = rate_limiter
        self._source_ref = source_ref
        self._clock = clock
        self._router = ParserRouter()
        self._router.register("rows", self._parse_rows)
        self._router.register("prose", self._parse_prose)

    # -- Source contract --------------------------------------------------- #

    def discover(self) -> Iterable[WorkItem]:
        for system, table in self._api.list_tables():
            yield WorkItem(
                item_id=f"rows:{system}.{table}",
                source_ref=self._source_ref,
                artifact_type="rows",
                metadata={"system": system, "table": table},
            )
        for uri in self._api.list_documents():
            yield WorkItem(
                item_id=f"prose:{uri}",
                source_ref=self._source_ref,
                artifact_type="prose",
                metadata={"uri": uri},
            )

    def fetch(self, item: WorkItem) -> RawArtifact:
        # The single rate-limited choke point. Every fetch, every connector.
        self._rate.acquire()
        if item.artifact_type == "rows":
            payload: object = self._api.get_rows(
                str(item.metadata["system"]), str(item.metadata["table"])
            )
        else:
            payload = self._api.get_document(str(item.metadata["uri"]))
        return RawArtifact(
            item_id=item.item_id,
            source_ref=self._source_ref,
            artifact_type=item.artifact_type,
            payload=payload,
            fetched_at=self._clock(),
        )

    def parse(self, artifact: RawArtifact) -> ParsedBundle:
        return self._router.parse(artifact)

    # -- parsers (registered on the router) -------------------------------- #

    def _provenance(self, fetched_at: str) -> Provenance:
        return Provenance(
            source_ref=self._source_ref,
            fetched_at=fetched_at,
            connector_version=self.connector_version,
        )

    def _parse_rows(self, artifact: RawArtifact) -> ParsedBundle:
        rows: list[dict[str, object]] = list(artifact.payload)  # type: ignore[arg-type]
        _, ref = artifact.item_id.split(":", 1)
        system, table = ref.split(".", 1)
        col_names = list(rows[0].keys()) if rows else []
        columns = tuple(
            ObservedColumn(
                system=system,
                table=table,
                name=name,
                dtype=_infer_dtype(rows, name),
                sample_values=tuple(
                    str(r[name]) for r in rows[:3] if r.get(name) is not None
                ),
                has_dictionary=False,  # dictionaries are missing by assumption
            )
            for name in col_names
        )
        # The dataset is itself a measured entity that owns its columns.
        entity = ObservedEntity(
            uid=f"{system}.{table}",
            candidate_labels=("Widget",),
            attributes={"system": system, "table": table},
            columns=columns,
        )
        return ParsedBundle(
            provenance=self._provenance(artifact.fetched_at),
            entities=(entity,),
        )

    def _parse_prose(self, artifact: RawArtifact) -> ParsedBundle:
        doc: dict[str, object] = artifact.payload  # type: ignore[assignment]
        _, uri = artifact.item_id.split(":", 1)
        observed = ObservedDocument(
            uri=uri,
            title=doc.get("title"),  # type: ignore[arg-type]
            text=str(doc.get("text", "")),
            as_of=doc.get("as_of"),  # type: ignore[arg-type]
        )
        return ParsedBundle(
            provenance=self._provenance(artifact.fetched_at),
            documents=(observed,),
        )


def _infer_dtype(rows: list[dict[str, object]], name: str) -> str | None:
    for r in rows:
        v = r.get(name)
        if v is not None:
            return type(v).__name__
    return None


def widgets_fixture() -> InMemoryRestStub:
    """Neutral fixture that exercises all three resolver tiers:
      weight -> tier 1 (exact alias in the widgets pack)
      lenght -> tier 2 (fuzzy near "length", needs confirmation)
      xyzzy  -> tier 3 (no confident match, escalated)
    """
    tables = {
        ("warehouse", "parts"): [
            {"weight": 12, "lenght": 40, "xyzzy": "a"},
            {"weight": 15, "lenght": 55, "xyzzy": "b"},
        ]
    }
    documents = {
        "doc://parts/overview": {
            "title": "Parts overview",
            "text": "Neutral prose describing the parts dataset.",
            "as_of": "2026-07-06",
        }
    }
    return InMemoryRestStub(tables=tables, documents=documents)
