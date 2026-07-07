"""The resolver: the bridge that maps observed columns to canonical Metrics.

Belongs to neither layer. A three-tier funnel (exact -> suggest -> escalate)
with write-back so confirmed mappings become pack rules and tier-2 volume decays.
"""

from .funnel import EscalationQueue, Resolution, Resolver, Tier
from .suggest import (
    EmbeddingSuggester,
    StringSimilaritySuggester,
    Suggester,
    Suggestion,
)

__all__ = [
    "EscalationQueue",
    "Resolution",
    "Resolver",
    "Tier",
    "EmbeddingSuggester",
    "StringSimilaritySuggester",
    "Suggester",
    "Suggestion",
]
