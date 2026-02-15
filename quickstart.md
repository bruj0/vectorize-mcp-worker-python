# Quickstart

End-to-end guide: clone the repo, provision Cloudflare resources, start the worker, and test every endpoint.

## 1. Clone and Install

```bash
git clone <repo-url> vectorize-mcp-worker-python
cd vectorize-mcp-worker-python
```

### Install uv (Python package manager)

**macOS:**

```bash
brew install uv
```

**Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or restart your shell
```

### Install Wrangler (Cloudflare CLI)

**macOS:**

```bash
brew install node  # skip if you already have Node.js
npm install -g wrangler
```

**Linux (Debian/Ubuntu):**

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install -g wrangler
```

**Linux (any distro, via nvm):**

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install --lts
npm install -g wrangler
```

### Authenticate Wrangler

```bash
wrangler login
```

A browser window opens. Authorize the CLI against your Cloudflare account.

### Install Python dependencies

```bash
uv sync
uv tool install workers-py
```

## 2. Provision Cloudflare Resources

### Create the Vectorize index

```bash
wrangler vectorize create mcp-knowledge-base --dimensions=384 --metric=cosine
```

### Create the D1 database

```bash
wrangler d1 create mcp-knowledge-db
```

Copy the `database_id` from the output and paste it into `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "mcp-knowledge-db"
database_id = "paste-your-database-id-here"
```

### Apply the database schema

```bash
wrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql
```

### Set the API key secret

```bash
wrangler secret put API_KEY
```

Enter any strong string when prompted (e.g. `my-secret-key-123`). Remember this value -- you'll pass it as a Bearer token in authenticated requests.

> **Dev mode shortcut:** If you skip this step, the worker runs in development mode where *all* endpoints are open without authentication. Useful for local testing but never use this in production.

## 3. Start the Dev Server

```bash
uv run pywrangler dev
```

The worker starts at `http://localhost:8787` (default). All `curl` examples below use this base URL. Replace it with your `*.workers.dev` URL after deploying.

Set a shell variable for convenience:

```bash
BASE=http://localhost:8787
API_KEY="my-secret-key-123"  # the value you set in step 2 (omit if dev mode)
```

## 4. Test Public Endpoints

These endpoints do not require authentication.

### GET / -- API documentation

```bash
curl -s "$BASE/" | python3 -m json.tool
```

Expected: JSON object with `name`, `version`, `endpoints`, `models`, and `authentication` fields.

### GET /test -- Health check

```bash
curl -s "$BASE/test" | python3 -m json.tool
```

Expected:

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

If `hasAPIKey` is `false` and `mode` is `"development"`, the API_KEY secret was not set (dev mode).

### GET /dashboard -- Interactive playground

```bash
curl -s -o /dev/null -w "%{http_code}" "$BASE/dashboard"
```

Expected: `200`. Open `http://localhost:8787/dashboard` in a browser to see the full UI.

### GET /llms.txt -- AI search engine info

```bash
curl -s "$BASE/llms.txt"
```

Expected: plain text describing the service for AI crawlers.

### GET /mcp/tools -- MCP tool schema

```bash
curl -s "$BASE/mcp/tools" | python3 -m json.tool
```

Expected: JSON with a `tools` array containing the `vectorize` tool definition and its `inputSchema`.

## 5. Test Authenticated Endpoints

All remaining endpoints require the `Authorization: Bearer <API_KEY>` header (unless running in dev mode).

### POST /ingest -- Ingest a document

Ingest a few documents so there is data to search against:

```bash
curl -s -X POST "$BASE/ingest" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "doc-python-intro",
    "content": "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected. It supports multiple programming paradigms, including structured, object-oriented and functional programming.",
    "title": "Introduction to Python",
    "category": "programming"
  }' | python3 -m json.tool
```

Expected:

```json
{
  "success": true,
  "documentId": "doc-python-intro",
  "chunksCreated": 1,
  "performance": { ... }
}
```

Ingest a second document to make search results more interesting:

```bash
curl -s -X POST "$BASE/ingest" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "doc-rust-intro",
    "content": "Rust is a multi-paradigm, general-purpose programming language that emphasizes performance, type safety, and concurrency. It enforces memory safety without a garbage collector. Rust was originally designed by Graydon Hoare at Mozilla Research.",
    "title": "Introduction to Rust",
    "category": "programming"
  }' | python3 -m json.tool
```

### GET /stats -- Index statistics

```bash
curl -s "$BASE/stats" \
  -H "Authorization: Bearer $API_KEY" | python3 -m json.tool
```

Expected: `vectorCount` and `total_documents` should reflect the documents you just ingested.

### POST /search -- Hybrid search

```bash
curl -s -X POST "$BASE/search" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "memory safety without garbage collection",
    "topK": 5,
    "rerank": true
  }' | python3 -m json.tool
```

Expected: results array with each result containing `id`, `score`, `content`, `category`, and per-scorer breakdown in `scores` (vector, keyword, reranker).

Search with pagination:

```bash
curl -s -X POST "$BASE/search" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "programming language",
    "topK": 1,
    "offset": 1,
    "rerank": true
  }' | python3 -m json.tool
```

### POST /ingest-image -- Ingest an image (multipart form)

Requires a test image. Download one first:

```bash
curl -s -o test-image.png "https://via.placeholder.com/300x200.png?text=Test+Image"
```

Then ingest it:

```bash
curl -s -X POST "$BASE/ingest-image" \
  -H "Authorization: Bearer $API_KEY" \
  -F "id=img-test-001" \
  -F "image=@test-image.png" \
  -F "category=test-images" \
  -F "title=Test Placeholder Image" \
  -F "imageType=auto" | python3 -m json.tool
```

Expected: `success: true` with `description` (AI-generated) and `extractedText` fields.

> **Note:** This endpoint calls Workers AI (Llama 4 Scout) via the MULTIMODAL service binding. It may fail in local dev if the service binding is not available.

### POST /find-similar-images -- Visual similarity search

```bash
curl -s -X POST "$BASE/find-similar-images" \
  -H "Authorization: Bearer $API_KEY" \
  -F "image=@test-image.png" \
  -F "topK=3" | python3 -m json.tool
```

Expected: results array filtered to image-type documents, ranked by similarity.

### DELETE /documents/:id -- Delete a document

```bash
curl -s -X DELETE "$BASE/documents/doc-rust-intro" \
  -H "Authorization: Bearer $API_KEY" | python3 -m json.tool
```

Expected:

```json
{
  "success": true,
  "deleted": "doc-rust-intro"
}
```

## 6. Test License Endpoints

### POST /license/create -- Create a license

```bash
curl -s -X POST "$BASE/license/create" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "plan": "standard",
    "max_documents": 5000,
    "max_queries_per_day": 500
  }' | python3 -m json.tool
```

Expected: `success: true` with a generated `license_key`. Save it:

```bash
LICENSE_KEY="<paste the license_key from the response>"
```

### POST /license/validate -- Validate a license

```bash
curl -s -X POST "$BASE/license/validate" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"license_key\": \"$LICENSE_KEY\"}" | python3 -m json.tool
```

Expected: `valid: true` with plan and limits.

### GET /license/list -- List all licenses

```bash
curl -s "$BASE/license/list" \
  -H "Authorization: Bearer $API_KEY" | python3 -m json.tool
```

Expected: `licenses` array containing the license you just created.

### POST /license/revoke -- Revoke a license

```bash
curl -s -X POST "$BASE/license/revoke" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"license_key\": \"$LICENSE_KEY\"}" | python3 -m json.tool
```

Expected:

```json
{
  "success": true,
  "revoked": "<license_key>"
}
```

Validate again to confirm it's revoked:

```bash
curl -s -X POST "$BASE/license/validate" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"license_key\": \"$LICENSE_KEY\"}" | python3 -m json.tool
```

Expected: `valid: false`.

## 7. Test MCP Endpoint

The `/mcp/call` endpoint wraps all operations behind a single `vectorize` tool. This is the interface AI agents use.

### MCP search

```bash
curl -s -X POST "$BASE/mcp/call" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "vectorize",
    "arguments": {
      "operation": "search",
      "query": "what is Python",
      "top_k": 3,
      "rerank": true
    }
  }' | python3 -m json.tool
```

### MCP ingest

```bash
curl -s -X POST "$BASE/mcp/call" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "vectorize",
    "arguments": {
      "operation": "ingest",
      "id": "doc-mcp-test",
      "content": "This document was ingested via the MCP tool interface.",
      "category": "mcp-test"
    }
  }' | python3 -m json.tool
```

### MCP stats

```bash
curl -s -X POST "$BASE/mcp/call" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "vectorize",
    "arguments": { "operation": "stats" }
  }' | python3 -m json.tool
```

### MCP delete

```bash
curl -s -X POST "$BASE/mcp/call" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "vectorize",
    "arguments": { "operation": "delete", "id": "doc-mcp-test" }
  }' | python3 -m json.tool
```

## 8. Deploy to Production

When everything works locally:

```bash
uv run pywrangler deploy
```

The CLI prints the live URL (e.g. `https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev`). Replace `$BASE` with that URL and re-run any of the tests above to verify the production deployment.

## Quick Reference

| Endpoint | Method | Auth | Body | Section |
|----------|--------|------|------|---------|
| `/` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/test` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/dashboard` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/llms.txt` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/mcp/tools` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/stats` | GET | Yes | -- | [5](#5-test-authenticated-endpoints) |
| `/search` | POST | Yes | JSON | [5](#5-test-authenticated-endpoints) |
| `/ingest` | POST | Yes | JSON | [5](#5-test-authenticated-endpoints) |
| `/ingest-image` | POST | Yes | multipart | [5](#5-test-authenticated-endpoints) |
| `/find-similar-images` | POST | Yes | multipart | [5](#5-test-authenticated-endpoints) |
| `/documents/:id` | DELETE | Yes | -- | [5](#5-test-authenticated-endpoints) |
| `/license/create` | POST | Yes | JSON | [6](#6-test-license-endpoints) |
| `/license/validate` | POST | Yes | JSON | [6](#6-test-license-endpoints) |
| `/license/list` | GET | Yes | -- | [6](#6-test-license-endpoints) |
| `/license/revoke` | POST | Yes | JSON | [6](#6-test-license-endpoints) |
| `/mcp/call` | POST | Yes | JSON | [7](#7-test-mcp-endpoint) |
