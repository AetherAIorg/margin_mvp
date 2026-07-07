"""The `Source` contract: the one interface every connector implements.

Downstream teams will point this at wildly different systems. The job of this
module is to define the smallest set of seams that lets all of them feed the
same IR (see `ir.py`) without the core knowing anything about any of them.

Three seams, each doing exactly one thing:

  discover() -> Iterable[WorkItem]
      Enumerate what exists to ingest. Cheap and idempotent. Each WorkItem
      carries a stable `item_id` so a crash/resume never double-ingests: the
      caller can record which ids are done and skip them on restart.

  fetch(item) -> RawArtifact
      Pull the bytes/rows for one item. This is the ONLY method that touches the
      network, and it is expected to route through a shared rate limiter so a
      hard per-IP limit on a public source cannot get the caller banned. The
      limiter is injected, not hardcoded to any provider.

  parse(artifact) -> ParsedBundle
      Normalize one raw artifact into the IR. A single source may emit several
      artifact kinds (structured rows vs prose); the recommended implementation
      dispatches by `RawArtifact.artifact_type` through a parser router so each
      kind has its own registered parser. The router lives alongside this
      contract; a connector may also parse inline if it only has one kind.

Why the split: discovery is cheap and drives resume; fetch is the rate-limited
I/O choke point; parse is pure and testable with no network. Keeping them
separate is what makes the whole pipeline resumable and unit-testable offline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .ir import ParsedBundle


@dataclass(frozen=True, slots=True)
class WorkItem:
    """One unit of ingestible work surfaced by discovery.

    `item_id` must be STABLE across runs for the same underlying thing. It is the
    idempotency key for crash/resume: the pipeline dedupes on it before ever
    calling fetch, so re-running discovery after a crash re-surfaces the same ids
    and already-done ones are skipped."""

    item_id: str
    source_ref: str
    """Origin identifier, echoed into provenance. Matches Provenance.source_ref."""

    artifact_type: str = "default"
    """Hint for the parser router so fetch/parse know which parser will handle
    this item (e.g. "rows", "prose"). Free-form; the router owns the vocabulary."""

    metadata: dict[str, object] = field(default_factory=dict)
    """Connector-private payload needed to fetch this item (a path, a query, a
    cursor). Opaque to the core; never reaches the graph."""


@dataclass(frozen=True, slots=True)
class RawArtifact:
    """The unparsed result of fetching one WorkItem.

    `payload` is intentionally `object`: it may be raw bytes, a list of row
    dicts, a decoded JSON structure, whatever the source produced. Only the
    connector's own parser interprets it. `artifact_type` selects that parser."""

    item_id: str
    source_ref: str
    artifact_type: str
    payload: object
    fetched_at: str
    """ISO-8601 fetch timestamp; flows into Provenance.fetched_at at parse time."""


@runtime_checkable
class Source(Protocol):
    """Every connector implements this and nothing more. To add a new source,
    implement these three methods and register the connector. See the README
    extension guide.

    Implementations should be constructed with their own config (endpoints,
    credentials, and the shared rate limiter for fetch). The Protocol covers the
    behavioral contract only; construction is the connector's business."""

    connector_version: str
    """Version string stamped into produced provenance (created_by on edges)."""

    def discover(self) -> Iterable[WorkItem]:
        """Enumerate work. Cheap, idempotent, no heavy I/O. Stable item ids."""
        ...

    def fetch(self, item: WorkItem) -> RawArtifact:
        """Pull one item's bytes/rows. The single rate-limited I/O choke point."""
        ...

    def parse(self, artifact: RawArtifact) -> ParsedBundle:
        """Normalize one artifact into the IR. Pure; no network; unit-testable."""
        ...
