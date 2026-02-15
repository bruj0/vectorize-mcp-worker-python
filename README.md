# Vectorize MCP Worker (Python)

Production-Grade Hybrid RAG with Multimodal Support on Cloudflare Edge in Python.

## Table of Contents

- [Features](#features)
- [Setup](#setup)
- [API Endpoints](#api-endpoints)
- [MCP Integration](#mcp-integration)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Credits](#credits)

## Features

- Hybrid Search (Vector + BM25) with Reciprocal Rank Fusion
- Multimodal Image Processing (Llama 4 Scout)
- Cross-Encoder Reranking (`bge-reranker-base`)
- Recursive Chunking with 15% overlap
- One-time License System
- Interactive Dashboard at `/dashboard`
- MCP tool integration (via `vectorize-mcp-tool` package)

## Setup

### Prerequisites

- A Cloudflare account with Workers, Vectorize, D1, and Workers AI enabled
- [uv](https://docs.astral.sh/uv/#installation) (Python package manager)
- [wrangler](https://developers.cloudflare.com/workers/wrangler/) (Cloudflare CLI) -- needed to create cloud resources

### Install uv

**macOS:**

```bash
brew install uv
```

**Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install Wrangler (Cloudflare CLI)

Wrangler is needed to create and manage Cloudflare resources (D1 databases, Vectorize indexes, secrets). Install it globally via npm:

**macOS:**

```bash
brew install node          # if you don't have Node.js
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
source ~/.bashrc   # or restart your shell
nvm install --lts
npm install -g wrangler
```

Then authenticate with your Cloudflare account:

```bash
wrangler login
```

This opens a browser window to authorize the CLI against your account.

### Install Python Dependencies

```bash
uv init
uv tool install workers-py
```

### Create Cloudflare Resources

The project requires three Cloudflare services: **Vectorize** (vector database), **D1** (SQL database), and **Workers AI** (inference). Workers AI is enabled automatically; the other two need to be created. A fourth service, **multimodal-pro-worker**, is optional and enables image features.

#### 1. Create the Vectorize Index

This creates the vector store used for semantic search with 384-dimension BGE embeddings:

```bash
wrangler vectorize create mcp-knowledge-base --dimensions=384 --metric=cosine
```

#### 2. Create the D1 Database

D1 stores document metadata, BM25 keyword indexes, and license records:

```bash
wrangler d1 create mcp-knowledge-db
```

This outputs a database ID. Copy it and update `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "mcp-knowledge-db"
database_id = "paste-your-database-id-here"
```

#### 3. Apply the Database Schema

Run the schema migration against the remote D1 database:

```bash
wrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql
```

This creates the following tables:

| Table | Purpose |
|-------|---------|
| `documents` | Ingested document chunks and metadata |
| `keywords` | BM25 term-frequency index per document |
| `doc_stats` | Corpus-level statistics (total docs, avg length) |
| `term_stats` | Document-frequency per term |
| `licenses` | API license keys and quotas |

#### 4. Set the API Key Secret

Set the API key that protects write operations (`/ingest/document`, `/license/*`):

```bash
wrangler secret put API_KEY
```

You will be prompted to enter the secret value interactively. This is stored encrypted and never appears in `wrangler.toml`.

#### 5. Deploy the Multimodal Worker (optional -- for image features)

The image endpoints (`/ingest/image`, `/search/similar-images`) require a separate worker that processes images via Llama 4 Scout. If you only need text search, skip this step.

```bash
cd multimodal-pro-worker
uv tool install workers-py    # if not already installed
uv run pywrangler deploy
cd ..
```

This deploys the `multimodal-pro-worker` which the main worker calls via a Service Binding. Without it, text features work normally and image endpoints return a 501 error with a clear message.

### Deploy and Debug

Build and deploy to Cloudflare's global edge network:

```bash
uv run pywrangler deploy
```

Stream live logs from the deployed worker:

```bash
wrangler tail --format=json
```

> For a complete step-by-step guide, see [docs/quickstart.md](docs/quickstart.md).
> For production deployment, security, and monitoring, see [docs/production.md](docs/production.md).

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API documentation |
| `/health/check` | GET | Health check |
| `/dashboard` | GET | Interactive playground UI |
| `/llms.txt` | GET | AI search engine info |
| `/stats/index` | GET | Index statistics |
| `/search/multimodal` | POST | Hybrid search (documents + images) |
| `/search/documents` | POST | Documents-only search |
| `/search/similar-images` | POST | Find similar images |
| `/ingest/document` | POST | Document ingestion |
| `/ingest/image` | POST | Image ingestion (requires multimodal-pro-worker) |
| `/get/document/:id` | GET | Get document by ID |
| `/get/image/:id` | GET | Get image by ID |
| `/list/documents` | GET | List documents |
| `/delete/document/:id` | DELETE | Delete document |
| `/delete/license/:key` | DELETE | Delete license |
| `/license/validate` | POST | Validate license |
| `/license/create` | POST | Create license |
| `/license/list` | GET | List licenses |
| `/license/revoke` | POST | Revoke license |
| `/init/reset-passphrase` | POST | Set passphrase for reset endpoints |
| `/reset/all` | POST | Reset all (passphrase-gated) |
| `/reset/documents` | POST | Reset documents (passphrase-gated) |
| `/reset/licenses` | POST | Reset licenses (passphrase-gated) |

Search results return snippets and metadata instead of full content. The passphrase-gated reset endpoints (`/init/reset-passphrase`, `/reset/*`) prevent accidental AI deletion.

## MCP Integration

All MCP operations are performed through the `vectorize-mcp-tool` package, which provides both a CLI and a FastMCP stdio server. The MCP tool dispatches directly to the worker's REST endpoints -- there are no `/mcp/*` proxy endpoints on the worker.

Operations: `search_multimodal`, `search_documents`, `ingest`, `ingest_image`, `stats`, `delete`, `get_document`, `get_image`, `list_documents`, `license_validate`, `license_create`, `license_list`, `license_revoke`, `delete_license`, `reset_all`, `reset_documents`, `reset_licenses`.

### Install and Use

```bash
# Install
cd vectorize-mcp-tool && pip install -e .

# CLI usage
vectorize-mcp --url https://your-worker.workers.dev --api-key YOUR_KEY health
vectorize-mcp --url https://your-worker.workers.dev --api-key YOUR_KEY search multimodal "your query"

# MCP server for Cursor
vectorize-mcp-server  # reads VECTORIZE_URL and VECTORIZE_API_KEY from env
```

See [vectorize-mcp-tool/README.md](vectorize-mcp-tool/README.md) for full documentation.

## Project Structure

```
vectorize-mcp-worker-python/
├── src/                        # Main worker source
│   ├── entry.py                # HTTP routing and Worker entrypoint
│   ├── bindings/               # Cloudflare binding wrappers (FFI)
│   ├── hybrid_search.py        # Vector + BM25 + RRF fusion
│   ├── ingestion.py            # Document/image ingestion pipeline
│   └── ...
├── multimodal-pro-worker/      # Separate worker for image processing
│   ├── src/entry.py            # Llama 4 Scout vision + OCR + embedding
│   └── wrangler.toml           # Independent worker config
├── vectorize-mcp-tool/         # CLI + MCP server package
│   ├── src/vectorize_mcp_tool/ # Client, server, CLI
│   └── tests/                  # MCP tool unit tests
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests (no network)
│   ├── integration/            # Contract tests (worker <-> MCP tool sync)
│   └── e2e/                    # E2E tests + benchmarks (live worker)
├── schema.sql                  # D1 database DDL
├── wrangler.toml.example       # Template config (copy to wrangler.toml)
└── docs/                       # All documentation
```

## Testing

```bash
# Unit tests (no network, fast)
uv run pytest tests/unit/ --cov=src --cov-report=term-missing

# Integration/contract tests (no network)
uv run pytest tests/integration/

# MCP tool tests
cd vectorize-mcp-tool && uv run pytest tests/

# E2E tests (requires live worker)
VECTORIZE_E2E_URL=https://... VECTORIZE_E2E_API_KEY=... uv run pytest tests/e2e/ -m "not benchmark"

# Benchmarks (persists results, detects regressions)
VECTORIZE_E2E_URL=https://... VECTORIZE_E2E_API_KEY=... uv run pytest tests/e2e/ -m benchmark
```

Contract tests in `tests/integration/` verify that the worker and MCP tool stay in sync. Any endpoint change in the worker that isn't reflected in the MCP tool will fail these tests.

## Architecture

See `docs/` for detailed documentation:

- `docs/quickstart.md` -- Step-by-step first-time setup and endpoint testing
- `docs/production.md` -- Production deployment, security, monitoring, operations
- `docs/port_decisions.md` -- Technology choices and rationale
- `docs/component_mapping.md` -- TypeScript to Python mapping
- `docs/abstraction_layers.md` -- Protocol design and FFI patterns

## Credits

Original TypeScript implementation by [Daniel Nwaneri](https://github.com/dannwaneri/vectorize-mcp-worker).
