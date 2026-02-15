# vectorize-mcp-tool

CLI and MCP server for the [Vectorize knowledge base worker](../README.md).

Two entry points in one package:

| Command | Purpose |
|---------|---------|
| `vectorize-mcp` | Interactive CLI for every REST endpoint |
| `vectorize-mcp-server` | stdio MCP server for Cursor / AI agents |

## Installation

### From the local checkout (recommended during development)

```bash
# Install as a uv tool (isolated environment, available globally)
uv tool install ./vectorize-mcp-tool

# Or install with pip
pip install ./vectorize-mcp-tool
```

### From PyPI (once published)

```bash
pip install vectorize-mcp-tool
# or
uv tool install vectorize-mcp-tool
```

### Run without installing

```bash
# Using uvx (uv's npx equivalent)
uvx --from ./vectorize-mcp-tool vectorize-mcp --help
```

## Configuration

Both the CLI and the MCP server need two values:

| Setting | CLI flag | Environment variable |
|---------|----------|---------------------|
| Worker URL | `--url` | `VECTORIZE_URL` |
| API key | `--api-key` | `VECTORIZE_API_KEY` |

CLI flags take precedence over environment variables. The MCP server reads only from environment variables.

```bash
export VECTORIZE_URL="https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev"
export VECTORIZE_API_KEY="your-api-key"
```

## CLI usage

```
vectorize-mcp [--url URL] [--api-key KEY] COMMAND [ARGS]
```

### Commands

```bash
# Health check (no auth required)
vectorize-mcp health

# Search (multimodal: documents + images)
vectorize-mcp search multimodal "memory safety" --top-k 5 --rerank

# Search documents only
vectorize-mcp search documents "memory safety" --top-k 5 --rerank

# Find similar images
vectorize-mcp search similar-images --file photo.jpg --top-k 3

# Ingest a document
vectorize-mcp ingest document --id doc-python --content "Python is a programming language." --category programming

# Ingest an image
vectorize-mcp ingest image --id img-001 --file photo.jpg --image-type photo

# Get a document or image by ID
vectorize-mcp get document doc-python
vectorize-mcp get image img-001

# List documents
vectorize-mcp list documents

# Index statistics
vectorize-mcp stats

# Delete a document or license
vectorize-mcp delete document doc-python
vectorize-mcp delete license LICENSE_KEY

# Reset (each prompts for passphrase)
vectorize-mcp reset init-passphrase
vectorize-mcp reset all
vectorize-mcp reset documents
vectorize-mcp reset licenses

# License management
vectorize-mcp license create --email user@example.com --plan pro
vectorize-mcp license validate LICENSE_KEY
vectorize-mcp license list
vectorize-mcp license revoke LICENSE_KEY

# Start MCP server (for Cursor)
vectorize-mcp serve
```

All commands output JSON to stdout. Errors go to stderr with a non-zero exit code.

### Piping and scripting

```bash
# Extract document IDs from search results
vectorize-mcp search multimodal "kubernetes" | python3 -c "
import json, sys
for r in json.load(sys.stdin)['results']:
    print(r['id'])
"

# Bulk ingest from a JSONL file
while IFS= read -r line; do
  id=$(echo "$line" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  content=$(echo "$line" | python3 -c "import json,sys; print(json.load(sys.stdin)['content'])")
  vectorize-mcp ingest document --id "$id" --content "$content"
done < documents.jsonl
```

## MCP server for Cursor

### Option A: Using the installed package

After installing with `uv tool install` or `pip install`, create `.cursor/mcp.json` in your project root:

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

### Option B: Using uvx (no global install)

```json
{
  "mcpServers": {
    "vectorize": {
      "command": "uvx",
      "args": [
        "--from", "/absolute/path/to/vectorize-mcp-tool",
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

### Option C: Via the CLI serve command

```json
{
  "mcpServers": {
    "vectorize": {
      "command": "vectorize-mcp",
      "args": ["serve"],
      "env": {
        "VECTORIZE_URL": "https://vectorize-mcp-worker-python.<your-subdomain>.workers.dev",
        "VECTORIZE_API_KEY": "your-api-key"
      }
    }
  }
}
```

### Verify in Cursor

1. Open **Settings** > **MCP**
2. The **vectorize** server should show a green dot (connected)
3. Open Agent chat (Cmd+L) and try: *"Search the knowledge base for Python"*

## Using as a library

```python
import asyncio
from vectorize_mcp_tool import VectorizeClient

async def main():
    client = VectorizeClient(
        "https://vectorize-mcp-worker-python.example.workers.dev",
        "your-api-key",
    )
    results = await client.search("machine learning", top_k=3)
    print(results)

asyncio.run(main())
```

## Development

```bash
cd vectorize-mcp-tool

# Install in development mode
uv pip install -e .

# Run the CLI
vectorize-mcp --help

# Run the MCP server
vectorize-mcp-server
```

## Testing

```bash
cd vectorize-mcp-tool

# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=src/vectorize_mcp_tool --cov-report=term-missing
```

Tests cover:
- **`test_client.py`**: HTTP request construction and response handling (via `httpx.MockTransport`)
- **`test_cli.py`**: CLI structure, help text, command routing (via Click `CliRunner`)

### E2E Benchmarking

Integration with the worker's benchmark framework lives in `tests/e2e/` at the project root:

```bash
# From project root
VECTORIZE_E2E_URL=https://... VECTORIZE_E2E_API_KEY=... uv run pytest tests/e2e/ -m benchmark
```

Historical results are stored in `tests/e2e/benchmark_results.json` and compared across runs to detect performance regressions (>20% slower flags a warning).
