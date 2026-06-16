# MetricGraph

**Glean for financial metrics** — search, govern, and execute trusted financial calculations across Excel, SQL, BI, and code.

MetricGraph indexes every financial function, metric, formula, SQL transformation, DAX measure, and backend calculation across your organization. It discovers conflicting definitions, builds an auditable metric catalog, and lets teams apply approved transformations to raw data.

## What the pilot proves

1. **Discover** — find where financial metrics are calculated across messy artifacts
2. **Detect conflicts** — flag conflicting time basis, fee treatment, deprecated logic, missing owners
3. **Execute** — apply an approved metric definition to raw CSV data with a full audit trail

## Architecture

```
Frontend (Next.js)
       ↓
FastAPI API
       ↓
Postgres + pgvector | MinIO/S3 | Redis/RQ Worker
       ↓
Parsers → Normalizer → LLM Labeling → Registry → Execution Engine (DuckDB + Python)
```

**Parse first, LLM second.** Artifacts are parsed deterministically; the LLM labels formulas, infers dimensions, explains diffs, and generates embeddings.

---

## External applications you must provision

MetricGraph requires these services. The repo ships a `docker-compose.yml` that runs all of them locally.

### 1. PostgreSQL 16 + pgvector

Stores the metric registry, formula index, clusters, issues, embeddings, and run audit logs.

| Variable | Example |
|----------|---------|
| `DATABASE_URL` | `postgresql+psycopg://metricgraph:metricgraph@localhost:5432/metricgraph` |

Docker image: `pgvector/pgvector:pg16`

After first boot, run migrations:
```bash
cd backend && alembic upgrade head
```

### 2. Redis

Job queue for background artifact parsing (RQ worker).

| Variable | Example |
|----------|---------|
| `REDIS_URL` | `redis://localhost:6379/0` |

### 3. MinIO or AWS S3

Object storage for uploaded artifacts, datasets, and execution results.

| Variable | Example |
|----------|---------|
| `S3_ENDPOINT` | `http://localhost:9000` |
| `S3_ACCESS_KEY` | `minioadmin` |
| `S3_SECRET_KEY` | `minioadmin` |
| `S3_BUCKET` | `metricgraph` |
| `S3_REGION` | `us-east-1` |
| `S3_USE_SSL` | `false` |

MinIO console: http://localhost:9001

For AWS S3, set `S3_ENDPOINT` to your bucket URL and provide IAM credentials.

### 4. OpenRouter (LLM)

Used for formula labeling and conflict explanations via OpenRouter's OpenAI-compatible chat API. Get a key at https://openrouter.ai/keys.

| Variable | Example |
|----------|---------|
| `OPENROUTER_API_KEY` | `sk-or-...` |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | `openai/gpt-4o-mini` (any OpenRouter model slug) |
| `OPENROUTER_SITE_URL` | `https://metricgraph.local` (sent as `HTTP-Referer`) |
| `OPENROUTER_APP_NAME` | `MetricGraph` (sent as `X-Title`) |

Without a key, parsing still works but LLM labeling falls back to deterministic defaults.

### 4b. Embeddings (optional, for semantic search)

OpenRouter does **not** provide an embeddings endpoint. To enable pgvector semantic search, supply a separate OpenAI-compatible embeddings provider. Leave it empty for keyword-only search.

| Variable | Example |
|----------|---------|
| `EMBEDDING_API_KEY` | `sk-...` (e.g. OpenAI) |
| `EMBEDDING_BASE_URL` | *(optional)* custom embeddings endpoint |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |

### 5. Docker + Docker Compose

Recommended for the pilot. Brings up all services with one command.

---

## Quick start (Docker)

```bash
cd metricgraph
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY

docker compose up --build
```

Services:
- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000
- **API docs**: http://localhost:8000/docs
- **MinIO console**: http://localhost:9001

### Seed demo data

After services are up, seed the investment-ops demo folder:

```bash
docker compose exec api python -m app.seed.run_seed /demo/investment_ops_demo
```

Wait for the worker to finish parsing (check logs: `docker compose logs worker -f`).

---

## Manual local setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
# Start Postgres, Redis, MinIO separately or via docker compose up postgres redis minio minio-init

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Worker (separate terminal)

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

---

## Pilot verification walkthrough

1. **Upload artifacts** — go to Upload, drop files from `demo/investment_ops_demo/` (or run seed command)
2. **Discovery dashboard** — see metric candidates, IRR clusters, issue counts
3. **Open IRR cluster** — click "Fund Net IRR" or similar to see 4 implementations side-by-side
4. **Issue dashboard** — review conflicting time basis, deprecated references, missing owners
5. **Metric registry** — open "Fund-Level Net IRR", review approved execution plan
6. **Apply metric** — upload `fund_cashflows.csv` and `fund_nav.csv`, select Fund-Level Net IRR, run
7. **Audit trail** — review computed IRR per fund, warnings, transformation plan used

Expected demo output:
```
Discovered N metric candidates across 6 artifacts.
IRR cluster: multiple implementations with conflicts detected.
Issues: conflicting time basis, deprecated formulas, missing owners.
Apply: Fund A/B/C net IRR with audit trail.
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/artifacts/upload` | Upload Excel/SQL/DAX/Python/CSV |
| GET | `/api/discovery/summary` | Discovery dashboard stats |
| GET | `/api/discovery/candidates` | Metric candidates |
| GET | `/api/clusters` | Formula clusters |
| GET | `/api/issues` | Governance issues |
| GET | `/api/search?q=` | Universal search |
| GET/POST | `/api/metrics` | Metric registry |
| POST | `/api/metrics/{id}/approve` | Approve canonical spec |
| GET | `/api/functions` | Function/transformation registry |
| POST | `/api/datasets/upload` | Upload raw CSV data |
| POST | `/api/metrics/{id}/run` | Execute approved metric |
| GET | `/api/runs/{id}/results` | Results + audit trail |
| GET | `/api/formulas/diff` | Formula diff with business impact |

---

## Project structure

```
metricgraph/
├── docker-compose.yml      # Postgres, Redis, MinIO, API, Worker, Frontend
├── .env.example            # All external service credentials
├── backend/
│   ├── app/
│   │   ├── parsers/        # Excel, SQL, DAX, Python, CSV
│   │   ├── normalizer/     # AST + dimension inference
│   │   ├── llm/            # OpenRouter labeling + optional embeddings
│   │   ├── discovery/      # Clustering + conflict detection
│   │   ├── execution/      # DuckDB + finance functions
│   │   ├── seed/           # Demo seed command
│   │   └── main.py         # FastAPI routes
│   ├── alembic/            # Database migrations
│   └── tests/
├── frontend/               # Next.js App Router UI
└── demo/investment_ops_demo/  # Pilot demo artifacts
```

---

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

---

## Out of scope (pilot)

- Live warehouse connectors (Snowflake, BigQuery)
- Enterprise SSO / permissions
- Real-time sync
- Automatic formula correction
- Full multi-tenant SaaS

---

## Positioning

> We help investment teams find every version of a financial metric, identify which one is correct, and safely apply the approved calculation to raw data.

MetricGraph sits on top of messy finance workflows — Excel models, SQL pipelines, BI dashboards, internal apps — and gives visibility without replacing existing systems.
