---
name: cloudflare-python-workers
description: Build and debug Cloudflare Workers written in Python (Pyodide runtime). Use when creating or editing Python Workers, troubleshooting Pyodide import errors, working with wrangler.toml for Python, configuring Cloudflare bindings (D1, Vectorize, AI, Service Bindings), or converting JS FFI patterns to Python.
---

# Cloudflare Python Workers

## Runtime Model

Python Workers run on **Pyodide** (CPython compiled to WebAssembly) inside the Cloudflare Workers V8 isolate. This is NOT a standard Python server -- there is no filesystem, no subprocess, no native C extensions.

Key constraints:
- **No `pip install` at runtime.** Dependencies must be Pyodide-compatible or pure Python.
- **Pydantic v2 works.** Confirmed compatible with Pyodide.
- **No numpy, pandas, or C-extension packages** unless they ship Pyodide wheels.
- **No `structlog`, `httpx`, `aiosqlite`, `FastMCP`** -- use Cloudflare bindings instead.

## Critical: Import Paths

When `wrangler.toml` sets `main = "src/entry.py"`, Pyodide treats `src/` as the module root. **Never prefix imports with `src.`**:

```python
# CORRECT
from auth import authenticate
from bindings.ai import CloudflareAIProvider
from models import Document

# WRONG -- ModuleNotFoundError at runtime
from src.auth import authenticate
from src.bindings.ai import CloudflareAIProvider
from src.models import Document
```

The error message includes: `If your main module is inside the 'src' directory then your import statement shouldn't include a 'src.' prefix`.

## wrangler.toml for Python

```toml
name = "my-worker"
main = "src/entry.py"
compatibility_date = "2026-02-12"
compatibility_flags = ["python_workers"]
```

The `python_workers` flag is **required**. Without it, Wrangler treats the file as JavaScript.

### Bindings

```toml
# Workers AI (embedding, reranking, inference)
[ai]
binding = "AI"

# Vectorize (vector database)
[[vectorize]]
binding = "VECTORIZE"
index_name = "my-index"

# D1 (SQLite database)
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "YOUR_DATABASE_ID_HERE"

# Service binding (call another worker)
[[services]]
binding = "OTHER_WORKER"
service = "other-worker-name"

# Observability
[observability]
enabled = true
```

### Secrets

```bash
wrangler secret put API_KEY   # interactive prompt, stored encrypted
```

Never put secrets in `wrangler.toml`. Use `.dev.vars` for local development:

```
API_KEY=dev-test-key
```

### Config File Convention

| File | Git | Purpose |
|------|:---:|---------|
| `wrangler.toml.example` | Yes | Template with placeholder values |
| `wrangler.toml` | **No** | Real config -- gitignore this |
| `.dev.vars` | **No** | Local dev secrets |

## Entry Point Pattern

```python
from workers import Response, WorkerEntrypoint

class Default(WorkerEntrypoint):
    async def fetch(self, request) -> Response:
        url = urlparse(str(request.url))
        method = str(request.method)

        # Access bindings via self.env
        ai = self.env.AI
        db = self.env.DB
        vectorize = self.env.VECTORIZE
        api_key = getattr(self.env, "API_KEY", None)

        # Return responses
        return Response(json.dumps(data), headers={"Content-Type": "application/json"})
```

## JS FFI Pattern

Python Workers use Pyodide FFI to call JavaScript APIs. The critical pattern for Cloudflare bindings:

```python
from js import Object
from pyodide.ffi import to_js as _to_js

def to_js(obj):
    """Convert Python dict to JS Object (not Map)."""
    return _to_js(obj, dict_converter=Object.fromEntries)
```

**Always use `Object.fromEntries`** -- Cloudflare bindings expect plain JS Objects, not Maps (which is Pyodide's default).

### Critical: D1 `.bind()` Pitfalls

**Pitfall 1: None becomes undefined.** Python `None` becomes JS `undefined` through FFI. D1's `.bind()` rejects `undefined`:

```
D1_TYPE_ERROR: Type 'undefined' not supported for value 'undefined'
```

**Always convert `None` to a fallback before passing to `.bind()`:**

```python
# WRONG -- will fail if title is None
stmt.bind(doc_id, content, title, category)

# CORRECT -- convert None to empty string for nullable text columns
stmt.bind(doc_id, content, title or "", category or "")
```

This applies to every `.bind()` call with nullable parameters.

**Pitfall 2: `.bind()` is not cumulative.** Each call to `.bind()` replaces all previous bindings. D1's `.bind()` takes all parameters at once (variadic in JS):

```python
# WRONG -- each .bind() replaces the previous one, only last token is bound
stmt = db.prepare("SELECT * FROM t WHERE term IN (?, ?, ?)")
for token in tokens:
    stmt = stmt.bind(token)  # overwrites previous bindings!

# CORRECT -- spread all parameters in a single .bind() call
stmt = db.prepare("SELECT * FROM t WHERE term IN (?, ?, ?)").bind(*tokens)
```

The error for this is `D1_ERROR: Wrong number of parameter bindings for SQL query.`

### Critical: Vectorize `.upsert()` and Float Types

Embedding values from Workers AI come through Pyodide FFI as typed-array elements. Always cast to plain `float` before passing to Vectorize:

```python
# WRONG -- values may contain typed-array proxies that Vectorize silently drops
to_js([{"id": v.id, "values": v.values, "metadata": v.metadata}])

# CORRECT -- explicit float() ensures plain JS numbers
to_js([{"id": v.id, "values": [float(x) for x in v.values], "metadata": v.metadata}])
```

### Vectorize `describe()` Response Shape

The JS proxy returned by `await env.VECTORIZE.describe()` has exactly **4 properties**:

| JS Property | Python type | Example |
|---|---|---|
| `vectorCount` | `int` | `9` |
| `dimensions` | `int` | `384` |
| `processedUpToMutation` | `str` (UUID) | `"7a381f33-b392-4d2b-..."` |
| `processedUpToDatetime` | `str` (ISO 8601) | `"2026-02-15T17:11:25.990Z"` |

**Critical: the property is `vectorCount` (no trailing "s"), NOT `vectorsCount`.** Using `getattr(js_stats, "vectorsCount", 0)` silently falls back to 0 and always reports zero vectors.

```python
js_stats = await env.VECTORIZE.describe()

# WRONG -- always returns 0, silently falls back to default
int(getattr(js_stats, "vectorsCount", 0))

# CORRECT
int(getattr(js_stats, "vectorCount", 0))
```

The `metric` (e.g. `"cosine"`) is on the index config (returned by `wrangler vectorize get`), NOT on the `describe()` response.

**Eventual consistency.** After upsert, `vectorCount` in `describe()` can stay at 0 for 30-60+ seconds while vectors are already fully queryable via `query()`. Don't use `vectorCount` to verify upserts -- use an actual search query instead.

### Critical: `request.formData()` Does Not Exist

The Python `workers.Request` wrapper does **not** expose the JS `formData()` method. Calling `await request.formData()` raises:

```
AttributeError: 'Request' object has no attribute 'formData'
```

**Use `src/multipart.py` instead** -- a pure-Python multipart parser that reads raw bytes via JS FFI:

```python
from multipart import parse_multipart

# In your route handler
form = await parse_multipart(request, log)
img_id = form.get_text("id")
image_bytes = form.get_bytes("image")  # raw file bytes
category = form.get_text("category", "images")  # with default
```

Internally, it reads the body via `new Response(request.body).arrayBuffer()` through Pyodide FFI, then splits on multipart boundaries. This avoids any dependency on the `workers.Request` wrapper.

### Common FFI Operations

```python
# Call D1
result = await env.DB.prepare("SELECT * FROM docs WHERE id = ?").bind(doc_id).first()
# result is a JS proxy -- use .to_py() or access attributes directly

# Call Vectorize
matches = await env.VECTORIZE.query(to_js(vector), to_js({"topK": 5}))

# Call Workers AI
result = await env.AI.run("@cf/baai/bge-small-en-v1.5", to_js({"text": ["hello"]}))
```

### Converting JS Results to Python

```python
# JS object to Python dict
py_dict = js_obj.to_py()

# JS array to Python list
py_list = list(js_array)

# Nested JS object -- access properties directly
value = js_obj.someProperty
```

## CLI Commands

Python Workers use `pywrangler` (installed via `uv tool install workers-py`), invoked through `uv run`:

```bash
uv run pywrangler deploy       # deploy to edge (primary workflow)
wrangler tail --format=json    # stream live logs with full details
wrangler secret put KEY        # manage secrets (plain wrangler)
wrangler d1 create my-db       # create D1 database (plain wrangler)
wrangler d1 execute my-db --remote --file=./schema.sql  # run SQL
wrangler vectorize create my-index --dimensions=384 --metric=cosine
```

Note: resource management commands (`secret`, `d1`, `vectorize`, `tail`) use standard `wrangler`, not `pywrangler`.

### Deploy-first workflow

Python Workers have limited local dev support (bindings don't fully work with `pywrangler dev`). The standard workflow is:

1. Deploy to Cloudflare: `uv run pywrangler deploy`
2. Test with `curl` against the deployed URL
3. Debug with `wrangler tail --format=json` in a second terminal

## Debugging

### wrangler tail

**Always use `--format=json`** to get full logs. Without it, you only see one-line summaries that don't show errors:

```bash
# WRONG -- shows "POST /ingest - Ok" even for 500 errors
wrangler tail

# CORRECT -- shows full stack traces, console output, exception details
wrangler tail --format=json
```

Note: "Ok" in plain mode means the worker responded (didn't crash), NOT that the response was successful. A worker returning `{ "error": "..." }` with status 500 still shows "Ok".

Useful filters:

```bash
wrangler tail --format=json --status error    # only errors
wrangler tail --format=json --method POST     # only POST requests
wrangler tail --format=json --search "ingest" # filter by content
```

### Structured Logging with RequestLogger

Use `src/logger.py` for structured, JSON-line logging with per-request trace IDs:

```python
from logger import RequestLogger, noop_logger

# Create per-request logger in entry.py
debug_flag = str(getattr(self.env, "DEBUG_LOGGING", "") or "").lower()
log = RequestLogger(debug=debug_flag in ("true", "1", "yes"))

# Log operations with trace ID automatically included
log.info("search.start", query=query, topK=5)
log.debug_log("embedding.generated", dimensions=384)  # only when DEBUG_LOGGING=true
log.error("d1.failed", exc=some_exception, sql=query)  # includes full traceback
```

Each log line is a JSON object with `level`, `traceId`, `msg`, and optional fields. Use `wrangler tail --format=json` and search by `traceId` to follow a request end-to-end.

**Toggle debug logs** via the `DEBUG_LOGGING` env var:

```bash
# Enable verbose logging
wrangler secret put DEBUG_LOGGING   # enter "true"

# Or in wrangler.toml [vars] for non-sensitive toggle
[vars]
DEBUG_LOGGING = "true"
```

**Pass the logger through the codebase.** Binding wrappers accept it in their constructor (created per-request), engine methods accept it as an optional parameter:

```python
# Binding wrappers -- logger in constructor
vector_store = CloudflareVectorStore(self.env.VECTORIZE, logger=log)
ai_provider = CloudflareAIProvider(self.env.AI, logger=log)

# Engine methods -- logger as optional kwarg
result = await _hybrid_search.search(query, ..., logger=log)
result = await _ingestion.ingest(doc, ..., logger=log)
```

When `logger` is omitted, a silent `noop_logger()` is used (backward-compatible).

### Debug logging with print() (ad-hoc)

For quick ad-hoc debugging, `print()` in Python Workers outputs to the `logs` array in `wrangler tail --format=json`. Use it to inspect FFI values at runtime:

```python
# Add temporary debug prints, deploy, tail, then remove
print(f"[debug] values_type={type(vals).__name__} len={len(vals)}")
print(f"[debug] result={result.to_py() if hasattr(result, 'to_py') else result}")
```

This is the fastest way to debug FFI issues since you can inspect actual types and values on the deployed worker. Prefer `RequestLogger` for persistent logging.

### Common Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'src'` | Imports prefixed with `src.` | Remove `src.` prefix from all imports |
| `D1_TYPE_ERROR: Type 'undefined' not supported` | Python `None` passed to D1 `.bind()` | Convert to fallback: `value or ""` |
| `TypeError: ... is not a function` | Passing Python dict where JS Object expected | Wrap with `to_js()` using `Object.fromEntries` |
| `JsException: ... is not iterable` | Treating JS proxy as Python iterable | Call `.to_py()` first or use `list()` |
| `ModuleNotFoundError: No module named 'xyz'` | Package not available in Pyodide | Use only Pyodide-compatible or pure-Python packages |
| `mode: "development"` in production | `API_KEY` secret not set | Run `wrangler secret put API_KEY` |
| Worker starts then crashes silently | Missing binding in `wrangler.toml` | Check all bindings are declared in wrangler.toml |
| `Could not resolve service binding` | Target worker not deployed yet | Deploy target worker first, then caller |
| `D1_ERROR: Wrong number of parameter bindings` | `.bind()` called in a loop (replaces previous) | Use `.bind(*params)` to spread all at once |
| `vectorCount: 0` but search works | JS property is `vectorCount` not `vectorsCount` | Use `getattr(js_stats, "vectorCount", 0)` -- no trailing "s" |
| `'Request' object has no attribute 'formData'` | Python workers.Request doesn't wrap JS formData() | Use `parse_multipart(request)` from `src/multipart.py` |
| `fetch() takes 1 positional argument but 2 were given` | Service binding `.fetch()` wrapped by workers lib | Create `JsRequest.new(url, init)` first, pass as single arg |
| Vision model says "There is no photograph provided" | Using top-level `image` field with Llama 4 Scout | Use multimodal content array: `content: [{type: "text", ...}, {type: "image_url", ...}]` |

## Supported AI Models

| Model ID | Purpose | Dims |
|----------|---------|------|
| `@cf/baai/bge-small-en-v1.5` | Text embeddings | 384 |
| `@cf/baai/bge-reranker-base` | Cross-encoder reranking | -- |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | Vision / image description (multimodal content format) | -- |

### Critical: Llama 4 Scout Vision Input Format

Llama 4 Scout does **NOT** use a top-level `image` field (unlike Llama 3.2 Vision / LLaVA). It uses the **OpenAI-style multimodal content format** where the image is embedded inside the message `content` as an array of typed objects. HTTP URLs are not accepted -- only `data:` URIs.

```python
import base64

b64 = base64.b64encode(image_bytes).decode("ascii")
data_url = f"data:image/jpeg;base64,{b64}"

input_data = to_js({
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ],
    "max_tokens": 1024,
})
result = await env.AI.run("@cf/meta/llama-4-scout-17b-16e-instruct", input_data)
```

If you pass the image as a top-level `image` field (number array, Uint8Array, or base64 string), the model runs successfully but responds with "There is no photograph provided" -- it silently ignores the field.

Ref: https://developers.cloudflare.com/workers-ai/models/llama-4-scout-17b-16e-instruct/

## Testing Without Cloudflare Runtime

Pure Python logic (chunking, scoring, data models) can be tested locally with pytest. Create a stub for the `workers` module:

```python
# tests/stubs/workers.py
class Response:
    def __init__(self, body="", status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}

class WorkerEntrypoint:
    pass
```

Add the stub to `sys.path` in `conftest.py`:

```python
import sys
sys.path.insert(0, "tests/stubs")
sys.path.insert(0, "src")
```

Anything that touches real Cloudflare bindings requires deploying and testing against the live worker.

## Service Bindings (Worker-to-Worker)

Service Bindings allow one Worker to call another internally with zero-latency RPC (no public HTTP):

```toml
# wrangler.toml of the CALLER
[[services]]
binding = "MULTIMODAL"
service = "multimodal-pro-worker"
```

```python
# In the caller worker
response = await self.env.MULTIMODAL.fetch(
    "http://internal/describe-image",
    to_js({
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }),
)
result = json.loads(await response.text())
```

Key points:
- The URL `http://internal/...` is a convention -- any URL works; only the path matters
- The target worker must be deployed first or `wrangler deploy` of the caller fails
- Use `getattr(self.env, "BINDING_NAME", None)` for optional bindings to avoid crashes
- Service bindings don't work with `--remote` in local dev; the target must be deployed

### Critical: Service Binding `.fetch()` Signature

The `workers` library wraps service binding `.fetch()` to accept **one** `Request` argument, NOT `(url, init)` like the standard Fetch API:

```python
# WRONG -- TypeError: fetch() takes 1 positional argument but 2 were given
response = await self.env.MULTIMODAL.fetch(
    "http://internal/endpoint",
    to_js({"method": "POST", "headers": headers, "body": body}),
)

# CORRECT -- create a JS Request object first, pass as single argument
from js import Request as JsRequest
js_request = JsRequest.new(
    "http://internal/endpoint",
    to_js({"method": "POST", "headers": headers, "body": body}),
)
response = await self.env.MULTIMODAL.fetch(js_request)
```

The error message is `fetch() takes 1 positional argument but 2 were given` and comes from `workers/_workers.py`.
