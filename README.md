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

- [uv](https://docs.astral.sh/uv/#installation)
- [Node.js](https://nodejs.org/)
- A Cloudflare account with Workers, Vectorize, D1, and Workers AI enabled

### Install

```bash
uv init
uv tool install workers-py
```

### Configure

1. Copy `wrangler.toml` and fill in your D1 database ID
2. Create the Vectorize index:

```bash
pywrangler vectorize create mcp-knowledge-base --dimensions=384 --metric=cosine
```

3. Create the D1 database and run the schema:

```bash
pywrangler d1 create mcp-knowledge-db
pywrangler d1 execute mcp-knowledge-db --remote --file=./schema.sql
```

4. Set your API key:

```bash
pywrangler secret put API_KEY
```

### Development

```bash
uv run pywrangler dev
```

### Deploy

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
