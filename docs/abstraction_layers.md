# Abstraction Layers

This document explains the protocol abstraction layer, how each protocol wraps a
Cloudflare binding, the JS FFI conversion patterns, and how to test business logic
without the Cloudflare runtime.

## Architecture

```
MCP Tools / HTTP Endpoints
         |
    Business Logic (ChunkingEngine, HybridSearchEngine, IngestionEngine)
         |
    Protocols (VectorStore, KeywordStore, AIProvider, ImageProcessor, LicenseStore)
         |
    Binding Wrappers (CloudflareVectorStore, CloudflareD1KeywordStore, etc.)
         |
    Cloudflare Bindings via JS FFI (env.VECTORIZE, env.DB, env.AI, env.MULTIMODAL)
```

Business logic never touches raw JS objects or Cloudflare bindings directly.
It only calls protocol methods that accept and return Python types (Pydantic models,
lists, dicts, strings).

## Protocol Definitions

All protocols live in `src/protocols.py` using `typing.Protocol` with
`@runtime_checkable`. Each protocol maps 1:1 to a Cloudflare binding.

### VectorStore (wraps env.VECTORIZE)

```python
class VectorStore(Protocol):
    async def upsert(self, vectors: list[VectorRecord]) -> None: ...
    async def query(self, embedding: list[float], top_k: int, return_metadata: bool = True) -> list[VectorMatch]: ...
    async def delete_by_ids(self, ids: list[str]) -> None: ...
    async def describe(self) -> IndexStats: ...
```

### KeywordStore (wraps env.DB keyword tables)

```python
class KeywordStore(Protocol):
    async def index_document(self, doc_id, content, title, source, category, chunk_index, parent_id, word_count, is_image, terms) -> None: ...
    async def search(self, tokens: list[str], top_k: int) -> tuple[DocStats | None, list[KeywordRow]]: ...
    async def delete_document(self, doc_id: str) -> list[str]: ...
    async def get_doc_stats(self) -> DocStats | None: ...
    async def document_exists(self, doc_id: str) -> bool: ...
    async def update_doc_stats_increment(self, token_count: int) -> None: ...
```

### AIProvider (wraps env.AI)

```python
class AIProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    async def rerank(self, query: str, contexts: list[str]) -> list[float]: ...
```

### ImageProcessor (wraps env.MULTIMODAL)

```python
class ImageProcessor(Protocol):
    async def describe_image(self, image_buffer: bytes, image_type: str = "auto", prompt: str | None = None) -> ImageDescription: ...
```

### LicenseStore (wraps env.DB licenses table)

```python
class LicenseStore(Protocol):
    async def validate(self, license_key: str) -> License | None: ...
    async def create(self, email: str, plan: str = "standard", max_documents: int | None = None, max_queries_per_day: int | None = None) -> License: ...
    async def list_all(self, limit: int = 100) -> list[License]: ...
    async def revoke(self, license_key: str) -> bool: ...
```

## JS FFI Conversion Patterns

Cloudflare Python Workers use Pyodide's Foreign Function Interface to call JS
binding APIs. The `src/bindings/ffi_utils.py` module centralizes conversion helpers.

### Python to JS

```python
from js import Object
from pyodide.ffi import to_js as _to_js

def to_js(obj):
    """Convert Python dict/list to JS Object/Array.

    Uses Object.fromEntries for dicts (not Map) because
    Cloudflare bindings expect plain JS Objects.
    """
    return _to_js(obj, dict_converter=Object.fromEntries)
```

**Usage in binding wrappers:**

```python
# Upsert vectors -- convert list of dicts to JS array of objects
js_vectors = to_js([{"id": v.id, "values": v.values, "metadata": v.metadata} for v in vectors])
await self._binding.upsert(js_vectors)

# Query options -- convert dict to JS object
js_options = to_js({"topK": top_k, "returnMetadata": True})
```

### JS to Python

JsProxy objects expose `.to_py()` for automatic conversion. For complex objects,
access properties directly:

```python
# Iterating JS arrays
for i in range(js_matches.length):
    m = js_matches[i]
    matches.append(VectorMatch(
        id=str(m.id),
        score=float(m.score),
        metadata=m.metadata.to_py() if m.metadata else {},
    ))

# Accessing D1 query results
row = await self._db.prepare("SELECT * FROM ...").first()
value = str(row.column_name)  # JsProxy property access
```

## Testing Without Cloudflare Runtime

The protocol layer enables testing business logic with mock implementations.

### Mock Protocol Example

```python
class MockVectorStore:
    """In-memory mock for testing."""

    def __init__(self):
        self.vectors = {}

    async def upsert(self, vectors):
        for v in vectors:
            self.vectors[v.id] = v

    async def query(self, embedding, top_k, return_metadata=True):
        # Return empty results for testing
        return []

    async def delete_by_ids(self, ids):
        for id_ in ids:
            self.vectors.pop(id_, None)

    async def describe(self):
        return IndexStats(vectors_count=len(self.vectors))
```

### What Can Be Tested Locally

| Component | Testable without runtime? | How |
|-----------|--------------------------|-----|
| ChunkingEngine | Yes | Pure Python, no dependencies |
| Tokenization + BM25 scoring | Yes | Pure Python math |
| RRF fusion | Yes | Pure Python, takes SearchResult lists |
| MCP dispatch validation | Yes | Validates args before calling protocols |
| Binding wrappers | No | Require Pyodide JS FFI |
| Full search pipeline | No | Requires all bindings |

### Running Tests

```bash
# Unit tests (no Cloudflare runtime needed)
pytest tests/unit/ -v

# With the Worker running locally (requires pywrangler dev)
# Integration tests would go in tests/integration/
```

## Writing Alternative Implementations

To swap a binding implementation (e.g., for a different vector DB), implement the
protocol and inject it in `src/entry.py`:

```python
# Example: using a hypothetical PineconeVectorStore
from src.bindings.pinecone import PineconeVectorStore

vector_store = PineconeVectorStore(api_key=self.env.PINECONE_KEY)
# Everything else stays the same -- HybridSearchEngine, IngestionEngine, etc.
# only see the VectorStore protocol interface
```

The key constraint: your implementation must match the protocol's method signatures
and return the expected Pydantic model types.
