"""llms.txt content for AI search engine optimization.

Identical content to the TS original's getLlmsTxt() function.
"""


def get_llms_txt() -> str:
    """Return the llms.txt content. Same as TS getLlmsTxt()."""
    return """# Vectorize MCP Worker
> Production-Grade Hybrid RAG with Multimodal Support on Cloudflare Edge

## Overview
A semantic search API combining vector similarity with BM25 keyword matching, using Reciprocal Rank Fusion (RRF) and cross-encoder reranking for optimal results. Includes multimodal image processing, a license system, and MCP tool integration for AI agents.

## Capabilities
- Hybrid search (Vector + BM25) with Reciprocal Rank Fusion
- Cross-encoder reranking
- Multimodal image processing (Llama 4 Scout vision + OCR)
- Visual similarity search across ingested images
- Recursive document chunking with 15% overlap
- One-time license key system
- MCP tool integration for AI agents
- Interactive dashboard playground
- Sub-second latency at edge

## API Endpoints

### Public (no authentication)
- GET / - API documentation
- GET /test - Health check and binding status
- GET /dashboard - Interactive playground UI
- GET /llms.txt - AI search engine info (this document)
- GET /mcp/tools - MCP tool schema

### Authenticated (Bearer token required)
- POST /search - Hybrid semantic search (vector + BM25 + reranking)
- POST /ingest - Document ingestion with auto-chunking
- POST /ingest-image - Image ingestion with AI description, OCR, and embedding
- POST /find-similar-images - Visual similarity search
- DELETE /documents/:id - Remove documents
- GET /stats - Index statistics

### License Management (Bearer token required)
- POST /license/create - Create a license key
- POST /license/validate - Validate a license key
- GET /license/list - List all licenses
- POST /license/revoke - Revoke a license key

### MCP (Bearer token required)
- POST /mcp/call - Execute MCP tool (search, ingest, stats, delete, license operations)

## Technical Stack
- Runtime: Cloudflare Workers (Python / Pyodide)
- Vector DB: Cloudflare Vectorize (384 dimensions, cosine)
- SQL: Cloudflare D1
- Embedding: @cf/baai/bge-small-en-v1.5 (384 dimensions)
- Reranker: @cf/baai/bge-reranker-base
- Vision: @cf/meta/llama-4-scout-17b-16e-instruct (via multimodal worker)

## Use Cases
- Knowledge base search
- Document retrieval
- Semantic Q&A systems
- RAG pipelines
- Image cataloging and visual search
- AI agent tool backends (via MCP)

## Integration
```bash
# Search
curl -X POST /search -H "Authorization: Bearer KEY" -H "Content-Type: application/json" -d '{"query": "your question", "topK": 5, "rerank": true}'

# Ingest
curl -X POST /ingest -H "Authorization: Bearer KEY" -H "Content-Type: application/json" -d '{"id": "doc-1", "content": "...", "category": "docs"}'

# MCP tool call
curl -X POST /mcp/call -H "Authorization: Bearer KEY" -H "Content-Type: application/json" -d '{"tool": "vectorize", "arguments": {"operation": "search", "query": "..."}}'
```

## Links
- GitHub: https://github.com/bruj0/vectorize-mcp-worker-python
- Dashboard: /dashboard
"""
