# System Design: Semantic Knowledge Graph Platform

Status: draft for review
Owner: platform team
Relationship to existing docs: this document extends [`README.md`](../README.md).
The README describes the shipped foundation (the two layers, the Source
contract, and the two extension paths). This document describes the production
system that grows around that foundation: distributed ingestion, document and
API connectors, data-lineage integration, hybrid search, the serving API, and a
worked domain pack. Read the README first; it is the contract
this design must not break.

---

## 1. Purpose and scope

Build a knowledge graph that models the *semantics* of data products (what every
column, metric, and document actually means) and resolves that meaning even when
data dictionaries are missing. Internal teams
build on top of it by adding domain "packs" and source connectors.

In scope for this design: how the shipped foundation scales into a production
platform, and how the named integrations attach to it (SharePoint, generic
APIs, data lineage tools, Celery workers, hybrid search).

Out of scope, by construction: any domain logic in the core. A domain pack
appears here only as a worked example of a *pack plus connectors* built on the
unchanged foundation. No domain vocabulary enters `graph/`, `ingestion/`, or
`resolver/`. That separation is the whole point and is treated as an invariant,
not a preference.

---

## 2. Current state (the shipped foundation)

What exists today, fully tested (33 tests, offline plus a live Neo4j check):

- **Layer 1, core ontology** (`graph/`): six fixed node types (Entity, Metric,
  Column, Document, Benchmark, Party) and eight domain-agnostic "resolver spine"
  edges, every edge carrying `{source_ref, as_of, created_by}` provenance.
  Identity constraints including a NODE KEY on `(Column.system, table, name)`.
  A storage seam (`GraphStore`) with an in-memory backend and a Neo4j backend;
  Cypher lives only in the Neo4j backend. `GraphClient` is the only API and
  enforces the multi-label invariant and pack allow-lists.
- **Layer 2, ingestion contract** (`ingestion/`): the `Source` protocol
  (`discover` / `fetch` / `parse`), the common IR that every connector
  normalizes into, and four cross-cutting pieces: a token-bucket rate limiter, a
  parser router (schema-version stamped), a pluggable checkpointer, and the
  generic pipeline.
- **Resolver** (`resolver/`): a three-tier funnel (exact auto-link, similarity
  suggest, escalate) with write-back so confirmed mappings become pack rules and
  tier-2 volume decays. The embedding suggester is a stub behind a clean seam.
- **Packs** (`packs/`): the pack loader and one neutral `widgets` example.

Invariants this design preserves:

1. Everything downstream consumes only the IR. No connector-specific shape ever
   reaches the graph or the resolver.
2. All graph writes are idempotent `MERGE`s on identity keys. Re-ingestion
   converges; it never duplicates. This is what makes at-least-once delivery
   safe under distributed workers (see section 5).
3. The core is domain-agnostic. Domains are added as packs and connectors, never
   as core code changes.

Both extension paths are now exercised by a downstream domain pack that ingests
live data from real public sources (a filings/document source and a
reference-rate API) and closed six foundation seams it surfaced (metric attribute
passthrough, pack namespace decoupling, IR-expressed specialized edges, document
DESCRIBES/DEFINED_IN links, `run_ingest` bundle retention, and a tier-0
DOCUMENTED resolver outcome).

### 2.1 As-built component and data flow

What exists today, single-process, driven by the demo script. Contrast this with
the production target in section 4: no Celery, no Redis/Vespa, one in-process
rate limiter, a CSV columnar sink, and the real Neo4j from `docker-compose`.

```
  Real free sources                 example pack  (downstream domain layer)
  -----------------                 imports the foundation as a library
  Filings source                    ---------------------------------------------
    documents + tabular exhibits    pack.yaml --load_pack_file--> [pack rules
  Reference-rate API                    |                                in the graph]
        |                             |  CachedHttp: real User-Agent
        +---------------------------> |  + TokenBucket(< 10 req/s) + disk cache
                                      v
                            docs / rows / rates connectors
                            (implement Source: discover -> fetch -> parse)
                                      |
                                      v   common IR (ParsedBundle):
                                      |   columns, documents{describes,defines},
                                      |   entities+owned columns,
                                      |   relations{role, rel_type}, provenance
  ====================================|=================== foundation ===========
                                      v
  ingestion/   run_ingest -> load_bundle        (Checkpointer, ParserRouter,
                    |            |                RateLimiter live here)
     observed columns |          | entities / documents / relations
                      v          v
  +---------------------------+   +--------------------------------------------+
  | resolver/  3-tier funnel  |   | graph/                                     |
  |  0 DOCUMENTED (has_dict.)  |   |  GraphClient  (only write/read API;        |
  |  1 AUTO_LINK (pack alias)  |-->|   multi-label + edge allow-list enforced)  |
  |  2 SUGGEST (string sim;    |   |  6 nodes + spine edges                     |
  |    EmbeddingSuggester=stub)|   |  (MEASURES, APPLIES_TO, DEFINED_IN,        |
  |  3 ESCALATE -> queue       |   |   DESCRIBES, BENCHMARKED_AGAINST, ...,     |
  |  confirm -> write-back     |   |   + pack CONTAINS)                         |
  +---------------------------+    |         |  GraphStore protocol             |
                                   |         v                                  |
                                   |  InMemory (offline tests) | Neo4j (Cypher) |
                                   +-------------------|------------------------+
                                                       v
                                            Neo4j  (docker-compose, Enterprise)

  bulk observed values (rate series, column samples) --> ColumnarStore (CSV)
```

Legend: everything is built and tested except `EmbeddingSuggester` (a stubbed
`Suggester` seam). The in-memory graph store backs the offline test suite; the
Neo4j store is the only module that emits Cypher. Packs and connectors carry all
domain vocabulary; `graph/ingestion/resolver/packs` stay domain-agnostic.

---

## 3. Design goals and principles

| Goal | How the design honors it |
|------|--------------------------|
| Decoupling of sources from domains | Sources implement `Source`; domains are packs. The two axes of change never touch each other or the core. |
| Idempotent, resumable ingestion | Stable `item_id` + durable checkpointer + `MERGE`. A crash or a redelivered task cannot double-ingest. |
| One global choke point per source | A single distributed rate limiter that every `fetch` routes through, so hard per-IP API limits cannot get us banned. |
| Meaning resolved without dictionaries | The three-tier resolver, strengthened by lineage integration and embedding search, with human-in-the-loop confirmation and write-back. |
| Full auditability | Provenance on every edge, raw-artifact archival, and bidirectional data-lineage integration. Any metric value traces back to the source column and the document that defines it. |
| Extensible retrieval | Graph for structure and traversal; a hybrid search engine for lexical plus semantic retrieval. Each does what it is good at. |

---

## 4. Target architecture

```
                         +-------------------------------------------+
   External systems      |                Ingestion                  |
   ----------------      |                                           |
   SharePoint  ---------->  discover -> fetch -> parse -> IR          |
   REST APIs   ---------->  (Celery workers, per-source rate limit)   |
   Postgres/Snowflake -->                    |                        |
   Lineage tools -------->                    v                        |
                         |            load_bundle (IR -> graph)       |
                         +------------------|------------------------+
                                            |
                    +-----------------------+------------------------+
                    v                                                v
          +-------------------+                          +----------------------+
          |   Neo4j (graph)   |  <---- resolver ---->    |  Escalation queue +   |
          |  core + packs     |  write-back rules        |  human review UI      |
          +---------+---------+                          +----------------------+
                    |  change data capture (projection)
                    v
          +-------------------+        +----------------------+
          |  Vespa (hybrid    | <----- |  Embedding service   |
          |  search index)    |        |  (batch, GPU)        |
          +---------+---------+        +----------------------+
                    |
                    v
          +-------------------------------------------------+
          |  Serving API (FastAPI): resolve, lineage,        |
          |  semantic search, review, metric catalog         |
          +-------------------------------------------------+

  Shared infra: Redis (Celery broker + distributed rate limiter),
  Postgres (checkpointer, escalation queue, pack-rule audit),
  Object store / S3 (raw artifact archive for replay),
  Secrets manager (per-source credentials), Observability stack.
```

Component responsibilities:

- **Ingestion workers** run the `Source` contract under Celery. They are the
  only thing that talks to external systems.
- **Neo4j** is the system of record for structure and meaning.
- **Vespa** is a read projection for retrieval (lexical plus vector). It is
  never a system of record; it is rebuildable from Neo4j.
- **Resolver** bridges observed columns to canonical metrics and is invoked
  inside `load_bundle` and by the review UI.
- **Serving API** is the only outward query surface.

---

## 5. Ingestion subsystem at scale

### 5.1 The contract does not change

The shipped `Source` protocol (`discover` / `fetch` / `parse`) and the IR are
already the right seams. Scaling is an orchestration and infrastructure concern
layered *around* the contract, not a change to it. Every new integration below
is "implement `Source`, register it," exactly as the README promises.

### 5.2 Celery-based orchestration

Map the pipeline stages onto Celery tasks and queues:

```
beat (scheduler)
  -> discover_source(source_id)              [queue: discover]
       for each WorkItem not seen:
         -> ingest_item(source_id, item)     [queue: fetch]   fan-out, one per item
              fetch(item)  (rate-limited)
              parse(artifact) -> IR
              -> load_and_resolve(bundle)     [queue: load]
```

Design decisions:

- **Fan-out on discovery.** `discover` is cheap and idempotent; it enumerates
  `WorkItem`s and dispatches one `ingest_item` task each. The stable `item_id`
  is the Celery idempotency key and the checkpointer key, so a redelivered or
  retried task is a no-op.
- **Separate queues by resource profile.** `fetch` is I/O bound and
  rate-limited; `parse` is CPU bound (PDF extraction, OCR); `load` is
  graph-write bound. Route each to a worker pool sized independently. This keeps
  a slow SharePoint download from starving graph writes.
- **At-least-once is safe here.** Celery guarantees at-least-once, not
  exactly-once. Because every graph write is a `MERGE` on an identity key and
  the checkpointer dedupes discovery, at-least-once delivery converges. We lean
  on the idempotency invariant rather than fighting Celery's delivery model.
- **Retries with backoff.** `fetch` tasks retry with exponential backoff and
  jitter on transient errors (HTTP 429/5xx). A poison item after N retries goes
  to a dead-letter queue and is surfaced, not silently dropped.
- **Backpressure.** Discovery respects a max in-flight bound per source so a
  large drive does not flood the broker.

### 5.3 Distributed rate limiting (the key upgrade)

The shipped `TokenBucket` is in-process. Under multiple Celery workers on
multiple hosts, "one global choke point per source" requires a *shared* bucket.
The design keeps the exact `RateLimiter` protocol and adds a `RedisTokenBucket`
implementation backed by a Redis Lua script (atomic refill-and-consume). Every
connector's `fetch` still calls `rate_limiter.acquire()`; only the
implementation changes. Config is per source (rate, burst) so a public API with
a hard per-IP limit and an internal warehouse get different budgets from one
mechanism. This is the pluggable seam the foundation already left open.

### 5.4 Durable checkpointing and crash-resume

The shipped `InMemoryCheckpointer` becomes a `PostgresCheckpointer` implementing
the same `Checkpointer` protocol, keyed on `(source_ref, item_id)` plus a
content hash / eTag for change detection. This gives true crash-resume across
worker restarts and lets incremental sync skip unchanged items (fetch nothing if
the eTag is unchanged). The decision to keep this an interface (made during the
foundation build) is what makes this a drop-in.

### 5.5 Raw artifact archival and replay

`fetch` writes the raw bytes to object storage (S3) keyed by
`(source_ref, item_id, fetched_at)` before parsing. Rationale: parsers evolve
(new extraction model, bug fix, new `schema_version`), and we must be able to
re-parse history without re-hitting the source (which may rate-limit us or may
have changed). Replay = re-run `parse` and `load` over archived artifacts. This
also underpins reproducibility for audit.

### 5.6 Connectors

Each is a `Source` implementation. None touches the core.

#### SharePoint and document ingestion

- **discover**: Microsoft Graph API. Enumerate sites, document libraries, and
  `driveItem`s. Use **delta queries** so re-discovery returns only changes;
  `item_id` = driveItem id, change detection via eTag stored in the
  checkpointer. Incremental by design.
- **fetch**: download file content through the shared rate limiter (Graph API
  throttles aggressively, so the choke point matters). Archive raw bytes.
- **parse**: route by content type through the `ParserRouter`:
  - `.docx`, `.pdf`, `.pptx` -> text extraction (Apache Tika or `unstructured`)
    -> `ObservedDocument(uri, title, text, as_of)`.
  - scanned PDFs -> OCR parser (Tesseract or a cloud OCR) as a distinct
    registered parser.
  - spreadsheets that are really tabular data -> a rows parser emitting
    `ObservedColumn`s, not prose. Same source, two artifact types, one router.
- **Chunking for search** is not an IR concern. The IR carries the whole
  document text; chunking and embedding happen in the search-projection pipeline
  (section 8). Keeping chunking out of the IR avoids coupling ingestion to a
  retrieval implementation.
- Auth: OAuth2 client credentials (app registration), tokens from the secrets
  manager, refreshed by the connector.

#### Generic REST / API sources

The in-memory REST stub shipped in `ingestion/connectors/synthetic.py` already
proves this shape. A real one adds: pagination (cursor or page tokens surfaced
as additional `WorkItem`s or handled inside `fetch`), per-host auth, retry on
429/5xx, and the shared rate limiter. Response JSON is parsed into
`ObservedColumn`s, `ObservedEntity`s, `ObservedRelation`s, or `ObservedDocument`s
depending on the endpoint. Different API response shapes converge on the IR;
that is the decoupling goal restated for APIs specifically.

#### Columnar warehouses (Postgres, Snowflake, AWS)

- **discover**: enumerate schemas/tables via `information_schema` or the
  provider metadata API. `item_id` = fully qualified table name plus a snapshot
  marker.
- **fetch**: pull column metadata and a bounded sample of values (never the full
  table; sampling is enough to drive resolution). Rate-limited to respect
  warehouse credit budgets.
- **parse**: emit `ObservedColumn(system, table, name, dtype, sample_values,
  has_dictionary)`. If the warehouse ships column comments/descriptions, set
  `has_dictionary=True`; the resolver can then trust tier-1 more.

#### Data lineage tools (bidirectional)

Tools: OpenLineage / Marquez, dbt (manifest and catalog), Collibra, Atlan.

- **Inbound (consume lineage).** A `LineageSource` ingests column-level lineage
  and metadata. This does two valuable things:
  1. Supplies the missing dictionary. A column that lineage describes arrives
     with `has_dictionary=True` and often a known upstream definition, which
     lets the resolver auto-link at tier 1 instead of guessing.
  2. Populates `COMPUTED_FROM` between metrics (Metric derived from Metric) and
     structural `RELATED_TO` between entities, straight from lineage edges. The
     graph's derivation spine is fed by real lineage rather than inferred.
- **Outbound (emit lineage).** The platform emits OpenLineage events describing
  its own resolution decisions (this column was mapped to this metric, by this
  resolver version, from this source). Downstream governance tools then see the
  semantic layer as part of the lineage graph. This closes the audit loop.

Net effect: lineage integration directly attacks the "dictionaries are missing"
assumption by importing whatever dictionaries do exist, and it enriches
provenance for compliance.

---

## 6. Knowledge graph subsystem

- **Neo4j**: Enterprise (NODE KEY is an Enterprise feature, per the README),
  deployed as a causal cluster for HA in production. `GraphClient` remains the
  only API. Writes are batched per bundle inside `load_and_resolve`.
- **Packs at scale**: packs are versioned YAML in a registry (git-backed). Pack
  load is idempotent and MERGEs the catalog. A pack version is recorded so the
  `created_by` provenance can reference both the resolver version and the pack
  version that asserted an edge.
- **Write-back governance**: resolver write-back (a confirmed mapping becoming a
  metric alias) is an audited operation. Confirmations are attributed to a user,
  recorded in Postgres with the before/after alias set, and reversible. This
  matters because write-back changes future automatic behavior; it must be
  traceable.

---

## 7. Resolver evolution

The three-tier funnel is unchanged in structure. Production strengthens it:

- **Tier 1 (exact)**: fed by pack aliases plus write-back plus imported lineage
  dictionaries. As lineage and confirmations accumulate, more columns land here
  and human volume drops.
- **Tier 2 (suggest)**: the shipped `StringSimilaritySuggester` is joined by a
  `VespaEmbeddingSuggester` that implements the already-defined `Suggester`
  interface (the `EmbeddingSuggester` stub becomes real). It queries Vespa for
  nearest metrics by embedding of the column name plus sample values plus any
  description, returning candidates and scores. Blend lexical and vector scores
  (see section 8). This is the plug-in point the foundation deliberately left.
- **Tier 3 (escalate)**: the in-memory `EscalationQueue` becomes a durable
  Postgres-backed queue that feeds a human review UI. A reviewer either confirms
  a suggestion (triggering write-back) or defines a new Metric (which updates
  the pack). Decay of tier-2 volume over time is a tracked product metric.

---

## 8. Hybrid search subsystem (Vespa)

### Why a search engine at all

Neo4j excels at structural traversal (metric lineage, entity relationships) but
is not the right tool for lexical-plus-semantic retrieval over large corpora of
documents, columns, and metric definitions. Two needs demand it:

1. The resolver's tier-2 wants embedding-based nearest-metric, not just string
   similarity.
2. The serving API wants "find metrics/documents about X" search and retrieval
   for downstream RAG.

Vespa is chosen because it does **hybrid ranking** (BM25 lexical plus
approximate nearest neighbor over vectors) in a single query with a tunable
ranking expression, at scale. Alternatives considered: OpenSearch/Elasticsearch
with kNN, pgvector, Qdrant, Weaviate. Vespa wins on first-class hybrid ranking
and phased ranking; any of the others is a valid smaller-footprint substitute
and the indexing seam is the same.

### What is indexed

Three document types, each rebuildable from Neo4j:

- **Metric**: metric_key, definition text, unit, aliases, plus an embedding of
  the definition. Powers tier-2 nearest-metric and catalog search.
- **Column**: system/table/name, sample values, description, plus an embedding.
  Used to find similar already-resolved columns.
- **Document (chunked)**: prose split into passages, each with an embedding.
  Powers document search and RAG retrieval, and links back to the Document node.

### Ranking

A phased hybrid rank: BM25 over text fields for recall, then a second phase
combining BM25 with cosine similarity of the query embedding, weights tuned per
use case. Exposed to the resolver as a normalized 0..1 score so tier-2 logic is
unchanged.

### Keeping Vespa in sync

Neo4j is the source of truth; Vespa is eventually consistent. A change-data-
capture / projection pipeline listens to graph writes (Neo4j change feed or a
transactional outbox written by `GraphClient`) and feeds Vespa. Embeddings are
produced by a batch **embedding service** (a model server, GPU-backed) invoked
by the projection pipeline. Because Vespa is a projection, it can be rebuilt
from scratch by replaying the graph, which also lets us re-embed when the model
changes.

### The clean interface win

The resolver already isolates suggestion behind `Suggester`. Adding Vespa is a
new `Suggester` implementation and a projection pipeline. The funnel, the graph,
and every connector are untouched. This is the payoff of having stubbed the
embedding suggester rather than hardcoding string similarity.

---

## 9. Serving and API layer

Two distinct meanings of "API," both addressed:

- **Inbound (APIs as sources)**: covered in 5.6. External APIs implement
  `Source`. Nothing special beyond the contract.
- **Outbound (the platform's own API)**: a FastAPI service (REST, optionally
  GraphQL for graph-shaped reads) that is the only query surface. Core
  endpoints:
  - `GET /resolve/column?system=&table=&name=` -> the metric(s) a column
    measures and the entities they apply to (the shipped `resolve_column` read
    path).
  - `GET /metrics/{metric_key}/lineage` -> `COMPUTED_FROM` traversal, the
    derivation tree of a metric.
  - `GET /search?q=` -> hybrid search over metrics/documents/columns via Vespa.
  - `GET /entities/{uid}` -> an entity, its metrics, documents, parties, and
    relations. Generic queries match `:Entity`, so this endpoint is identical
    across every domain (the multi-label payoff).
  - Review endpoints backing the human-in-the-loop UI: list escalations, list
    tier-2 suggestions, confirm a mapping (triggers write-back), define a metric.
- **AuthN/Z**: OIDC for callers; role-based access. Access control can key on
  `:Entity` subtype labels so a team only sees the domains it owns.

---

## 10. Worked domain example: a widgets catalog pack

This section demonstrates the design paying off. A product catalog / inventory
domain is modeled entirely as a pack plus connectors, using the neutral
`widgets` pack that ships. The core does not change. Every domain concept below
maps onto one of the six fixed node types and the eight fixed edges. This mapping
is the proof that the domain-agnostic core was worth it.

### 10.1 Mapping onto the fixed core

| Domain concept | Core node | Notes |
|----------------|-----------|-------|
| A single catalog item | `Entity` + subtype `Widget` | subtype allow-listed by the pack |
| An assembly / kit of items | `Entity` + subtype `Gadget` | can carry its own aggregate columns (see 10.4); `CONTAINS` its items |
| On-hand quantity | `Metric` `shared.record_count` | shared namespace, common across domains |
| Unit weight | `Metric` `widgets.weight` | |
| Unit length | `Metric` `widgets.length` | |
| Average assembly weight | `Metric` `widgets.avg_weight` | derived (see edges below) |
| Spec sheet, supplier catalog | `Document` | ingested from SharePoint |
| Reference weight threshold | `Benchmark` `widgets.reference_weight` | `BENCHMARKED_AGAINST` |
| Supplier, manufacturer | `Party` | `HAS_ROLE {role}` |

Edges used, all from the fixed spine:

```
(Column: "qty_oh")-[:MEASURES]->(Metric: shared.record_count)
(Metric: shared.record_count)-[:APPLIES_TO]->(Entity:Widget)
(Metric: widgets.avg_weight)-[:COMPUTED_FROM]->(Metric: widgets.weight)
(Document: spec_sheet)-[:DEFINES ... DEFINED_IN]->(Metric: widgets.weight)
(Document: supplier_catalog)-[:DESCRIBES]->(Entity:Gadget)
(Party: supplier)-[:HAS_ROLE {role:"supplies"}]->(Entity:Gadget)
(Entity:Widget)-[:RELATED_TO {role:"component_of"}]->(Entity:Gadget)
(Entity:Gadget)-[:RELATED_TO {role:"listed_in"}]->(Entity:Gadget)
```

The pack may also allow-list specialized edge types (for example `CONTAINS`)
via the edge allow-list, but note that the generic `RELATED_TO {role}` escape
hatch already expresses all of it. Specialized types are sugar, not necessity.

### 10.2 The pack (declarative, no code)

```yaml
name: widgets
entity_subtypes: [Widget, Gadget]
edge_types: [CONTAINS]
metrics:
  - metric_key: shared.record_count
    unit: count
    aliases: [count, qty, quantity, n]
  - metric_key: widgets.weight
    unit: gram
    numerator_def: mass of one widget
    aliases: [weight, wgt, mass]
  - metric_key: widgets.length
    unit: millimetre
    aliases: [length, len, size]
benchmarks:
  - benchmark_key: widgets.reference_weight
```

### 10.3 The resolution narrative (why this platform exists)

Supplier inventory feeds are the canonical "dictionaries are missing" problem.
Every supplier names the on-hand quantity column differently: `qty`, `Quantity`,
`on_hand`, `qty_oh`. The flow:

1. A warehouse connector ingests supplier A's feed. Column `qty` is observed.
2. Resolver tier 1 finds `qty` in the `widgets` pack aliases and auto-links it to
   `shared.record_count`. Done, no human.
3. Supplier B's feed has `qty_oh`, not in the aliases. Tier 2 (Vespa embedding
   suggester) proposes `shared.record_count` at high confidence with
   alternatives. An analyst confirms once.
4. Write-back adds `qty_oh` as an alias. Supplier C's identical column now
   auto-links at tier 1. Human volume decays toward zero as coverage grows.
5. A truly novel column (`some_bespoke_field`) escalates to tier 3, where an
   analyst defines a new metric, extending the pack.

Meanwhile the spec sheet (from SharePoint) becomes a `Document`, and the metric
definition edge `DEFINED_IN` points `widgets.weight` at the exact sheet that
defines it. Provenance on every edge plus raw-artifact archival means a weight
value traces back to the feed column, the resolver version that mapped it, and
the spec-sheet section that defines the measurement. That end-to-end trace is the
auditability value.

### 10.4 Why entity-owned columns matter here

A `Gadget` (assembly) is not only described by item-level columns living in a
separate table; it also has its own aggregate feed (assembly-level count, total
weight). The IR's `ObservedEntity.columns` field (made first-class in the
foundation) models exactly this: the gadget entity carries its own observed
columns, and `load_bundle` links the resolved metrics `APPLIES_TO` the gadget. A
reference entity that is itself a measured dataset is a generic case, and the
assembly is the concrete instance that justified the design.

### 10.5 What did NOT change

No file in `graph/`, `ingestion/`, or `resolver/` changes to support this
domain. The additions are: one YAML pack, warehouse/SharePoint connectors
(generic, reusable across domains), and Vespa content. If a second domain
arrives next quarter, it is another pack and reuses the same connectors. That is
the platform thesis, demonstrated.

---

## 11. Cross-cutting concerns

- **Provenance and auditability**: every edge carries `{source_ref, as_of,
  created_by}`. Combined with raw-artifact archival and emitted OpenLineage,
  every fact is traceable to its source and the code version that asserted it.
- **Idempotency**: `MERGE` everywhere plus checkpointer dedupe. Safe under
  retries and at-least-once delivery.
- **Schema versioning**: `schema_version` on every IR record (enforced by the
  parser router). Consumers can gate on it; parsers can evolve behind archival
  and replay.
- **Security and PII**: some sources contain sensitive or personal data (PII).
  The foundation stores column metadata and samples, not necessarily full
  records; sample values from PII columns must be masked at the connector.
  Field-level access control keys on Entity subtype labels. Source credentials
  live in a secrets manager. This needs a dedicated data-governance review
  before real ingestion of sensitive records (open question below).
- **Observability**: per-source ingestion metrics (items discovered, fetched,
  skipped, resolution tier distribution, escalation backlog, tier-2 decay rate),
  rate-limiter saturation, graph write latency, Vespa freshness lag.
- **Multi-tenancy**: if multiple teams share the platform, isolate by pack
  ownership and subtype-scoped access; consider a Neo4j database per tenant if
  isolation must be hard.

---

## 12. End-to-end data flow (one item)

```
1. beat triggers discover_source("sharepoint:site-x")
2. SharePointSource.discover() -> WorkItem(item_id=driveItem-123, eTag=abc)
3. PostgresCheckpointer.has_seen? no  -> dispatch ingest_item
4. ingest_item: RedisTokenBucket.acquire()  (respect Graph API limit)
5. SharePointSource.fetch() -> RawArtifact; raw bytes archived to S3
6. SharePointSource.parse() -> ParserRouter -> pdf parser -> IR (ObservedDocument)
7. load_bundle: GraphClient.upsert_document(...) with provenance
8. resolver runs over any observed columns (none for a pure doc)
9. checkpointer.mark_done(source_ref, item_id, eTag)
10. graph change feed -> projection pipeline -> embedding service -> Vespa upsert
11. Serving API /search now returns this document
```

---

## 13. Deployment and infrastructure

| Component | Technology | Notes |
|-----------|------------|-------|
| Graph | Neo4j Enterprise, causal cluster | NODE KEY requires Enterprise |
| Broker + rate limiter | Redis | Celery broker/result backend; Lua token bucket |
| Workers | Celery, separate pools per queue | fetch / parse / load isolated |
| Checkpointer, escalation, audit | Postgres | durable state |
| Raw artifact archive | S3 or compatible | replay and reproducibility |
| Search | Vespa cluster | rebuildable projection |
| Embeddings | model server (GPU) | batch, invoked by projection |
| Serving | FastAPI | only outward query surface |
| Secrets | vault / cloud secrets manager | per-source credentials |
| Observability | metrics + logs + traces | ingestion and freshness dashboards |

Local development keeps the shipped `docker-compose.yml` (Neo4j) and the
in-memory implementations, so the foundation stays fully testable offline. The
production implementations (Redis rate limiter, Postgres checkpointer, Vespa
suggester) are added behind their existing interfaces without touching callers.

---

## 14. Phased roadmap

1. **Foundation (done).** Two layers, resolver, widgets pack, tests, local Neo4j.
2. **Distributed ingestion.** Celery orchestration, Redis rate limiter, Postgres
   checkpointer, raw-artifact archival. One real connector (warehouse) end to
   end.
3. **Documents.** SharePoint connector, extraction/OCR parsers, Document nodes.
4. **First domain pack.** A domain pack plus warehouse-feed resolution, with
   the human review UI and write-back governance.
5. **Lineage integration.** Consume OpenLineage/dbt to seed dictionaries and
   `COMPUTED_FROM`; emit OpenLineage for auditability.
6. **Hybrid search.** Vespa projection, embedding service, `VespaEmbeddingSuggester`
   for tier 2, semantic search in the serving API.
7. **Hardening.** HA, PII governance, multi-tenancy, observability depth.

Each phase is independently shippable because the seams already exist.

---

## 15. Risks and open questions

- **PII in sensitive source data.** Needs a governance decision on what is
  stored, masking policy for sample values, and field-level access control
  before real ingestion. Highest-priority open item.
- **Document-to-entity linking.** The IR carries documents and entities but the
  `DESCRIBES` edge is not auto-created during ingestion today (noted in the
  README). Deciding how a document is linked to the entities it describes
  (explicit relation, NLP entity extraction, or manual) is an open design step.
- **Embedding model choice and drift.** Re-embedding on model change is a batch
  replay; acceptable, but cost and cadence need sizing.
- **Vespa vs simpler vector store.** If corpus size is modest early, a smaller
  store (pgvector, Qdrant) may be enough. The `Suggester` and projection seams
  make this reversible; pick by measured scale, not upfront.
- **Resolver confidence thresholds.** Tier-2 threshold tuning is empirical and
  per domain; needs a feedback loop from review outcomes.

---

## Appendix: how each requested integration attaches

| Ask | Where it lands | Touches core? |
|-----|----------------|---------------|
| APIs (inbound) | new `Source` implementations | no |
| APIs (outbound) | FastAPI serving layer | no |
| SharePoint / docs | `Source` + extraction/OCR parsers on the router | no |
| Data lineage tools | `LineageSource` (in) + OpenLineage emitter (out) | no |
| Celery workers | orchestration around the pipeline; `RedisTokenBucket`, `PostgresCheckpointer` behind existing interfaces | no |
| Hybrid search (Vespa) | read projection + `VespaEmbeddingSuggester` behind `Suggester` | no |
| A domain pack | one YAML pack + reused connectors + Vespa content | no |

Every requested capability attaches through a seam the foundation already
defines. Nothing on this list requires changing `graph/`, `ingestion/`, or
`resolver/` core code. That is the design working as intended.
