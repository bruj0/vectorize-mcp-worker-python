# Production Deployment Guide

This document covers deploying and operating the Vectorize MCP Worker (Python) in production on Cloudflare's global edge network.

## Table of Contents

1. [Infrastructure Overview](#infrastructure-overview)
2. [Prerequisites](#prerequisites)
3. [Infrastructure Setup](#infrastructure-setup)
4. [Configuration](#configuration)
5. [Deployment](#deployment)
6. [Post-Deployment Verification](#post-deployment-verification)
7. [Security](#security)
8. [Monitoring & Observability](#monitoring--observability)
9. [Operations](#operations)
10. [Scaling & Limits](#scaling--limits)
11. [Troubleshooting](#troubleshooting)

---

## Infrastructure Overview

### Architecture

```mermaid
graph TB
    Client([Client / Browser])

    subgraph Cloudflare["Cloudflare Edge Network"]
        Worker["Main Worker<br/>(Python / Pyodide)"]
        Multimodal["Multimodal Worker<br/>(Python / Pyodide)"]

        subgraph AI["Workers AI"]
            BGE["BGE Small<br/>Embeddings (384d)"]
            Reranker["BGE Reranker<br/>Cross-Encoder"]
            Llama["Llama 4 Scout<br/>Vision + OCR"]
        end

        Vectorize[(Vectorize<br/>Vector Index)]
        D1[(D1<br/>SQLite Database)]
    end

    Client -->|HTTPS| Worker
    Worker -->|Service Binding| Multimodal
    Worker -->|Embedding + Reranking| BGE
    Worker -->|Embedding + Reranking| Reranker
    Multimodal -->|Vision + OCR + Embedding| Llama
    Multimodal -->|Embedding| BGE
    Worker -->|Vector search| Vectorize
    Worker -->|SQL queries| D1
```

### Search Request Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant W as Main Worker
    participant AI as Workers AI
    participant V as Vectorize
    participant D as D1 Database

    C->>W: POST /search/multimodal { query, topK, rerank }
    W->>AI: Generate embedding (BGE Small)
    AI-->>W: vector[384]

    par Vector Search
        W->>V: Query nearest neighbors (topK)
        V-->>W: vector results + scores
    and Keyword Search
        W->>D: BM25 keyword query
        D-->>W: keyword results + scores
    end

    Note over W: Reciprocal Rank Fusion

    opt rerank = true
        W->>AI: Cross-encoder rerank (BGE Reranker)
        AI-->>W: reranked scores
    end

    W-->>C: { results[], performance{} }
```

### Image Ingestion Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant W as Main Worker
    participant M as Multimodal Worker
    participant AI as Workers AI
    participant V as Vectorize
    participant D as D1 Database

    C->>W: POST /ingest/image (multipart)
    W->>M: Service Binding: image bytes + imageType
    M->>AI: Llama 4 Scout: describe image
    AI-->>M: description text
    M->>AI: Llama 4 Scout: OCR extraction
    AI-->>M: extracted text
    M->>AI: BGE Small: embed combined text
    AI-->>M: vector[384]
    M-->>W: { description, extractedText, vector }
    W->>V: Upsert vector + metadata
    W->>D: INSERT document record
    W-->>C: { success, description, extractedText }
```

### Deployment Flow

```mermaid
flowchart LR
    Code[Source Code] --> Build["Build<br/>(Pyodide bundle)"]
    Build --> Deploy["Deploy<br/>(wrangler deploy)"]
    Deploy --> Health{"/health/check<br/>Health Check"}
    Health -->|All bindings OK| Live["Live on<br/>Cloudflare Edge"]
    Health -->|Binding missing| Fix["Check config<br/>& secrets"]
    Fix --> Deploy
```

## Prerequisites

| Requirement | Purpose |
|-------------|---------|
| Cloudflare account (Workers Paid plan) | Workers Paid is required for Vectorize and D1 production usage |
| [wrangler](https://developers.cloudflare.com/workers/wrangler/) >= 3.x | CLI for managing Cloudflare resources |
| [uv](https://docs.astral.sh/uv/) | Python package manager |
| `workers-py` (via `uv tool install workers-py`) | Python Workers build toolchain |

Verify your setup:

```bash
wrangler --version        # >= 3.0
uv --version              # any recent version
wrangler whoami           # confirms you're authenticated
```

## Infrastructure Setup

The worker depends on four Cloudflare services:

| Service | Binding Name | Purpose |
|---------|-------------|---------|
| **Workers AI** | `AI` | Embedding (`bge-small-en-v1.5`), reranking (`bge-reranker-base`), vision (`llama-4-scout`) |
| **Vectorize** | `VECTORIZE` | 384-dimension cosine vector index for semantic search |
| **D1** | `DB` | SQLite database for documents, BM25 keywords, licenses |
| **Service Binding** | `MULTIMODAL` | Internal binding to a multimodal image processing worker |

### 1. Create the Vectorize Index

```bash
wrangler vectorize create mcp-knowledge-base \
  --dimensions=384 \
  --metric=cosine
```

### 2. Create the D1 Database

```bash
wrangler d1 create mcp-knowledge-db
```

Copy the `database_id` from the output.

### 3. Apply the Database Schema

```bash
wrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql
```

This creates five tables: `documents`, `keywords`, `doc_stats`, `term_stats`, and `licenses`. See `schema.sql` for the full DDL.

## Configuration

### wrangler.toml

Copy the example and fill in your values:

```bash
cp wrangler.toml.example wrangler.toml
```

Edit `wrangler.toml` and replace the D1 database ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "mcp-knowledge-db"
database_id = "your-actual-database-id"
```

### Secrets

Set the API key that protects write operations:

```bash
wrangler secret put API_KEY
```

Enter a strong, random value when prompted. This secret is:
- Stored encrypted in Cloudflare's infrastructure
- Never exposed in `wrangler.toml` or logs
- Required as a `Bearer` token for all non-public endpoints

Generate a strong key:

```bash
openssl rand -hex 32
```

### Environment-Specific Overrides

For staging vs production, use wrangler environments:

```toml
# wrangler.toml

[env.staging]
name = "vectorize-mcp-worker-python-staging"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "mcp-knowledge-db-staging"
database_id = "your-staging-db-id"

[[env.staging.vectorize]]
binding = "VECTORIZE"
index_name = "mcp-knowledge-base-staging"
```

Deploy to a specific environment:

```bash
uv run pywrangler deploy --env staging
```

## Deployment

### Deploy the Main Worker

```bash
uv run pywrangler deploy
```

This compiles the Python source via Pyodide, bundles it, and pushes it to Cloudflare's edge network. The worker is available globally within seconds.

> If the `[[services]]` block for `MULTIMODAL` is present in `wrangler.toml` and the multimodal worker hasn't been deployed yet, this will fail. Either deploy the multimodal worker first (see below) or comment out the binding until you need image features.

### Deploy the Multimodal Worker (optional -- for image features)

The `MULTIMODAL` service binding points to a separate worker (`multimodal-pro-worker/`) that handles image description, OCR, and embedding via Llama 4 Scout + BGE. It lives inside this repository.

```bash
cd multimodal-pro-worker
uv tool install workers-py    # if not already installed
uv run pywrangler deploy
cd ..
```

After deploying the multimodal worker, **redeploy the main worker** so Cloudflare can resolve the service binding:

```bash
uv run pywrangler deploy
```

If you don't need image features, comment out the `[[services]]` block in `wrangler.toml`:

```toml
# [[services]]
# binding = "MULTIMODAL"
# service = "multimodal-pro-worker"
```

Text features work normally without it; image endpoints (`/ingest/image`, `/search/similar-images`) return HTTP 501.

### Custom Domain

By default, the worker is accessible at `vectorize-mcp-worker-python.<your-subdomain>.workers.dev`. To use a custom domain:

1. Go to **Cloudflare Dashboard > Workers & Pages > your worker > Settings > Domains & Routes**
2. Add a custom domain (must be on a zone in your Cloudflare account)
3. Or add a route pattern like `api.yourdomain.com/v1/*`

### CI/CD Deployment

For automated deployments, use a `CLOUDFLARE_API_TOKEN` with the **Edit Cloudflare Workers** permission template:

```bash
# In your CI pipeline
export CLOUDFLARE_API_TOKEN="your-ci-token"
export CLOUDFLARE_ACCOUNT_ID="your-account-id"

# Deploy multimodal worker first (if using image features)
cd multimodal-pro-worker && uv run pywrangler deploy && cd ..

# Deploy main worker (must come after multimodal if service binding is enabled)
uv run pywrangler deploy
```

## Post-Deployment Verification

Run these checks after every production deployment:

### 1. Health Check

```bash
curl https://your-worker-url/health/check
```

Expected response:

```json
{
  "status": "healthy",
  "bindings": {
    "hasAI": true,
    "hasVectorize": true,
    "hasD1": true,
    "hasAPIKey": true
  },
  "mode": "production"
}
```

**Critical**: `mode` must be `"production"` (meaning `API_KEY` is set). If it shows `"development"`, your secret is missing and all endpoints are unprotected.

### 2. API Root

```bash
curl https://your-worker-url/
```

Verify the JSON response lists all endpoints and shows `"authentication": "required"`.

### 3. Stats Endpoint

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" https://your-worker-url/stats/index
```

### 4. Search Test

```bash
curl -X POST https://your-worker-url/search/multimodal \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"query": "test", "topK": 1}'
```

### 5. Dashboard

Open `https://your-worker-url/dashboard` in a browser. The interactive playground should load.

## Security

### Authentication Model

| Route | Auth Required | Description |
|-------|:------------:|-------------|
| `GET /` | No | API documentation (read-only) |
| `GET /health/check` | No | Health check |
| `GET /dashboard` | No | Interactive UI |
| `GET /llms.txt` | No | AI search engine info |
| All other routes | **Yes** | Bearer token required |

### Production Security Checklist

- [ ] **API_KEY is set** -- verify `/health/check` returns `"mode": "production"`
- [ ] **Strong API key** -- use at least 32 random hex characters
- [ ] **HTTPS only** -- Cloudflare Workers enforce HTTPS by default on `*.workers.dev`; verify custom domains use Full (Strict) SSL mode
- [ ] **CORS** -- the worker allows `Access-Control-Allow-Origin: *`. If you need to restrict origins, modify `cors_headers()` in `src/auth.py`
- [ ] **No secrets in git** -- `wrangler.toml` is in `.gitignore`; only `wrangler.toml.example` is committed
- [ ] **License system** -- if using the license endpoints, create license keys via `POST /license/create` and distribute them to authorized consumers

### Rotating the API Key

```bash
wrangler secret put API_KEY
# Enter new value
```

The new key takes effect immediately. Existing requests using the old key will receive `403 Forbidden`.

## Monitoring & Observability

### Live Logs with wrangler tail

The primary debugging tool. Stream real-time logs (Python tracebacks, request metadata, console output) from the deployed worker:

```bash
wrangler tail --format=json
```

Keep this running in a terminal while testing or after a deployment. Useful filters:

```bash
wrangler tail --format=json --status error    # only show errors
wrangler tail --format=json --method POST     # only POST requests
wrangler tail --format=json --search "search" # filter by path/content
```

### Built-in Observability

The worker has `[observability] enabled = true` in `wrangler.toml`. This enables:

- **Workers Analytics** in the Cloudflare dashboard (requests, errors, CPU time, duration)
- **Cloudflare Dashboard:** Workers & Pages > your worker > Logs tab for historical request logs

### Key Metrics to Watch

| Metric | Where | Alert Threshold |
|--------|-------|----------------|
| Error rate | Workers Analytics | > 1% of requests |
| P99 latency | Workers Analytics | > 5000ms |
| CPU time per request | Workers Analytics | Approaching 30s limit |
| D1 rows read/written | D1 Analytics | Approaching plan limits |
| Vectorize query count | Vectorize Analytics | Approaching plan limits |
| AI inference | Workers AI Analytics | Unexpected spikes |

### Performance Telemetry

Every `/search/multimodal` response includes a `performance` object:

```json
{
  "performance": {
    "embeddingTime": "45ms",
    "vectorSearchTime": "12ms",
    "keywordSearchTime": "8ms",
    "rerankerTime": "120ms",
    "totalTime": "195ms"
  }
}
```

Use this to identify bottlenecks. The reranker is typically the slowest step; disable it (`"rerank": false`) if latency is critical and precision can be traded off.

### Search Cache

The `HybridSearchEngine` maintains an in-memory cache with a 60-second TTL. Identical queries within the TTL window return `"totalTime": "0ms (cached)"`. Note that each Worker isolate has its own cache -- this is per-isolate, not global.

## Operations

### Ingesting Documents

```bash
curl -X POST https://your-worker-url/ingest/document \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "id": "doc-001",
    "content": "Your document text here...",
    "category": "docs",
    "title": "Getting Started"
  }'
```

Documents are automatically chunked (recursive splitting with 15% overlap) and indexed in both Vectorize (vector embeddings) and D1 (BM25 term frequencies).

### Ingesting Images

```bash
curl -X POST https://your-worker-url/ingest/image \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "id=img-001" \
  -F "image=@photo.jpg" \
  -F "category=images" \
  -F "title=Product Photo" \
  -F "imageType=photo"
```

Requires the `multimodal-pro-worker` to be deployed and the `MULTIMODAL` service binding configured.

The image processing pipeline:
1. Main worker sends image bytes to `multimodal-pro-worker` via Service Binding
2. Multimodal worker runs Llama 4 Scout for description (prompt varies by `imageType`)
3. Multimodal worker runs Llama 4 Scout for OCR text extraction
4. Multimodal worker generates BGE embedding (384d) from combined text
5. Main worker stores description + OCR in D1 and vector in Vectorize

Supported `imageType` values: `screenshot`, `diagram`, `document`, `chart`, `photo`, `auto` (default).

### Deleting Documents

```bash
curl -X DELETE https://your-worker-url/delete/document/doc-001 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

This removes the document from both Vectorize and D1.

### Database Migrations

To modify the D1 schema:

1. Write your migration SQL
2. Apply it to staging first:
   ```bash
   wrangler d1 execute mcp-knowledge-db-staging --remote --file=./migration.sql
   ```
3. Verify, then apply to production:
   ```bash
   wrangler d1 execute mcp-knowledge-db --remote --file=./migration.sql
   ```

### Backup & Restore

Export the D1 database for backup:

```bash
# Use the D1 HTTP API or Cloudflare dashboard to export
wrangler d1 export mcp-knowledge-db --remote --output=backup.sql
```

Note: Vectorize indexes cannot be exported. If you need disaster recovery, keep a record of all ingested documents so you can re-ingest them.

## Scaling & Limits

### Cloudflare Workers Limits (Paid Plan)

| Resource | Limit |
|----------|-------|
| Request duration (CPU time) | 30 seconds |
| Memory per isolate | 128 MB |
| Script size (after bundling) | 10 MB |
| Subrequests per request | 1,000 |
| Concurrent connections | Unlimited (auto-scaled) |

### Vectorize Limits

| Resource | Limit |
|----------|-------|
| Vectors per index | 5,000,000 |
| Dimensions | 384 (configured) |
| Metadata per vector | 10 KB |
| Queries per second | ~1,000 (soft limit, auto-scales) |

### D1 Limits (Paid Plan)

| Resource | Limit |
|----------|-------|
| Database size | 10 GB |
| Rows read per day | 25 billion |
| Rows written per day | 50 million |
| Max query result size | 20 MB |

### Workers AI

Workers AI uses a neuron-based billing model. Key models used:

| Model | Purpose | Relative Cost |
|-------|---------|--------------|
| `@cf/baai/bge-small-en-v1.5` | Text embeddings (384d) | Low |
| `@cf/baai/bge-reranker-base` | Cross-encoder reranking | Medium |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | Image description (vision) | High |

To reduce costs:
- Set `"rerank": false` in search requests when approximate ranking is acceptable
- Avoid ingesting images unless the multimodal features are needed
- The 60-second search cache prevents redundant AI calls for repeated queries

## Troubleshooting

### Worker Returns 500 Errors

1. Check live logs: `wrangler tail --format=json`
2. Verify bindings: `curl https://your-worker-url/health/check` -- check that all bindings are `true`
3. Check D1 connectivity separately: the health check runs `SELECT 1` against D1

### "mode": "development" in Production

The `API_KEY` secret is not set. Fix:

```bash
wrangler secret put API_KEY
```

### Search Returns Empty Results

1. Check index stats: `GET /stats/index` -- verify `vectorCount > 0`
2. Ingest a test document and search for its content
3. Verify the Vectorize index name in `wrangler.toml` matches the one you created

### Module Import Errors (Pyodide)

The Python Workers runtime (Pyodide) treats `src/` as the module root. All imports must be relative to `src/`, not include the `src.` prefix. For example:

```python
# Correct
from auth import authenticate
from bindings.ai import CloudflareAIProvider

# Wrong -- will cause ModuleNotFoundError
from src.auth import authenticate
```

### D1 Schema Out of Sync

If you see SQL errors about missing tables or columns:

```bash
wrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql
```

The schema uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`, so it's safe to re-run.

### Deploy Fails: "Could not resolve service binding 'MULTIMODAL'"

The `multimodal-pro-worker` has not been deployed yet, but the main worker's `wrangler.toml` references it as a service binding. Two options:

1. **Deploy the multimodal worker first:**
   ```bash
   cd multimodal-pro-worker && uv run pywrangler deploy && cd ..
   ```

2. **Comment out the binding** if you don't need image features:
   ```toml
   # [[services]]
   # binding = "MULTIMODAL"
   # service = "multimodal-pro-worker"
   ```

### Image Endpoints Return 501

The `/ingest/image` and `/search/similar-images` endpoints return HTTP 501 when the `MULTIMODAL` service binding is not configured. Deploy `multimodal-pro-worker` and ensure the `[[services]]` block is uncommented in `wrangler.toml`.

### High Latency

1. Check the `performance` object in search responses to identify the slow step
2. Reranking (`rerankerTime`) is usually the bottleneck -- disable with `"rerank": false`
3. Reduce `topK` to limit the number of results processed
4. Repeated queries benefit from the 60-second cache
5. Image ingestion takes ~7-8s due to two Llama 4 Scout calls (description + OCR) plus embedding -- this is expected

## Automated E2E Monitoring

The project includes an E2E benchmark suite that can be run on a schedule to detect performance regressions in production:

```bash
# Run benchmarks against production worker
VECTORIZE_E2E_URL=https://your-worker.workers.dev \
VECTORIZE_E2E_API_KEY=your-api-key \
uv run pytest tests/e2e/ -m benchmark -v
```

Results are persisted to `tests/e2e/benchmark_results.json`. On each run, the framework compares current p50 latencies against historical baselines and flags any operations that are >20% slower as regressions.

This can be integrated into CI/CD to block deploys when performance degrades.
