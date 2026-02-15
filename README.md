# Vectorize MCP Worker (Python)

Production-Grade Hybrid RAG with Multimodal Support on Cloudflare Edge in Python.

## Features

- Hybrid Search (Vector + BM25) with Reciprocal Rank Fusion
- Multimodal Image Processing (Llama 4 Scout)
- Cross-Encoder Reranking (`bge-reranker-base`)
- Recursive Chunking with 15% overlap
- One-time License System
- Interactive Dashboard at `/dashboard`
- MCP tool integration (`/mcp/tools`, `/mcp/call`)

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

The project requires three Cloudflare services: **Vectorize** (vector database), **D1** (SQL database), and **Workers AI** (inference). Workers AI is enabled automatically; the other two need to be created.

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

Set the API key that protects write operations (`/ingest`, `/license/*`):

```bash
wrangler secret put API_KEY
```

You will be prompted to enter the secret value interactively. This is stored encrypted and never appears in `wrangler.toml`.

### Development

Start a local dev server with hot reload:

```bash
uv run pywrangler dev
```

### Deploy

Build and deploy to Cloudflare's global edge network:

```bash
uv run pywrangler deploy
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API documentation |
| `/test` | GET | Health check |
| `/dashboard` | GET | Interactive playground UI |
| `/llms.txt` | GET | AI search engine info |
| `/stats` | GET | Index statistics |
| `/search` | POST | Hybrid search |
| `/ingest` | POST | Document ingestion |
| `/ingest-image` | POST | Image ingestion |
| `/documents/:id` | DELETE | Delete document |
| `/license/validate` | POST | Validate license |
| `/license/create` | POST | Create license |
| `/license/list` | GET | List licenses |
| `/license/revoke` | POST | Revoke license |
| `/mcp/tools` | GET | List MCP tools |
| `/mcp/call` | POST | Execute MCP tool |

## MCP Integration

The server exposes a single MCP tool `vectorize` with multiple operations:

```json
{
  "tool": "vectorize",
  "arguments": {
    "operation": "search",
    "query": "your question here",
    "top_k": 5,
    "rerank": true
  }
}
```

Operations: `search`, `ingest`, `ingest_image`, `stats`, `delete`, `license_validate`, `license_create`, `license_list`, `license_revoke`.

## Architecture

See `docs/` for detailed documentation:

- `docs/port_decisions.md` -- Technology choices and rationale
- `docs/component_mapping.md` -- TypeScript to Python mapping
- `docs/abstraction_layers.md` -- Protocol design and FFI patterns

## Credits

Original TypeScript implementation by [Daniel Nwaneri](https://github.com/dannwaneri/vectorize-mcp-worker).
