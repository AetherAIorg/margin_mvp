"""Candidate suggesters for resolver tier 2.

A suggester scores how well an observed column matches each known metric, given
the metric's terms (its aliases plus the local part of its metric_key). The
resolver uses the ranked output to propose a top match plus alternatives for a
human to confirm.

`Suggester` is the seam. `StringSimilaritySuggester` is the simple default
(difflib ratio, no dependencies, deterministic). `EmbeddingSuggester` is a
deliberate stub: the interface is fixed now so an embedding-based nearest-metric
implementation drops in later without touching the funnel, but it is NOT
implemented in this foundation.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from ingestion.ir import ObservedColumn


@dataclass(frozen=True, slots=True)
class Suggestion:
    metric_key: str
    score: float  # 0.0 to 1.0, higher is a better match


class Suggester(Protocol):
    def suggest(
        self, column: ObservedColumn, terms_by_metric: dict[str, list[str]]
    ) -> list[Suggestion]:
        """Return suggestions sorted by descending score. May be empty."""
        ...


class StringSimilaritySuggester:
    """Scores a column against each metric by the best fuzzy match between the
    column name and any of the metric's terms. Dependency-free and deterministic
    so tests are stable."""

    def suggest(
        self, column: ObservedColumn, terms_by_metric: dict[str, list[str]]
    ) -> list[Suggestion]:
        name = column.name.casefold()
        out: list[Suggestion] = []
        for metric_key, terms in terms_by_metric.items():
            best = max(
                (SequenceMatcher(None, name, t.casefold()).ratio() for t in terms),
                default=0.0,
            )
            if best > 0.0:
                out.append(Suggestion(metric_key, round(best, 4)))
        # Sort by score desc, then metric_key for a stable, deterministic order.
        out.sort(key=lambda s: (-s.score, s.metric_key))
        return out


class EmbeddingSuggester:
    """Stub. The nearest-metric-by-embedding strategy lives behind this exact
    interface but is intentionally not built in the foundation. Swapping it in
    later is a one-line change at the resolver construction site."""

    def suggest(
        self, column: ObservedColumn, terms_by_metric: dict[str, list[str]]
    ) -> list[Suggestion]:
        raise NotImplementedError(
            "EmbeddingSuggester is a stubbed strategy seam; wire in an embedding "
            "backend here without changing the resolver funnel"
        )
