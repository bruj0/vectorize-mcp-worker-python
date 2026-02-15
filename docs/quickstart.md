# Quickstart

End-to-end guide: clone the repo, provision Cloudflare resources, deploy the worker, and test every endpoint.

## Table of Contents

1. [Clone and Install](#1-clone-and-install)
2. [Provision Cloudflare Resources](#2-provision-cloudflare-resources)
3. [Deploy and Verify](#3-deploy-and-verify)
4. [Test Public Endpoints](#4-test-public-endpoints)
5. [Test Authenticated Endpoints](#5-test-authenticated-endpoints)
6. [Test License Endpoints](#6-test-license-endpoints)
7. [Configure Cursor as an MCP Client](#7-configure-cursor-as-an-mcp-client)
8. [Debugging & Redeployment](#8-debugging--redeployment)
9. [Quick Reference](#quick-reference)

---

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

### Set secrets

Set the API key that protects authenticated endpoints on the main worker:

```bash
wrangler secret put API_KEY
```

Enter any strong string when prompted (e.g. `my-secret-key-123`). Remember this value -- you'll pass it as a Bearer token in authenticated requests.

Set the shared secret used for internal communication between the main worker and the multimodal worker. Use the same value for both:

```bash
# Main worker (from project root)
wrangler secret put INTERNAL_SECRET

# Multimodal worker
cd multimodal-pro-worker
wrangler secret put INTERNAL_SECRET
cd ..
```

## 3. Deploy and Verify

Python Workers are best tested against the deployed Cloudflare environment (local dev has limited binding support).

### Deploy the multimodal worker

The multimodal worker must be deployed **before** the main worker because the main worker references it via a Service Binding. Cloudflare validates this at deploy time.

```bash
cd multimodal-pro-worker
uv run pywrangler deploy
cd ..
```

The CLI prints the multimodal worker URL, e.g. `https://multimodal-pro-worker.<your-subdomain>.workers.dev`. You don't need this URL -- the main worker calls it internally via Service Binding.

Verify the multimodal worker rejects unauthenticated requests:

```bash
curl -s -X POST "https://multimodal-pro-worker.<your-subdomain>.workers.dev/describe-image" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
```

Expected:

```json
{
  "error": "Unauthorized. This worker is internal-only."
}
```

The response status should be `403`. If you get a different response, the `INTERNAL_SECRET` was not set correctly in step 2.

### Deploy the main worker

```bash
uv run pywrangler deploy
```

The CLI prints the main worker URL, e.g. `https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev`. This is the URL you'll use for all API calls.

### Set shell variables

You'll use these throughout the rest of the quickstart:

```bash
BASE="https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev"
API_KEY="my-secret-key-123"  # the value you set in step 2
```

### Verify the deployment

```bash
curl -s "$BASE/health/check" | python3 -m json.tool
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

**Critical**: `mode` must be `"production"`. If it shows `"development"`, the `API_KEY` secret was not set and all endpoints are unprotected.

### Verify authentication is enforced

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/search/multimodal" \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'
```

Expected: `401`. To see the full error:

```bash
curl -s -X POST "$BASE/search/multimodal" \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' | python3 -m json.tool
```

Expected:

```json
{
  "error": "Missing Authorization header",
  "hint": "Include 'Authorization: Bearer YOUR_API_KEY' in your request"
}
```

If the request succeeds without a Bearer token, authentication is not working -- re-run `wrangler secret put API_KEY` and redeploy.

## 4. Test Public Endpoints

These endpoints do not require authentication.

### GET / -- API documentation

```bash
curl -s "$BASE/" | python3 -m json.tool
```

Expected: JSON object with `name`, `version`, `endpoints`, `models`, and `authentication` fields.

### GET /dashboard -- Interactive playground

```bash
curl -s -o /dev/null -w "%{http_code}" "$BASE/dashboard"
```

Expected: `200`. Open `$BASE/dashboard` in a browser to see the full UI.

### GET /llms.txt -- AI search engine info

```bash
curl -s "$BASE/llms.txt"
```

Expected: plain text describing the service for AI crawlers.

## 5. Test Authenticated Endpoints

All remaining endpoints require the `Authorization: Bearer <API_KEY>` header (unless running in dev mode).

### POST /ingest/document -- Ingest a document

Ingest a few documents so there is data to search against:

```bash
curl -s -X POST "$BASE/ingest/document" \
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
curl -s -X POST "$BASE/ingest/document" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "doc-rust-intro",
    "content": "Rust is a multi-paradigm, general-purpose programming language that emphasizes performance, type safety, and concurrency. It enforces memory safety without a garbage collector. Rust was originally designed by Graydon Hoare at Mozilla Research.",
    "title": "Introduction to Rust",
    "category": "programming"
  }' | python3 -m json.tool
```

### GET /stats/index -- Index statistics

```bash
curl -s "$BASE/stats/index" \
  -H "Authorization: Bearer $API_KEY" | python3 -m json.tool
```

Expected: `vectorCount` and `total_documents` should reflect the documents you just ingested.

### POST /search/multimodal -- Hybrid search

```bash
curl -s -X POST "$BASE/search/multimodal" \
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
curl -s -X POST "$BASE/search/multimodal" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "programming language",
    "topK": 1,
    "offset": 1,
    "rerank": true
  }' | python3 -m json.tool
```

### POST /ingest/image -- Ingest a photo

Download a real photograph to test visual description:

```bash
curl -sL -o test-photo.jpg "https://picsum.photos/seed/quickstart/400/300.jpg"
```

> This is a seeded URL that always returns the same photograph. It typically shows
> a landscape or architectural shot -- exactly the kind of image Llama 4 Scout
> excels at describing.

Ingest it with `imageType=photo`:

```bash
curl -s -X POST "$BASE/ingest/image" \
  -H "Authorization: Bearer $API_KEY" \
  -F "id=img-photo-001" \
  -F "image=@test-photo.jpg" \
  -F "category=test-images" \
  -F "title=Sample Photo" \
  -F "imageType=photo" | python3 -m json.tool
```

Expected: `success: true` with a `description` generated by Llama 4 Scout describing what is visible in the photograph (e.g. scenery, objects, colors). The `extractedText` field will be `null` or empty since the photo has no readable text.

### POST /ingest/image -- Ingest a document with OCR

Download an image that contains text-heavy content to test OCR extraction:

```bash
curl -sL -o test-document.jpg "https://www.w3.org/WAI/WCAG21/Techniques/pdf/img/table-word.jpg"
```

> This is a W3C accessibility example showing a table created in Microsoft Word.
> It contains clear, readable text in rows and columns -- ideal for verifying
> that OCR extraction works correctly.

Ingest it with `imageType=document`:

```bash
curl -s -X POST "$BASE/ingest/image" \
  -H "Authorization: Bearer $API_KEY" \
  -F "id=img-doc-001" \
  -F "image=@test-document.jpg" \
  -F "category=test-documents" \
  -F "title=W3C Table Screenshot" \
  -F "imageType=document" | python3 -m json.tool
```

Expected:
- `success: true`
- `description`: explains what the image shows (a table in a Word document)
- `extractedText`: **non-null** OCR output containing the text from the table cells

Verify OCR worked by checking that `extractedText` contains words visible in the
table (e.g. column headers or cell values). If `extractedText` is `null`, the
multimodal worker may not be running -- check with `wrangler tail`.

Supported image types: `screenshot`, `diagram`, `document`, `chart`, `photo`, `auto` (default). The `document` type uses a prompt optimized for text-heavy images and OCR, while `photo` focuses on visual description.

### POST /search/similar-images -- Visual similarity search

Search using the photo you ingested:

```bash
curl -s -X POST "$BASE/search/similar-images" \
  -H "Authorization: Bearer $API_KEY" \
  -F "image=@test-photo.jpg" \
  -F "topK=3" | python3 -m json.tool
```

Expected: results array containing `img-photo-001` ranked highest (exact match), followed by `img-doc-001` if both were ingested.

Search using the document image to verify OCR-ingested content is findable:

```bash
curl -s -X POST "$BASE/search/similar-images" \
  -H "Authorization: Bearer $API_KEY" \
  -F "image=@test-document.jpg" \
  -F "topK=3" | python3 -m json.tool
```

Expected: `img-doc-001` should rank highest since it's the same image.

You can also search for the OCR content via text search:

```bash
curl -s -X POST "$BASE/search/multimodal" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "table word document",
    "topK": 3,
    "rerank": true
  }' | python3 -m json.tool
```

Expected: `img-doc-001` should appear in results since its extracted text was indexed alongside the AI description.

### DELETE /delete/document/:id -- Delete a document

```bash
curl -s -X DELETE "$BASE/delete/document/doc-rust-intro" \
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

## 7. Configure Cursor as an MCP Client

Cursor can use the Vectorize worker as an MCP server, giving the AI agent direct access to search, ingest, and manage your knowledge base. The `vectorize-mcp-tool` package (in the `vectorize-mcp-tool/` subdirectory) provides both a CLI and a stdio MCP server.

### Prerequisites

You need `uv` installed (from step 1) and a deployed worker (from step 3).

### How it works

```
Cursor IDE  ──stdio──▶  vectorize-mcp-server  ──HTTPS──▶  Deployed Cloudflare Worker
 (MCP client)            (local process)                     (REST endpoints)
```

The `vectorize-mcp-server` command runs as a local process that:
1. Receives MCP tool calls from Cursor over stdio
2. Translates them into direct HTTP requests to your deployed worker's REST endpoints (e.g. /search/multimodal, /ingest/document, /stats/index, etc.)
3. Returns the JSON response back to Cursor

### Install the tool

From the project root:

```bash
uv tool install ./vectorize-mcp-tool
```

This makes both `vectorize-mcp` (CLI) and `vectorize-mcp-server` (MCP server) available globally.

### Test the CLI

Verify the tool works against your deployed worker:

```bash
vectorize-mcp --url "$BASE" --api-key "$API_KEY" health
```

Expected: JSON with `"status": "healthy"`. Then try a search:

```bash
vectorize-mcp --url "$BASE" --api-key "$API_KEY" search "Python programming"
```

### Create the Cursor MCP configuration

Create the file `.cursor/mcp.json` in the **project root** (not your home directory):

```json
{
  "mcpServers": {
    "vectorize": {
      "command": "vectorize-mcp-server",
      "env": {
        "VECTORIZE_URL": "https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev",
        "VECTORIZE_API_KEY": "your-api-key"
      }
    }
  }
}
```

Replace the two placeholder values:

- `VECTORIZE_URL`: your deployed worker URL (the `$BASE` value from step 3)
- `VECTORIZE_API_KEY`: the API key you set with `wrangler secret put API_KEY` in step 2

> **Security note**: `.cursor/mcp.json` is already in `.gitignore` since it contains your API key. Never commit this file.

**Alternative (without global install):** use `uvx` to run directly from the local checkout:

```json
{
  "mcpServers": {
    "vectorize": {
      "command": "uvx",
      "args": [
        "--from", "./vectorize-mcp-tool",
        "vectorize-mcp-server"
      ],
      "env": {
        "VECTORIZE_URL": "https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev",
        "VECTORIZE_API_KEY": "your-api-key"
      }
    }
  }
}
```

### Verify in Cursor

1. Open Cursor and navigate to the project
2. Open **Settings** (Cmd+, on macOS, Ctrl+, on Linux) and go to **MCP**
3. You should see **vectorize** listed as an MCP server
4. The status indicator should show a green dot (connected)

If the server shows as disconnected, click the refresh icon next to it. Check the Cursor MCP logs (Output panel > MCP) for error details.

### Test the MCP connection

Open Cursor's AI chat (Cmd+L / Ctrl+L) and switch to **Agent** mode, then try:

> Search the knowledge base for "Python programming"

Cursor should call the `vectorize` tool with `operation: "search_multimodal"` and display the results from your deployed worker.

Other things to try:

> Ingest a new document about TypeScript with id "doc-ts-intro"

> Show me the knowledge base statistics

> Delete the document with id "doc-ts-intro"

### Troubleshooting

**"VECTORIZE_URL environment variable is required"**: The `env` block in `mcp.json` is missing or `VECTORIZE_URL` is empty. Double-check the configuration.

**"401 Unauthorized" errors**: The `VECTORIZE_API_KEY` in `mcp.json` doesn't match the secret on the deployed worker. Verify with:

```bash
curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE/stats/index" \
  -H "Authorization: Bearer $API_KEY"
```

Expected: `200`. If you get `401`, re-run `wrangler secret put API_KEY` and redeploy.

**Server not appearing in Cursor**: Make sure `.cursor/mcp.json` is in the project root (the same directory as `wrangler.toml`), not in `~/.cursor/`.

**"vectorize-mcp-server: command not found"**: The tool isn't installed or isn't on the PATH. Either run `uv tool install ./vectorize-mcp-tool` or use the `uvx` alternative config above.

### Global vs project-level configuration

The configuration above is **project-level** (`.cursor/mcp.json` in the repo). This is recommended because `uvx` paths are relative to the project root.

To make the MCP server available across all Cursor projects, install the tool globally with `uv tool install` and use `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "vectorize": {
      "command": "vectorize-mcp-server",
      "env": {
        "VECTORIZE_URL": "https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev",
        "VECTORIZE_API_KEY": "your-api-key"
      }
    }
  }
}
```

## 8. Debugging & Redeployment

### Live logs with wrangler tail

Stream real-time logs (Python tracebacks, request metadata, console output) from the deployed worker:

```bash
wrangler tail --format=json
```

Keep this running in a second terminal while you test. Useful filters:

```bash
wrangler tail --format=json --status error    # only show errors
wrangler tail --format=json --method POST     # only POST requests
wrangler tail --format=json --search "search" # filter by path/content
```

### Redeploying after code changes

Always deploy the multimodal worker first, then the main worker:

```bash
cd multimodal-pro-worker && uv run pywrangler deploy && cd ..
uv run pywrangler deploy
```

### Other debugging tools

- **Cloudflare Dashboard:** Workers & Pages > your worker > Logs tab for historical request logs
- **curl directly:** All the `curl` commands in this guide work against the deployed URL at any time

## Quick Reference

| Endpoint | Method | Auth | Body | Section |
|----------|--------|------|------|---------|
| `/` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/health/check` | GET | No | -- | [3](#3-deploy-and-verify) |
| `/dashboard` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/llms.txt` | GET | No | -- | [4](#4-test-public-endpoints) |
| `/stats/index` | GET | Yes | -- | [5](#5-test-authenticated-endpoints) |
| `/search/multimodal` | POST | Yes | JSON | [5](#5-test-authenticated-endpoints) |
| `/ingest/document` | POST | Yes | JSON | [5](#5-test-authenticated-endpoints) |
| `/ingest/image` | POST | Yes | multipart | [5](#5-test-authenticated-endpoints) |
| `/search/similar-images` | POST | Yes | multipart | [5](#5-test-authenticated-endpoints) |
| `/delete/document/:id` | DELETE | Yes | -- | [5](#5-test-authenticated-endpoints) |
| `/license/create` | POST | Yes | JSON | [6](#6-test-license-endpoints) |
| `/license/validate` | POST | Yes | JSON | [6](#6-test-license-endpoints) |
| `/license/list` | GET | Yes | -- | [6](#6-test-license-endpoints) |
| `/license/revoke` | POST | Yes | JSON | [6](#6-test-license-endpoints) |
