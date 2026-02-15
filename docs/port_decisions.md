# Port Decisions

This document records every significant decision made during the 1:1 port of
vectorize-mcp-worker from TypeScript to Python.

## Design Principle

Two sources, two concerns:

- **vectorize-mcp-worker** dictates *what* to build: features, endpoints, algorithms,
  Cloudflare infrastructure.
- **cerebrov2** dictates *how* to write it: coding style, module organization,
  protocol abstractions, error handling patterns.

## Runtime: Cloudflare Python Workers (Pyodide)

**Decision:** Deploy as a Cloudflare Worker using the Python Workers runtime, not
a standalone Python server.

**Rationale:** The original runs as a Cloudflare Worker with direct binding access
(`env.VECTORIZE`, `env.DB`, `env.AI`, `env.MULTIMODAL`). A standalone Python server
would need Cloudflare REST APIs, adding network latency and authentication complexity.
Python Workers use the same bindings via JS FFI (Pyodide), preserving the original's
in-process performance characteristics.

**Tradeoff:** Pyodide limits available packages to pure-Python or Pyodide-supported
libraries. This rules out sentence-transformers, numpy with C extensions, etc. -- but
since we use the same Cloudflare bindings, we don't need local alternatives.

## Protocol Abstraction Layer

**Decision:** Wrap every Cloudflare binding in a Python `Protocol` class. Business
logic depends only on protocols.

**Rationale (from cerebrov2 pattern):**

1. **JS FFI isolation** -- Binding calls return `JsProxy` objects. Conversion to/from
   Python types (`to_js()`, `.to_py()`) is centralized in binding wrappers, keeping
   business logic free of JS interop details.
2. **Testability** -- Unit tests mock the protocol, not the Cloudflare runtime. Tests
   run locally without `pywrangler dev`.
3. **Type safety** -- Pydantic models flow in and out of protocols. No raw JS objects
   in business logic.

**Tradeoff:** Adds ~200 LOC of wrapper code. Acceptable for testability and
maintainability gains.

## One MCP Tool with Operations (cerebrov2 pattern)

**Decision:** Expose one MCP tool named `vectorize` with an `operation` parameter
instead of the original's 4 separate tools.

**Rationale:** cerebrov2's `slack_query(operation=...)` pattern groups related
operations under a single tool with rich descriptions. This:

- Reduces tool count for LLM agents (less cognitive overhead)
- Provides a single entry point with self-documenting operations
- Makes the operation enum the natural dispatch mechanism

**What changed:** The original exposed `search`, `ingest`, `stats`, `delete` as
separate tools. The port consolidates these into 9 operations under one tool,
also adding license operations and image ingestion guidance.

## Pydantic Models for Data Types

**Decision:** Replace TypeScript interfaces with Pydantic BaseModel classes.

**Rationale (from cerebrov2):** Pydantic provides runtime validation, serialization,
and type safety. It's confirmed to work in Pyodide. The TS original uses interfaces
for compile-time checking only; Pydantic adds runtime guarantees.

## No Additional Dependencies

**Decision:** Only `pydantic` as a runtime dependency. Everything else comes from
the Cloudflare runtime or Python stdlib.

**What was NOT included and why:**

| Library | Why excluded |
|---------|-------------|
| structlog | No filesystem in Workers for JSON log files. Console logging via JS FFI. |
| httpx | Not needed -- use `fetch` via FFI for the MULTIMODAL service binding. |
| sentence-transformers | Not needed -- use `env.AI` for embeddings and reranking. |
| numpy | Not needed -- use `env.VECTORIZE` for vector operations. |
| aiosqlite | Not needed -- use `env.DB` (D1) for SQLite. |
| cachetools | Not needed -- plain dict with timestamp for TTL cache (same as TS `Map`). |
| FastMCP | Not compatible with Cloudflare Workers runtime. MCP is HTTP-based. |

## Business Logic: Identical Algorithms

Every algorithm is ported verbatim from the TypeScript original:

- **ChunkingEngine:** Paragraph-based, 512 char max, 15% overlap, 100 char min
- **BM25:** k1=1.2, b=0.75, same stop words, same tokenization rules
- **RRF:** k=60, same fusion formula
- **Reranker weighting:** 0.4 * RRF + 0.6 * reranker score
- **Cache TTL:** 60 seconds
- **License key format:** `lic_` + UUID hex

## Module Organization

**Decision:** Split the single `index.ts` (~1300 LOC) into focused modules.

**Rationale (from cerebrov2):** Single-responsibility modules are easier to test,
navigate, and maintain. The TS original was a single file because Cloudflare Workers
TypeScript traditionally used single-file workers. Python Workers support multi-file
projects natively.

**Mapping:** See `component_mapping.md` for the complete file-by-file mapping.

## Dashboard and llms.txt

**Decision:** Port the dashboard HTML and llms.txt verbatim.

**Rationale:** These are pure HTML/CSS/JS that work identically regardless of the
backend language. The only change is mentioning "Python Workers Runtime" in the tagline.
