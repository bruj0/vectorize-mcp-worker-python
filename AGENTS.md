# AGENTS.md -- AI Agent Guide for vectorize-mcp-worker-python

## What Is This Repo

It is a **Cloudflare Python Worker** that provides hybrid RAG (Retrieval-Augmented Generation) with multimodal image support, deployed on Cloudflare's edge network using the Python Workers runtime (Pyodide).

## Runtime & Deployment

- **Runtime:** Cloudflare Python Workers (Pyodide). NOT a standalone Python server.
- **Entry point:** `src/entry.py` -- class `Default(WorkerEntrypoint)` with `async def fetch(self, request)`.
- **Config:** `wrangler.toml` (gitignored). Copy `wrangler.toml.example` to get started.
- **CLI:** Use `pywrangler` (via `uv run pywrangler`) for dev/deploy: `uv run pywrangler dev`, `uv run pywrangler deploy`.
- **Secrets:** `wrangler secret put API_KEY` -- never commit secrets.

## Critical: Import Paths

The Pyodide runtime treats `src/` as the Python module root (because `wrangler.toml` sets `main = "src/entry.py"`). **All imports must be relative to `src/`**, never prefixed with `src.`:

```python
# Correct
from auth import authenticate
from bindings.ai import CloudflareAIProvider

# WRONG -- causes ModuleNotFoundError at runtime
from src.auth import authenticate
from src.bindings.ai import CloudflareAIProvider
```

## Cloudflare Bindings

All infrastructure is Cloudflare-native, accessed via `self.env` in the Worker:

| Binding | Variable | Purpose |
|---------|----------|---------|
| Workers AI | `env.AI` | Embeddings (`@cf/baai/bge-small-en-v1.5`, 384 dims) and reranking (`@cf/baai/bge-reranker-base`) |
| Vectorize | `env.VECTORIZE` | Vector similarity search (index: `mcp-knowledge-base`) |
| D1 | `env.DB` | SQLite for BM25 keyword index + licenses (database: `mcp-knowledge-db`) |
| Service Binding | `env.MULTIMODAL` | Calls `multimodal-pro-worker` for image processing (Llama 4 Scout) |
| Secret | `env.API_KEY` | Bearer token auth. If unset, runs in dev mode (no auth). |

## Architecture

```
HTTP Request
    │
    ▼
src/entry.py (WorkerEntrypoint -- routing, CORS, auth)
    │
    ├── src/hybrid_search.py (Vector + BM25 → RRF → optional reranking)
    ├── src/ingestion.py (text chunking + image processing → D1 + Vectorize)
    ├── src/keyword_search.py (BM25 scoring engine)
    ├── src/chunking.py (paragraph-based, 512 chars, 15% overlap)
    ├── src/auth.py (Bearer token + public routes + CORS)
    ├── src/dashboard.py (HTML UI)
    └── src/llms_txt.py (AI search metadata -- AUTO-GENERATED, do not edit directly)
    │
    ▼
src/protocols.py (5 Protocol interfaces)
    │
    ▼
src/bindings/ (JS FFI wrappers for Cloudflare bindings)
    ├── vectorize.py (CloudflareVectorStore)
    ├── d1.py (CloudflareD1KeywordStore + CloudflareD1LicenseStore + CloudflareD1SettingsStore)
    ├── ai.py (CloudflareAIProvider)
    ├── multimodal.py (CloudflareMultimodalProcessor → calls multimodal-pro-worker)
    └── ffi_utils.py (to_js / js_to_dict helpers)

multimodal-pro-worker/ (separate Cloudflare Worker, deployed independently)
    └── src/entry.py (POST /describe-image → Llama 4 Scout + BGE embedding)
```

## Multimodal Pro Worker

A **separate** Python Worker at `multimodal-pro-worker/` that handles image processing. Connected to the main worker via a Cloudflare Service Binding (`env.MULTIMODAL`).

**Single endpoint:** `POST /describe-image`

Pipeline: image → Llama 4 Scout (description) → Llama 4 Scout (OCR) → BGE embedding (384d) → JSON response.

**Deploy separately before enabling image features:**

```bash
cd multimodal-pro-worker
uv tool install workers-py    # if not already installed
uv run pywrangler deploy
```

The MULTIMODAL binding in `src/entry.py` is optional: if missing, text features work normally; image endpoints (`/ingest/image`, `/search/similar-images`) return 501.

## Key Design Patterns

### Protocol Abstraction Layer

Every Cloudflare binding is wrapped in a `typing.Protocol` (in `src/protocols.py`). Business logic **never** touches raw JS objects or bindings directly. Binding wrappers in `src/bindings/` handle all JS FFI conversions (`to_js()`, `.to_py()`).

**Protocols:** `VectorStore`, `KeywordStore`, `AIProvider`, `ImageProcessor`, `LicenseStore`.

### JS FFI Pattern

Python Workers use Pyodide FFI. The canonical conversion:

```python
from js import Object
from pyodide.ffi import to_js as _to_js

def to_js(obj):
    return _to_js(obj, dict_converter=Object.fromEntries)
```

Use `Object.fromEntries` for dicts (Cloudflare bindings expect plain JS Objects, not Maps).

### MCP Integration (via vectorize-mcp-tool)

All MCP operations go through the `vectorize-mcp-tool` package (in `vectorize-mcp-tool/`). There are **no** `/mcp/*` endpoints on the worker. The MCP tool dispatches directly to the worker's REST endpoints.

The tool exposes ONE FastMCP tool named `vectorize` with an `operation` parameter. Operations: `search_multimodal`, `search_documents`, `ingest`, `ingest_image`, `stats`, `delete`, `get_document`, `get_image`, `list_documents`, `license_validate`, `license_create`, `license_list`, `license_revoke`, `delete_license`, `reset_all`, `reset_documents`, `reset_licenses`.

The canonical metadata for all operations, parameters, and endpoints lives in `vectorize-mcp-tool/src/vectorize_mcp_tool/metadata.py`.

### Generated File: src/llms_txt.py

`src/llms_txt.py` is **auto-generated** from `vectorize-mcp-tool/src/vectorize_mcp_tool/metadata.py`. Do **not** edit it directly. To regenerate:

```bash
cd vectorize-mcp-tool && uv run python ../scripts/generate_llms_txt.py
```

A contract test (`tests/integration/test_llms_txt_contract.py`) will fail if the file is stale.

### Pydantic Models

All data types in `src/models.py` as Pydantic `BaseModel` classes. Confirmed to work in Pyodide. Models: `Document`, `ImageDocument`, `Chunk`, `SearchResult`, `HybridSearchResult`, `VectorRecord`, `VectorMatch`, `IndexStats`, `ImageDescription`, `License`, `DocStats`, `KeywordRow`.

## Algorithm Constants (identical to TS original)

| Constant | Value | Location |
|----------|-------|----------|
| Max chunk size | 512 chars | `ChunkingEngine.__init__` |
| Chunk overlap | 15% | `ChunkingEngine.__init__` |
| Min chunk size | 100 chars | `ChunkingEngine.__init__` |
| BM25 k1 | 1.2 | `KeywordSearchEngine.__init__` |
| BM25 b | 0.75 | `KeywordSearchEngine.__init__` |
| RRF k | 60 | `HybridSearchEngine.RRF_K` |
| Reranker weighting | 0.4 RRF + 0.6 reranker | `HybridSearchEngine.search` |
| Cache TTL | 60 seconds | `HybridSearchEngine.CACHE_TTL` |
| Embedding dimensions | 384 | `@cf/baai/bge-small-en-v1.5` |

## HTTP Endpoints

All endpoints follow the `/operation/target` naming convention (see below).

| Endpoint | Method | Auth Required | Handler |
|----------|--------|---------------|---------|
| `/` | GET | No | API documentation JSON |
| `/health/check` | GET | No | Health check |
| `/dashboard` | GET | No | Interactive HTML playground |
| `/llms.txt` | GET | No | AI search engine info |
| `/stats/index` | GET | Yes | Index statistics |
| `/search/multimodal` | POST | Yes | Hybrid search (docs + images, snippet + metadata) |
| `/search/documents` | POST | Yes | Hybrid search (documents only, snippet + metadata) |
| `/search/similar-images` | POST | Yes | Visual similarity search (image file input) |
| `/ingest/document` | POST | Yes | Document ingestion with auto-chunking |
| `/ingest/image` | POST | Yes | Image ingestion (multipart form) |
| `/get/document/:id` | GET | Yes | Get full document by ID |
| `/get/image/:id` | GET | Yes | Get full image document by ID |
| `/list/documents` | GET | Yes | List documents with pagination |
| `/delete/document/:id` | DELETE | Yes | Delete document by ID |
| `/delete/license/:key` | DELETE | Yes | Delete license by key |
| `/init/reset-passphrase` | POST | Yes | Set/rotate reset passphrase |
| `/reset/all` | POST | Yes | Wipe all databases (requires passphrase) |
| `/reset/documents` | POST | Yes | Wipe documents + vectors (requires passphrase) |
| `/reset/licenses` | POST | Yes | Wipe licenses (requires passphrase) |
| `/license/validate` | POST | Yes | Validate license key |
| `/license/create` | POST | Yes | Create license |
| `/license/list` | GET | Yes | List licenses |
| `/license/revoke` | POST | Yes | Revoke license |

### Search Result Format

All `/search/*` endpoints return **snippets** (truncated content, default 200 chars) plus full metadata instead of full document content. Use `GET /get/document/:id` or `GET /get/image/:id` to retrieve full content. Request body accepts optional `snippetLength` (50-500) to control snippet size.

### Reset Passphrase

All `/reset/*` endpoints require a passphrase in the request body. The passphrase must first be configured via `POST /init/reset-passphrase`. This prevents accidental data deletion by AI agents.

## Database Schema

`schema.sql` defines 6 tables in D1: `documents`, `keywords`, `doc_stats`, `term_stats`, `licenses`, `settings`. Run with: `wrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql`.

## Testing

```bash
# Unit tests -- no network, fast (tests all business logic)
uv run pytest tests/unit/ -v --cov=src --cov-report=term-missing

# Integration/contract tests -- verify worker <-> MCP tool sync
uv run pytest tests/integration/ -v

# MCP tool tests (separate venv)
cd vectorize-mcp-tool && uv run pytest tests/ -v

# E2E tests against live worker
VECTORIZE_E2E_URL=https://... VECTORIZE_E2E_API_KEY=... uv run pytest tests/e2e/ -m "not benchmark"

# Benchmarks (persists results to tests/e2e/benchmark_results.json)
VECTORIZE_E2E_URL=https://... VECTORIZE_E2E_API_KEY=... uv run pytest tests/e2e/ -m benchmark
```

### Test Architecture

| Directory | Purpose | Network Required |
|-----------|---------|:----------------:|
| `tests/unit/` | Business logic, models, auth, multipart, multimodal binding | No |
| `tests/integration/` | Contract tests: worker endpoints match MCP tool, multimodal worker matches binding, llms.txt freshness | No |
| `tests/e2e/` | Full flows + benchmarking against live worker | Yes |
| `vectorize-mcp-tool/tests/` | CLI structure, HTTP client, MCP server dispatch + validation | No |

Tests use stubs (`tests/stubs/workers.py`, `tests/stubs/js.py`, `tests/stubs/pyodide/`) for imports that normally require the Cloudflare runtime. The `tests/conftest.py` adds these stubs and `src/` to `sys.path` automatically.

**What's testable locally:** auth, models, chunking, tokenization, BM25 scoring, RRF fusion, MCP tool dispatch + validation (in vectorize-mcp-tool/tests/), ingestion engine, hybrid search engine, multipart parsing, multimodal binding, logger, endpoint contract sync, llms.txt freshness.

**What requires a live worker:** full search/ingest flows, image processing, performance benchmarks.

## Dependencies

**Runtime (in Pyodide):** Only `pydantic>=2.0`. Everything else is from Cloudflare runtime or Python stdlib.

**Dev (local):** `workers-py`, `workers-runtime-sdk`, `pytest`, `pytest-asyncio`, `ruff`.

**NOT used and why:** No `structlog` (no filesystem), no `httpx` (use FFI `fetch`), no `sentence-transformers` (use `env.AI`), no `numpy` (use `env.VECTORIZE`), no `aiosqlite` (use `env.DB`), no `FastMCP` (incompatible with Workers runtime).

## File Conventions

- Snake_case for all Python files and functions.
- Pydantic models in `src/models.py`, protocols in `src/protocols.py`.
- One binding wrapper per file in `src/bindings/`.
- Business logic engines as classes with methods that take protocol implementations as parameters.
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`, E2E tests in `tests/e2e/`.
- MCP tool tests in `vectorize-mcp-tool/tests/`.

### Endpoint Naming Convention

All HTTP endpoints follow the `/operation/target` pattern:

- **Operation**: the verb/action (`search`, `ingest`, `delete`, `reset`, `list`, `get`, `init`)
- **Target**: the resource being acted upon (`document`, `image`, `documents`, `licenses`)
- **Examples**: `POST /ingest/document`, `POST /search/documents`, `DELETE /delete/document/:id`
- **Exceptions**: `/`, `/dashboard`, `/llms.txt` (root-level utility routes)
- **Sub-resources**: license endpoints use `/license/{action}` (resource-first grouping)

When adding new endpoints, always follow this pattern. Never use kebab-case for multi-word paths (use `/search/similar-images` not `/find-similar-images`).

## Documentation

All documentation (besides `README.md`) lives in `docs/`. Never place standalone `.md` docs in the project root.

| Document | Purpose |
|----------|---------|
| `docs/quickstart.md` | Step-by-step first-time setup guide |
| `docs/production.md` | Production deployment, security, monitoring, operations |
| `docs/port_decisions.md` | Rationale for every design choice |
| `docs/component_mapping.md` | Complete TS-to-Python file/class/function mapping |
| `docs/abstraction_layers.md` | Protocol design, FFI patterns, testing without runtime |

## Configuration Files

| File | Tracked | Purpose |
|------|:-------:|---------|
| `wrangler.toml.example` | Yes | Template with placeholder values -- commit this |
| `wrangler.toml` | **No** (gitignored) | Local/production config with real DB IDs -- never commit |
| `multimodal-pro-worker/wrangler.toml` | Yes | Multimodal worker config (no secrets, safe to commit) |
| `.dev.vars` | **No** (gitignored) | Local development environment variables |
| `.env` | **No** (gitignored) | Environment variables |
| `schema.sql` | Yes | D1 database DDL (safe to re-run, uses IF NOT EXISTS) |

## Common Tasks

### Add a new HTTP endpoint
1. Follow the `/operation/target` naming convention (see Endpoint Naming Convention above).
2. Add route in `src/entry.py` in the `fetch()` method.
3. If it needs a new protocol method, add to `src/protocols.py` and implement in the relevant `src/bindings/` file.
4. Update the root `/` endpoint documentation JSON, AGENTS.md, and docs.

### Add a new MCP operation
1. Add the operation to `OPERATIONS` and any new parameters to `PARAMETERS` in `vectorize-mcp-tool/src/vectorize_mcp_tool/metadata.py`.
2. Add the corresponding REST endpoint handler in `src/entry.py`.
3. Add the client method in `vectorize-mcp-tool/src/vectorize_mcp_tool/client.py`.
4. Add the dispatch branch in `vectorize-mcp-tool/src/vectorize_mcp_tool/server.py`.
5. Regenerate `src/llms_txt.py`: `cd vectorize-mcp-tool && uv run python ../scripts/generate_llms_txt.py`
6. Add tests in `vectorize-mcp-tool/tests/test_server.py`.

### Change an algorithm parameter
All constants are in the engine class `__init__` or as class attributes. The values must stay identical to the TS original unless intentionally diverging.

### Swap a binding implementation
Implement the protocol from `src/protocols.py` and inject in `src/entry.py`. Business logic is unaffected.
