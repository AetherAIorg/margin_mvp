# margin-kg-mvp

A domain-agnostic knowledge-graph platform. It models the *semantics* of data
products (what every column, metric, and document actually means) and resolves
that meaning even when data dictionaries are missing.

This repository is the **foundation only**: two layers plus the bridge between
them. It contains zero domain logic. Domains are added later as declarative
*packs*, without touching any code here.

> For the production architecture that grows around this foundation (Celery
> workers, SharePoint and API connectors, data-lineage integration, Vespa hybrid
> search, and a worked domain pack), see
> [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md).

```
graph/       Layer 1: the fixed core ontology + the graph client
ingestion/   Layer 2: the generic Source contract + the common IR + infra
resolver/    the bridge: observed columns -> canonical metrics (3-tier funnel)
packs/        declarative domain specializations (only the neutral widgets example ships)
tests/        proofs of every invariant, all offline
```

## Why two layers

The whole design goal is *decoupling*. Downstream teams point ingestion at wildly
different systems (SharePoint, Postgres, Snowflake, REST APIs) and add different
business domains. Those two axes of change are isolated:

- **Adding a source** touches only a new `Source` implementation. Nothing about
  the graph or the resolver changes.
- **Adding a domain** touches only a new pack (a YAML file). No code changes.

Everything in between speaks one shape: the **IR** (intermediate representation).
No connector-specific shape ever reaches the graph or the resolver.

## Quickstart

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
uv run pytest            # 32 tests, all offline, no network or DB needed
```

Optional, to exercise the real Neo4j backend locally:

```bash
docker compose up -d     # Neo4j at bolt://localhost:7687, browser :7474
```

The compose file uses **Neo4j Enterprise** (developer license, accepted for
local/eval use). This is required because the `Column` identity is a `NODE KEY`
constraint on `(system, table, name)`, and NODE KEY is an Enterprise feature.

The foundation is fully testable with **no network and no database**: the
in-memory graph store models MERGE-on-key semantics faithfully, so idempotency
is a real property in the tests, not a mock. `Neo4jGraphStore` is the same
operations compiled to Cypher and is the only module that emits Cypher.

## Layer 1: the core ontology

Six node types, fixed for every domain forever:

| Node | Identity | Purpose |
|------|----------|---------|
| `Entity` | `uid` (unique) | the thing being described (base label; packs add a subtype) |
| `Metric` | `metric_key` (unique, namespaced) | canonical definition of a measurement |
| `Column` | `(system, table, name)` (node key) | a physical column observed in a source |
| `Document` | `uri` (unique) | a qualitative prose artifact |
| `Benchmark` | `benchmark_key` (unique) | a relational/strategic reference point |
| `Party` | `uid` (unique) | an actor with a role toward an entity |

The invariant "resolver spine" edges, all domain-agnostic, every one carrying
`{source_ref, as_of, created_by}` provenance:

```
(Column)   -[:MEASURES]->            (Metric)
(Metric)   -[:APPLIES_TO]->          (Entity)
(Metric)   -[:DEFINED_IN]->          (Document)
(Metric)   -[:BENCHMARKED_AGAINST]-> (Benchmark)
(Metric)   -[:COMPUTED_FROM]->       (Metric)
(Document) -[:DESCRIBES]->           (Entity)
(Party)    -[:HAS_ROLE {role}]->     (Entity)
(Entity)   -[:RELATED_TO {role}]->   (Entity)   # generic structural escape hatch
```

**Multi-label pattern.** Every asset node is `:Entity` plus an *optional* pack
subtype label (e.g. `:Entity:Widget`). Generic queries match `:Entity` and run
identically across every domain. The subtype label is written only if a loaded
pack allow-listed it; unknown labels are rejected at write time, not silently
persisted.

All writes go through `MERGE` on the identity key, so re-ingestion converges
rather than duplicating. The only API is `GraphClient`; calling code never
writes Cypher.

```python
from graph import GraphClient, InMemoryGraphStore   # or Neo4jGraphStore(...)

client = GraphClient(InMemoryGraphStore())
client.init_schema()                                 # creates identity constraints
client.upsert_metric("shared.record_count", unit="count")
client.upsert_entity("acme.parts", subtype_label="Widget")   # needs the widgets pack loaded
```

## Layer 2: the ingestion contract

Every connector implements one protocol:

```python
class Source(Protocol):
    connector_version: str
    def discover(self) -> Iterable[WorkItem]: ...   # enumerate work; cheap; idempotent
    def fetch(self, item: WorkItem) -> RawArtifact: ...  # pull one item; rate-limited
    def parse(self, artifact: RawArtifact) -> ParsedBundle: ...  # normalize into the IR
```

The three seams do exactly one thing each: **discover** is cheap and drives
crash-resume (stable `item_id`); **fetch** is the single rate-limited I/O choke
point; **parse** is pure and unit-testable with no network.

The IR every connector produces:

- **observed columns** `(system, table, name, dtype, sample_values, has_dictionary)`
- **observed documents** `(uri, title, text, as_of)`
- **observed entities** `(uid, candidate_labels, attributes, columns)`
- **observed relations** generic `(subject_uid, role, object_uid)` triples
- **provenance** `(source_ref, fetched_at, connector_version)`

An observed entity may carry **its own columns** (`ObservedEntity.columns`). Use
this when the entity *is* a measured dataset with its own feed, as opposed to
being described by columns living elsewhere. `ParsedBundle.iter_columns()` yields
free-standing and entity-owned columns together so downstream never misses them.

Cross-cutting infrastructure, all generic:

- **Rate limiter** (`TokenBucket` behind the `RateLimiter` protocol): one choke
  point every `fetch` routes through, configurable per source, pluggable for a
  distributed limiter later.
- **Checkpointer** (`InMemoryCheckpointer` behind the `Checkpointer` protocol):
  idempotent discovery keyed on `(source_ref, item_id)` so crash/resume never
  double-ingests.
- **Parser router** (`ParserRouter`): a source emitting multiple artifact kinds
  (rows vs prose) dispatches each to a registered parser by type, and every
  parsed record is stamped with `schema_version`.

## The resolver: mapping columns to metrics

Dictionaries are missing by assumption, so an observed column's meaning is
resolved through a three-tier funnel:

1. **Tier 1 auto-link** exact match against known pack rules (metric aliases).
2. **Tier 2 suggest** string-similarity candidate + top-k alternatives, above a
   confidence threshold, for a human to confirm.
3. **Tier 3 escalate** queue for a human to define a new metric.

When a human confirms a tier-2/3 mapping, `Resolver.confirm` links the column
**and writes the mapping back** as a new metric alias in the graph. So the next
same-named column resolves at tier 1, and tier-2 volume decays over time.

The similarity suggester is swappable: `StringSimilaritySuggester` ships;
`EmbeddingSuggester` is a stubbed strategy behind the same interface, ready for
an embedding-based nearest-metric backend with no change to the funnel.

## Extension path 1: add a new source

Implement `Source` and register it. Worked example, the whole pipeline over a
fixture with no network (see `ingestion/connectors/synthetic.py`):

```python
from graph import GraphClient, InMemoryGraphStore
from ingestion import TokenBucket, InMemoryCheckpointer, run_ingest
from ingestion.connectors.synthetic import SyntheticSource, widgets_fixture
from packs import WIDGETS_PACK_PATH, load_pack_file
from resolver import Resolver

client = GraphClient(InMemoryGraphStore()); client.init_schema()
load_pack_file(client, WIDGETS_PACK_PATH)
resolver = Resolver(client)

source = SyntheticSource(widgets_fixture(), TokenBucket(rate=100))
report = run_ingest(source, client, resolver, InMemoryCheckpointer())
# report.by_tier(Tier.SUGGESTED) -> columns awaiting human confirmation
```

To write your own connector:

1. Build your fetch client (REST, DB cursor, file walker). Route every network
   call through the injected `RateLimiter`.
2. `discover()` yields `WorkItem`s with a **stable** `item_id` and an
   `artifact_type` hint.
3. `fetch(item)` pulls bytes/rows and returns a `RawArtifact`.
4. Register one parser per `artifact_type` on a `ParserRouter`; each parser
   normalizes into the IR. `parse()` just delegates to the router.

That is the entire contract. The graph, resolver, and packs are untouched.

## Extension path 2: add a new domain pack

A pack is a YAML document declaring an allow-list of entity subtype labels, an
allow-list of specialized edge types, a namespaced metric catalog, and
benchmarks. `load_pack` registers the allow-lists (for write-time validation)
and MERGEs the catalog. See `packs/widgets.yaml` for the neutral example.

```yaml
name: mypack
entity_subtypes: [Thing]
edge_types: [CONTAINS]
metrics:
  - metric_key: mypack.some_measure     # namespaced under the pack (or "shared")
    unit: unit_a
    aliases: [some_measure, sm]         # seeds the resolver's tier-1 exact match
benchmarks:
  - benchmark_key: mypack.reference_point
```

```python
from packs import load_pack_file
load_pack_file(client, "packs/mypack.yaml")
```

Loading is idempotent. `metric_key` must live in the pack's namespace or the
reserved `shared` namespace. `aliases` are the seed for tier-1 resolution and
grow automatically via resolver write-back.

## Deliberate extension points (not built here)

These are seams left clean on purpose, per the "add an extension point, not the
feature" rule:

- **Embedding suggester** for tier-2, behind `Suggester` (`EmbeddingSuggester`
  stub).
- **Durable checkpointer / distributed rate limiter**, behind `Checkpointer` /
  `RateLimiter`.
- **Real connectors** (SharePoint, Postgres, Snowflake, REST). Only the neutral
  synthetic reference connector ships.

The IR expresses document-to-entity (`ObservedDocument.describes`) and
metric-to-document (`.defines`) links, pack-specialized edge types
(`ObservedRelation.rel_type`), and arbitrary pack metric attributes, and the
resolver has a tier-0 `DOCUMENTED` outcome for sources that ship a dictionary.
These closed the seams a first downstream domain pack surfaced.

## Constraints this foundation holds to

Python 3.11+, type-hinted throughout, `uv` for env/deps, no em dashes, and
**domain-agnostic core**: no industry vocabulary anywhere in `graph/`,
`ingestion/`, or `resolver/`. The only example vocabulary is the neutral
`widgets` pack, which exists solely to demonstrate the mechanism.
