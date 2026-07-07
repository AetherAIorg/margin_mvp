"""Idempotent-discovery ledger: which work items are already ingested.

Discovery is keyed on a stable `item_id`, so a crash mid-run never
double-ingests: on restart, discovery re-surfaces the same ids and the pipeline
skips any the ledger has marked done.

`Checkpointer` is the pluggable seam (the design decision was to keep this an
interface, not hardcode a store). `InMemoryCheckpointer` is the default for
tests and single-process runs; a graph- or Redis-backed implementation drops in
later with no pipeline change. Items are namespaced by `source_ref` so ids from
different sources cannot collide.
"""

from __future__ import annotations

from typing import Protocol


class Checkpointer(Protocol):
    def has_seen(self, source_ref: str, item_id: str) -> bool:
        """True if (source_ref, item_id) was already marked done."""
        ...

    def mark_done(self, source_ref: str, item_id: str) -> None:
        """Record that (source_ref, item_id) finished ingesting. Idempotent."""
        ...


class InMemoryCheckpointer:
    """Set-backed ledger. Process-local; resets on restart. Fine for tests and
    single runs, replaceable by a durable impl for real crash/resume."""

    def __init__(self) -> None:
        self._done: set[tuple[str, str]] = set()

    def has_seen(self, source_ref: str, item_id: str) -> bool:
        return (source_ref, item_id) in self._done

    def mark_done(self, source_ref: str, item_id: str) -> None:
        self._done.add((source_ref, item_id))
