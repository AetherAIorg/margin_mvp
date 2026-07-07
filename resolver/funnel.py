"""The three-tier resolver funnel.

Dictionaries are missing by assumption, so an observed column's meaning must be
resolved to a canonical Metric. Every column enters the funnel and exits at
exactly one tier:

  Tier 1  AUTO_LINKED : the column name matches a known pack rule (a metric
                        alias). Auto-link, no human needed.
  Tier 2  SUGGESTED   : no exact rule, but a suggester proposes a match at or
                        above the confidence threshold. Emit the top candidate
                        plus alternatives for a human to confirm.
  Tier 3  ESCALATED   : nothing confident enough. Queue for a human to define a
                        new Metric.

When a human confirms a tier-2 or tier-3 outcome, `confirm` writes the MEASURES
edge AND writes the mapping back as a new pack rule (a metric alias in the
graph). So the next column with that name resolves at tier 1, and tier-2 volume
decays over time. That write-back loop is the point of the funnel.

The funnel decides; it does not itself walk the source. The pipeline feeds it
columns and acts on the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from graph.client import GraphClient
from graph.model import EdgeProvenance
from ingestion.ir import ObservedColumn

from .suggest import StringSimilaritySuggester, Suggester, Suggestion


class Tier(str, Enum):
    AUTO_LINKED = "AUTO_LINKED"  # tier 1
    SUGGESTED = "SUGGESTED"      # tier 2
    ESCALATED = "ESCALATED"      # tier 3
    DOCUMENTED = "DOCUMENTED"    # tier 0: source ships a dictionary, no guess needed


@dataclass(frozen=True, slots=True)
class Resolution:
    column: ObservedColumn
    tier: Tier
    metric_key: str | None = None
    """The auto-linked (tier 1) or top-suggested (tier 2) metric. None at tier 3."""

    score: float = 0.0
    alternatives: tuple[Suggestion, ...] = ()
    """Top-k ranked candidates at tier 2 for a human to choose among."""


class EscalationQueue:
    """Where tier-3 columns wait for a human to define a new Metric. In-memory
    for the foundation; a durable queue drops in behind the same shape."""

    def __init__(self) -> None:
        self._items: list[Resolution] = []

    def enqueue(self, resolution: Resolution) -> None:
        self._items.append(resolution)

    def pending(self) -> tuple[Resolution, ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)


class Resolver:
    def __init__(
        self,
        client: GraphClient,
        suggester: Suggester | None = None,
        threshold: float = 0.6,
        top_k: int = 3,
        queue: EscalationQueue | None = None,
    ) -> None:
        self._client = client
        self._suggester = suggester or StringSimilaritySuggester()
        self._threshold = threshold
        self._top_k = top_k
        self.queue = queue or EscalationQueue()

    def resolve(self, column: ObservedColumn) -> Resolution:
        """Run one column through the funnel and return its outcome. Pure with
        respect to the graph: tier-1 links are performed by the caller (or
        `confirm`), tier-3 items are queued here for human attention."""
        # Tier 1: exact match against known pack rules (metric aliases).
        index = self._client.metric_aliases()
        hit = index.get(column.name.casefold())
        if hit is not None:
            return Resolution(column, Tier.AUTO_LINKED, metric_key=hit, score=1.0)

        # Tier 0: the source ships a data dictionary for this column. There is no
        # missing meaning to reconstruct, so do not guess (tier 2) or escalate as
        # a gap (tier 3). Mark it DOCUMENTED; a human may still map it, but it is
        # not funnel work.
        if column.has_dictionary:
            return Resolution(column, Tier.DOCUMENTED)

        # Tier 2: suggest candidates by similarity.
        terms = self._client.metric_terms()
        suggestions = self._suggester.suggest(column, terms)[: self._top_k]
        if suggestions and suggestions[0].score >= self._threshold:
            top = suggestions[0]
            return Resolution(
                column,
                Tier.SUGGESTED,
                metric_key=top.metric_key,
                score=top.score,
                alternatives=tuple(suggestions),
            )

        # Tier 3: escalate for a human to define a new metric.
        escalated = Resolution(
            column, Tier.ESCALATED, alternatives=tuple(suggestions)
        )
        self.queue.enqueue(escalated)
        return escalated

    def confirm(
        self,
        column: ObservedColumn,
        metric_key: str,
        prov: EdgeProvenance,
    ) -> None:
        """A human accepted `metric_key` for `column`. Link it AND write the
        mapping back as a pack rule so the next same-named column resolves at
        tier 1. This is the decay mechanism for tier-2 volume."""
        self._client.link_column_to_metric(
            column.system, column.table, column.name, metric_key, prov
        )
        self._client.add_metric_alias(metric_key, column.name.casefold())
