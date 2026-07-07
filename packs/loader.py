"""The pack loader.

A pack is a declarative document (dict or YAML) that specializes the
domain-agnostic core for one domain WITHOUT touching core code. It declares:

  entity_subtypes : allow-list of second labels an Entity may carry
  edge_types      : allow-list of specialized entity-to-entity edge types
  metrics         : the canonical metric catalog (namespaced metric_keys)
  benchmarks      : reference points

`load_pack` registers the allow-lists on the GraphClient (so writes can be
validated) and MERGEs the catalog and benchmarks into the graph. It is
idempotent: loading the same pack twice converges.

Metric `aliases` are the seed for the resolver's tier-1 exact match: a column
whose name matches an alias auto-links to that metric. The resolver writes
confirmed mappings back as new aliases (see resolver.writeback), so the pack's
rule set grows in the graph and tier-2 volume decays over time.

The only bundled pack is the neutral `widgets` example. It exists to prove the
mechanism, not to model anything real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from graph.client import GraphClient

# Metric keys must be namespaced. A pack owns its own namespace; "shared" is the
# reserved cross-pack namespace for metrics common to every domain.
SHARED_NAMESPACE = "shared"


# Metric fields the loader maps to dedicated GraphClient arguments. Any other key
# on a metric entry is carried through as a free-form attribute (display_name,
# annualization, etc.), so a pack is not limited to this fixed set.
_RESERVED_METRIC_KEYS = frozenset({
    "metric_key", "formula", "unit", "numerator_def", "denominator_def",
    "provenance", "aliases",
})


@dataclass(frozen=True, slots=True)
class MetricDef:
    metric_key: str
    formula: str | None = None
    unit: str | None = None
    numerator_def: str | None = None
    denominator_def: str | None = None
    provenance: str | None = None
    aliases: tuple[str, ...] = ()
    """Column-name aliases that tier-1 exact match uses to auto-link. Seeds the
    resolver; grows via write-back."""

    attributes: dict[str, object] = field(default_factory=dict)
    """Free-form pack metric attributes beyond the reserved set (e.g. display_name,
    annualization). Written onto the Metric node as-is."""


@dataclass(frozen=True, slots=True)
class BenchmarkDef:
    benchmark_key: str
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Pack:
    name: str
    entity_subtypes: tuple[str, ...] = ()
    edge_types: tuple[str, ...] = ()
    metrics: tuple[MetricDef, ...] = ()
    benchmarks: tuple[BenchmarkDef, ...] = ()

    namespace: str | None = None
    """The metric-key namespace this pack owns. Defaults to `name` when unset, so
    a pack's display name can differ from its (often shorter) metric namespace."""

    @property
    def metric_namespace(self) -> str:
        return self.namespace or self.name

    def validate(self) -> None:
        """Each metric_key must live in this pack's namespace or the shared one.
        Catches copy-paste namespace mistakes before anything is written."""
        allowed = {self.metric_namespace, SHARED_NAMESPACE}
        for m in self.metrics:
            ns = m.metric_key.split(".", 1)[0]
            if ns not in allowed:
                raise ValueError(
                    f"metric_key {m.metric_key!r} is not in namespace "
                    f"{self.metric_namespace!r} or {SHARED_NAMESPACE!r}"
                )


def pack_from_dict(data: dict) -> Pack:
    return Pack(
        name=data["name"],
        namespace=data.get("namespace"),
        entity_subtypes=tuple(data.get("entity_subtypes", ())),
        edge_types=tuple(data.get("edge_types", ())),
        metrics=tuple(
            MetricDef(
                metric_key=m["metric_key"],
                formula=m.get("formula"),
                unit=m.get("unit"),
                numerator_def=m.get("numerator_def"),
                denominator_def=m.get("denominator_def"),
                provenance=m.get("provenance"),
                aliases=tuple(m.get("aliases", ())),
                attributes={k: v for k, v in m.items()
                            if k not in _RESERVED_METRIC_KEYS},
            )
            for m in data.get("metrics", ())
        ),
        benchmarks=tuple(
            BenchmarkDef(
                benchmark_key=b["benchmark_key"],
                attributes=dict(b.get("attributes", {})),
            )
            for b in data.get("benchmarks", ())
        ),
    )


def load_pack_file(client: GraphClient, path: str | Path) -> Pack:
    data = yaml.safe_load(Path(path).read_text())
    return load_pack(client, pack_from_dict(data))


def load_pack(client: GraphClient, pack: Pack) -> Pack:
    """Register the pack's allow-lists and MERGE its catalog. Idempotent."""
    pack.validate()
    client.register_allowlists(
        entity_subtypes=set(pack.entity_subtypes),
        edge_types=set(pack.edge_types),
    )
    for m in pack.metrics:
        attrs: dict[str, object] = dict(m.attributes)
        if m.aliases:
            attrs["aliases"] = list(m.aliases)
        client.upsert_metric(
            metric_key=m.metric_key,
            formula=m.formula,
            unit=m.unit,
            numerator_def=m.numerator_def,
            denominator_def=m.denominator_def,
            provenance=m.provenance,
            attributes=attrs or None,
        )
    for b in pack.benchmarks:
        client.upsert_benchmark(b.benchmark_key, attributes=b.attributes or None)
    return pack
