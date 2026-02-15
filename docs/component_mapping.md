# Component Mapping: TypeScript to Python

Every class, function, interface, and constant from `src/index.ts` mapped to its
Python equivalent.

## Type Definitions

| TS Interface | Python Module | Python Class |
|-------------|---------------|-------------|
| `Env` | N/A | `self.env` on WorkerEntrypoint (JS FFI) |
| `Document` | `src/models.py` | `Document(BaseModel)` |
| `ImageDocument` | `src/models.py` | `ImageDocument(Document)` |
| `Chunk` | `src/models.py` | `Chunk(BaseModel)` |
| `SearchResult` | `src/models.py` | `SearchResult(BaseModel)` |
| `HybridSearchResult` | `src/models.py` | `HybridSearchResult(SearchResult)` |
| (inline license type) | `src/models.py` | `License(BaseModel)` |
| (inline VectorizeVector) | `src/models.py` | `VectorRecord(BaseModel)` |
| (inline VectorMatch) | `src/models.py` | `VectorMatch(BaseModel)` |

## Engine Classes

| TS Class | Python Module | Python Class | Changes |
|----------|--------------|-------------|---------|
| `ChunkingEngine` | `src/chunking.py` | `ChunkingEngine` | Same algorithm. `re.split()` instead of JS regex. |
| `KeywordSearchEngine` | `src/keyword_search.py` | `KeywordSearchEngine` | Same BM25. Delegates D1 queries to `KeywordStore` protocol. |
| `HybridSearchEngine` | `src/hybrid_search.py` | `HybridSearchEngine` | Same RRF. `dict` with timestamp for cache. |
| `IngestionEngine` | `src/ingestion.py` | `IngestionEngine` | Same logic. Uses protocol abstractions for all bindings. |

## Functions

| TS Function | Python Module | Python Function |
|------------|--------------|----------------|
| `authenticate()` | `src/auth.py` | `authenticate()` |
| `corsHeaders()` | `src/auth.py` | `cors_headers()` |
| `getDashboardHTML()` | `src/dashboard.py` | `get_dashboard_html()` |
| `getLlmsTxt()` | `src/llms_txt.py` | `get_llms_txt()` |

## Entry Point

| TS | Python |
|----|--------|
| `export default { async fetch(request, env) }` | `class Default(WorkerEntrypoint): async def fetch(self, request)` |
| `env.VECTORIZE` | `self.env.VECTORIZE` via `CloudflareVectorStore` wrapper |
| `env.DB` | `self.env.DB` via `CloudflareD1KeywordStore` / `CloudflareD1LicenseStore` |
| `env.AI` | `self.env.AI` via `CloudflareAIProvider` |
| `env.MULTIMODAL` | `self.env.MULTIMODAL` via `CloudflareMultimodalProcessor` |
| `env.API_KEY` | `self.env.API_KEY` (direct access, string) |

## Protocol Layer (new in Python port)

| Protocol | Wraps | Default Implementation |
|----------|-------|----------------------|
| `VectorStore` | `env.VECTORIZE` | `CloudflareVectorStore` |
| `KeywordStore` | `env.DB` (keyword tables) | `CloudflareD1KeywordStore` |
| `AIProvider` | `env.AI` | `CloudflareAIProvider` |
| `ImageProcessor` | `env.MULTIMODAL` | `CloudflareMultimodalProcessor` |
| `LicenseStore` | `env.DB` (licenses table) | `CloudflareD1LicenseStore` |

## MCP Endpoints

| TS | Python |
|----|--------|
| `GET /mcp/tools` returns 4 tools | `GET /mcp/tools` returns 1 tool with 9 operations |
| `POST /mcp/call { tool: "search" }` | `POST /mcp/call { tool: "vectorize", arguments: { operation: "search" } }` |

## Constants

| TS Constant | Python Location | Value |
|------------|----------------|-------|
| `maxChunkSize = 512` | `ChunkingEngine.__init__` | `512` |
| `overlapPercent = 0.15` | `ChunkingEngine.__init__` | `0.15` |
| `minChunkSize = 100` | `ChunkingEngine.__init__` | `100` |
| `k1 = 1.2` | `KeywordSearchEngine.__init__` | `1.2` |
| `b = 0.75` | `KeywordSearchEngine.__init__` | `0.75` |
| `rrfK = 60` | `HybridSearchEngine.RRF_K` | `60` |
| `CACHE_TTL = 60000` (ms) | `HybridSearchEngine.CACHE_TTL` | `60.0` (seconds) |
| stop words `Set` | `keyword_search.STOP_WORDS` | Same `frozenset` |
