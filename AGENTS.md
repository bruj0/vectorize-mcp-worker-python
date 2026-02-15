# AGENTS.md -- AI Agent Guide for vectorize-mcp-worker-python

## What Is This Repo

A 1:1 Python port of [vectorize-mcp-worker](https://github.com/dannwaneri/vectorize-mcp-worker) (TypeScript). It is a **Cloudflare Python Worker** that provides hybrid RAG (Retrieval-Augmented Generation) with multimodal image support, deployed on Cloudflare's edge network using the Python Workers runtime (Pyodide).

**Two sources, two concerns:**
- The original TypeScript worker defines *what* the code does (features, algorithms, endpoints, infrastructure).
- [cerebrov2](https://github.com/bruj0/cerebrov2) defines *how* the Python code is written (Pydantic models, Protocol abstractions, module organization, one-MCP-tool-with-operations pattern).

## Runtime & Deployment

- **Runtime:** Cloudflare Python Workers (Pyodide). NOT a standalone Python server.
- **Entry point:** `src/entry.py` -- class `Default(WorkerEntrypoint)` with `async def fetch(self, request)`.
- **Config:** `wrangler.toml` with `compatibility_flags = ["python_workers"]`.
- **CLI:** Use `pywrangler` (not `wrangler`) for dev/deploy: `pywrangler dev`, `pywrangler deploy`.
- **Secrets:** `pywrangler secret put API_KEY` -- never commit secrets.

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
    ├── src/mcp.py (MCP: single "vectorize" tool with 9 operations)
    ├── src/hybrid_search.py (Vector + BM25 → RRF → optional reranking)
    ├── src/ingestion.py (text chunking + image processing → D1 + Vectorize)
    ├── src/keyword_search.py (BM25 scoring engine)
    ├── src/chunking.py (paragraph-based, 512 chars, 15% overlap)
    ├── src/auth.py (Bearer token + public routes + CORS)
    ├── src/dashboard.py (HTML UI)
    └── src/llms_txt.py (AI search metadata)
    │
    ▼
src/protocols.py (5 Protocol interfaces)
    │
    ▼
src/bindings/ (JS FFI wrappers for Cloudflare bindings)
    ├── vectorize.py (CloudflareVectorStore)
    ├── d1.py (CloudflareD1KeywordStore + CloudflareD1LicenseStore)
    ├── ai.py (CloudflareAIProvider)
    ├── multimodal.py (CloudflareMultimodalProcessor)
    └── ffi_utils.py (to_js / js_to_dict helpers)
```

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

### One MCP Tool with Operations

The MCP layer exposes ONE tool named `vectorize` with an `operation` parameter (cerebrov2 pattern). Operations: `search`, `ingest`, `ingest_image`, `stats`, `delete`, `license_validate`, `license_create`, `license_list`, `license_revoke`.

Endpoint: `POST /mcp/call` with body `{ "tool": "vectorize", "arguments": { "operation": "search", "query": "..." } }`.

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

| Endpoint | Method | Auth Required | Handler |
|----------|--------|---------------|---------|
| `/` | GET | No | API documentation JSON |
| `/test` | GET | No | Health check |
| `/dashboard` | GET | No | Interactive HTML playground |
| `/llms.txt` | GET | No | AI search engine info |
| `/mcp/tools` | GET | No | MCP tool schema |
| `/stats` | GET | Yes | Index statistics |
| `/search` | POST | Yes | Hybrid search |
| `/ingest` | POST | Yes | Document ingestion |
| `/ingest-image` | POST | Yes | Image ingestion (multipart form) |
| `/documents/:id` | DELETE | Yes | Delete document |
| `/license/validate` | POST | Yes | Validate license key |
| `/license/create` | POST | Yes | Create license |
| `/license/list` | GET | Yes | List licenses |
| `/license/revoke` | POST | Yes | Revoke license |
| `/mcp/call` | POST | Yes | Execute MCP tool |
| `/find-similar-images` | POST | Yes | Visual similarity search |

## Database Schema

`schema.sql` defines 5 tables in D1: `documents`, `keywords`, `doc_stats`, `term_stats`, `licenses`. Run with: `pywrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql`.

## Testing

```bash
# Install deps
uv venv .venv && source .venv/bin/activate
uv pip install pydantic pytest pytest-asyncio

# Run all unit tests (no Cloudflare runtime needed)
pytest tests/ -v
```

Tests use a `workers` stub (`tests/stubs/workers.py`) for imports that normally require the Cloudflare runtime. The `tests/conftest.py` adds this stub to `sys.path` automatically.

**What's testable locally:** chunking, tokenization, BM25 scoring, RRF fusion, MCP schema validation, dispatch argument validation.

**What requires `pywrangler dev`:** anything that touches Cloudflare bindings (search, ingest, image processing, licenses).

## Dependencies

**Runtime (in Pyodide):** Only `pydantic>=2.0`. Everything else is from Cloudflare runtime or Python stdlib.

**Dev (local):** `workers-py`, `workers-runtime-sdk`, `pytest`, `pytest-asyncio`, `ruff`.

**NOT used and why:** No `structlog` (no filesystem), no `httpx` (use FFI `fetch`), no `sentence-transformers` (use `env.AI`), no `numpy` (use `env.VECTORIZE`), no `aiosqlite` (use `env.DB`), no `FastMCP` (incompatible with Workers runtime).

## File Conventions

- Snake_case for all Python files and functions.
- Pydantic models in `src/models.py`, protocols in `src/protocols.py`.
- One binding wrapper per file in `src/bindings/`.
- Business logic engines as classes with methods that take protocol implementations as parameters.
- Tests in `tests/unit/` for pure-Python logic.

## Documentation

- `docs/port_decisions.md` -- Rationale for every design choice.
- `docs/component_mapping.md` -- Complete TS-to-Python file/class/function mapping.
- `docs/abstraction_layers.md` -- Protocol design, FFI patterns, testing without runtime.

## Common Tasks

### Add a new HTTP endpoint
1. Add route in `src/entry.py` in the `fetch()` method.
2. If it needs a new protocol method, add to `src/protocols.py` and implement in the relevant `src/bindings/` file.

### Add a new MCP operation
1. Add to the `TOOL_SCHEMA` enum and properties in `src/mcp.py`.
2. Add the `elif operation == "..."` handler in `dispatch_mcp_call()`.

### Change an algorithm parameter
All constants are in the engine class `__init__` or as class attributes. The values must stay identical to the TS original unless intentionally diverging.

### Swap a binding implementation
Implement the protocol from `src/protocols.py` and inject in `src/entry.py`. Business logic is unaffected.
