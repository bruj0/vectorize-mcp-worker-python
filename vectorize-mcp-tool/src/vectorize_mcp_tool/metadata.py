"""Canonical metadata for the Vectorize knowledge-base tool.

This module is the **single source of truth** for:
- tool description, operations, parameters, endpoints, and usage examples;
- the ``render_llms_txt()`` helper that produces the ``/llms.txt`` content.

Both ``server.py`` (FastMCP tool definition) and
``scripts/generate_llms_txt.py`` (code-generation of ``src/llms_txt.py``)
import from here.  Nothing in this module depends on Cloudflare / Pyodide.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tool-level description
# ---------------------------------------------------------------------------

TOOL_DESCRIPTION: str = (
    "Interact with the Vectorize knowledge base deployed on Cloudflare Workers. "
    "Supports hybrid semantic + keyword search with Reciprocal Rank Fusion (RRF) "
    "and cross-encoder reranking, document ingestion with automatic recursive "
    "chunking (15 % overlap), image ingestion with AI-generated descriptions "
    "(Llama 4 Scout vision + OCR), visual similarity search, index statistics, "
    "document/image retrieval, listing, deletion, license management, and "
    "database reset (requires passphrase). Use the 'operation' parameter to "
    "select the action."
)

# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

OPERATIONS: list[dict[str, Any]] = [
    {
        "name": "search_multimodal",
        "description": "Hybrid search returning documents and images with snippets and metadata. "
                       "Combines vector similarity + BM25 keyword matching using RRF, "
                       "optionally reranked by a cross-encoder model.",
        "required_params": ["query"],
        "optional_params": ["top_k", "rerank", "snippet_length"],
    },
    {
        "name": "search_documents",
        "description": "Hybrid search returning documents only (no images). Same search pipeline "
                       "as search_multimodal but filters out image results.",
        "required_params": ["query"],
        "optional_params": ["top_k", "rerank", "snippet_length"],
    },
    {
        "name": "ingest",
        "description": "Add a text document with automatic recursive chunking (15 % overlap). "
                       "Each chunk is embedded and stored in the vector index + D1 keyword store.",
        "required_params": ["id", "content"],
        "optional_params": ["category", "title"],
    },
    {
        "name": "ingest_image",
        "description": "Ingest an image with AI-generated description (Llama 4 Scout vision), "
                       "OCR extraction, and embedding. Requires an image URL.",
        "required_params": ["id", "image_url"],
        "optional_params": ["category", "title", "image_type"],
    },
    {
        "name": "stats",
        "description": "Return knowledge-base statistics: vector count, document count, dimensions.",
        "required_params": [],
        "optional_params": [],
    },
    {
        "name": "delete",
        "description": "Remove a document (text or image) by ID from both the vector index "
                       "and the keyword store.",
        "required_params": ["id"],
        "optional_params": [],
    },
    {
        "name": "get_document",
        "description": "Retrieve the full text document by ID, including metadata. "
                       "Returns an error if the ID refers to an image document.",
        "required_params": ["id"],
        "optional_params": [],
    },
    {
        "name": "get_image",
        "description": "Retrieve the full image document by ID, including AI description and metadata. "
                       "Returns an error if the ID refers to a text document.",
        "required_params": ["id"],
        "optional_params": [],
    },
    {
        "name": "list_documents",
        "description": "List documents with pagination, returning ID, title, category, "
                       "and creation timestamp for each document.",
        "required_params": [],
        "optional_params": ["limit", "offset"],
    },
    {
        "name": "license_validate",
        "description": "Validate a license key and return its plan, limits, and status.",
        "required_params": ["license_key"],
        "optional_params": [],
    },
    {
        "name": "license_create",
        "description": "Create a new license key for the given email address with the specified plan and limits.",
        "required_params": ["email"],
        "optional_params": ["plan", "max_documents", "max_queries_per_day"],
    },
    {
        "name": "license_list",
        "description": "List all licenses with their keys, emails, plans, and limits.",
        "required_params": [],
        "optional_params": [],
    },
    {
        "name": "license_revoke",
        "description": "Revoke (deactivate) a license key. The key remains in the database but becomes invalid.",
        "required_params": ["license_key"],
        "optional_params": [],
    },
    {
        "name": "delete_license",
        "description": "Permanently delete a license row from the database.",
        "required_params": ["license_key"],
        "optional_params": [],
    },
    {
        "name": "reset_all",
        "description": "Wipe ALL databases (documents, vectors, and licenses). "
                       "Requires the reset passphrase configured via POST /init/reset-passphrase.",
        "required_params": ["passphrase"],
        "optional_params": [],
    },
    {
        "name": "reset_documents",
        "description": "Wipe documents and vectors only (licenses are preserved). "
                       "Requires the reset passphrase.",
        "required_params": ["passphrase"],
        "optional_params": [],
    },
    {
        "name": "reset_licenses",
        "description": "Wipe licenses only (documents are preserved). Requires the reset passphrase.",
        "required_params": ["passphrase"],
        "optional_params": [],
    },
]

OPERATION_NAMES: list[str] = [op["name"] for op in OPERATIONS]

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

PARAMETERS: dict[str, dict[str, Any]] = {
    "operation": {
        "type": "string",
        "description": (
            "Operation to perform. One of: " + ", ".join(f"'{n}'" for n in OPERATION_NAMES) + "."
        ),
        "enum": OPERATION_NAMES,
        "required": True,
    },
    "query": {
        "type": "string",
        "description": "Search query text. Required for search_multimodal and search_documents.",
    },
    "top_k": {
        "type": "integer",
        "description": "Number of results to return (1-20, default 5). Used by search operations.",
        "default": 5,
        "range": [1, 20],
    },
    "rerank": {
        "type": "boolean",
        "description": (
            "Whether to use cross-encoder reranking via @cf/baai/bge-reranker-base (default true). "
            "Improves result quality at slight latency cost. Used by search operations."
        ),
        "default": True,
    },
    "snippet_length": {
        "type": "integer",
        "description": (
            "Maximum snippet length in characters (50-500, default 200). "
            "Controls how much of each matching document is returned in search results."
        ),
        "default": 200,
        "range": [50, 500],
    },
    "id": {
        "type": "string",
        "description": (
            "Document or image ID. Required for ingest, ingest_image, delete, "
            "get_document, and get_image."
        ),
    },
    "content": {
        "type": "string",
        "description": "Full text content of the document to ingest. Required for 'ingest'.",
    },
    "category": {
        "type": "string",
        "description": "Optional category tag for 'ingest' and 'ingest_image'. Used for filtering.",
    },
    "title": {
        "type": "string",
        "description": "Optional title for 'ingest' and 'ingest_image'. Stored as metadata.",
    },
    "image_url": {
        "type": "string",
        "description": (
            "Publicly accessible image URL for 'ingest_image'. The image will be fetched, "
            "described by the vision model, OCR'd, and embedded."
        ),
    },
    "image_type": {
        "type": "string",
        "description": (
            "Image type hint for 'ingest_image' that influences the vision model prompt. "
            "One of: 'screenshot', 'diagram', 'photo', 'document', 'chart', 'auto'. Default: 'auto'."
        ),
        "default": "auto",
        "enum": ["screenshot", "diagram", "photo", "document", "chart", "auto"],
    },
    "license_key": {
        "type": "string",
        "description": "License key string. Required for license_validate, license_revoke, delete_license.",
    },
    "email": {
        "type": "string",
        "description": "Email address for license_create. The license will be associated with this email.",
    },
    "plan": {
        "type": "string",
        "description": "Plan tier for license_create. One of: 'standard', 'pro', 'enterprise'. Default: 'standard'.",
        "default": "standard",
        "enum": ["standard", "pro", "enterprise"],
    },
    "max_documents": {
        "type": "integer",
        "description": "Maximum number of documents allowed for the license. Used by license_create.",
    },
    "max_queries_per_day": {
        "type": "integer",
        "description": "Maximum number of queries per day allowed for the license. Used by license_create.",
    },
    "limit": {
        "type": "integer",
        "description": "Pagination limit (1-200, default 50). Used by list_documents.",
        "default": 50,
        "range": [1, 200],
    },
    "offset": {
        "type": "integer",
        "description": "Pagination offset (default 0). Used by list_documents.",
        "default": 0,
    },
    "passphrase": {
        "type": "string",
        "description": (
            "Reset passphrase. Required for reset_all, reset_documents, and reset_licenses. "
            "Must be configured first via POST /init/reset-passphrase."
        ),
    },
}

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

ENDPOINTS: list[dict[str, Any]] = [
    {"method": "GET",    "path": "/",                      "auth": False,  "description": "API documentation and endpoint list"},
    {"method": "GET",    "path": "/health/check",          "auth": False,  "description": "Health check and binding status"},
    {"method": "GET",    "path": "/dashboard",             "auth": False,  "description": "Interactive playground UI"},
    {"method": "GET",    "path": "/llms.txt",              "auth": False,  "description": "AI search engine optimization info (this document)"},
    {"method": "POST",   "path": "/search/multimodal",     "auth": True,   "description": "Hybrid semantic search returning documents + images"},
    {"method": "POST",   "path": "/search/documents",      "auth": True,   "description": "Hybrid semantic search returning documents only"},
    {"method": "POST",   "path": "/search/similar-images",  "auth": True,  "description": "Visual similarity search across ingested images"},
    {"method": "POST",   "path": "/ingest/document",       "auth": True,   "description": "Ingest a text document with automatic chunking"},
    {"method": "POST",   "path": "/ingest/image",          "auth": True,   "description": "Ingest an image with AI description and OCR"},
    {"method": "GET",    "path": "/stats/index",           "auth": True,   "description": "Index statistics (vector count, document count, dimensions)"},
    {"method": "GET",    "path": "/get/document/:id",      "auth": True,   "description": "Retrieve full text document by ID"},
    {"method": "GET",    "path": "/get/image/:id",         "auth": True,   "description": "Retrieve full image document by ID"},
    {"method": "GET",    "path": "/list/documents",        "auth": True,   "description": "List documents with pagination"},
    {"method": "POST",   "path": "/init/reset-passphrase", "auth": True,   "description": "Set or rotate the reset passphrase"},
    {"method": "POST",   "path": "/reset/all",             "auth": True,   "description": "Wipe all databases (requires passphrase)"},
    {"method": "POST",   "path": "/reset/documents",       "auth": True,   "description": "Wipe documents + vectors (requires passphrase)"},
    {"method": "POST",   "path": "/reset/licenses",        "auth": True,   "description": "Wipe licenses only (requires passphrase)"},
    {"method": "POST",   "path": "/license/validate",      "auth": True,   "description": "Validate a license key"},
    {"method": "POST",   "path": "/license/create",        "auth": True,   "description": "Create a new license key"},
    {"method": "GET",    "path": "/license/list",          "auth": True,   "description": "List all licenses"},
    {"method": "POST",   "path": "/license/revoke",        "auth": True,   "description": "Revoke (deactivate) a license key"},
    {"method": "DELETE", "path": "/delete/document/:id",   "auth": True,   "description": "Delete a document by ID"},
    {"method": "DELETE", "path": "/delete/license/:key",   "auth": True,   "description": "Delete a license by key"},
]

# ---------------------------------------------------------------------------
# Usage examples
# ---------------------------------------------------------------------------

USAGE_EXAMPLES: dict[str, dict[str, Any]] = {
    "search_multimodal": {
        "operation": "search_multimodal",
        "query": "How does authentication work?",
        "top_k": 5,
        "rerank": True,
        "snippet_length": 200,
    },
    "search_documents": {
        "operation": "search_documents",
        "query": "database migration steps",
        "top_k": 10,
    },
    "ingest": {
        "operation": "ingest",
        "id": "doc-setup-guide",
        "content": "# Setup Guide\n\nFollow these steps to set up the application...",
        "category": "documentation",
        "title": "Setup Guide",
    },
    "ingest_image": {
        "operation": "ingest_image",
        "id": "img-architecture-diagram",
        "image_url": "https://example.com/architecture.png",
        "image_type": "diagram",
        "title": "Architecture Diagram",
    },
    "get_document": {
        "operation": "get_document",
        "id": "doc-setup-guide",
    },
    "stats": {
        "operation": "stats",
    },
    "list_documents": {
        "operation": "list_documents",
        "limit": 20,
        "offset": 0,
    },
    "license_create": {
        "operation": "license_create",
        "email": "user@example.com",
        "plan": "standard",
    },
}


# ---------------------------------------------------------------------------
# render_llms_txt() -- produces the /llms.txt content
# ---------------------------------------------------------------------------

def render_llms_txt() -> str:
    """Render the ``/llms.txt`` content from the canonical metadata.

    The output is a human-readable Markdown document suitable for AI search
    engine optimization.  It includes the tool description, endpoints,
    operations, parameters, usage examples, and a note directing AI agents
    to use the ``vectorize-mcp-tool`` package for MCP integration.
    """
    lines: list[str] = []

    # -- header
    lines.append("# Vectorize MCP Worker")
    lines.append("> Production-Grade Hybrid RAG with Multimodal Support on Cloudflare Edge")
    lines.append("")

    # -- overview
    lines.append("## Overview")
    lines.append(TOOL_DESCRIPTION)
    lines.append("")

    # -- capabilities
    lines.append("## Capabilities")
    lines.append("- Hybrid search (Vector + BM25) with Reciprocal Rank Fusion")
    lines.append("- Cross-encoder reranking (@cf/baai/bge-reranker-base)")
    lines.append("- Multimodal image processing (Llama 4 Scout vision + OCR)")
    lines.append("- Visual similarity search across ingested images")
    lines.append("- Recursive document chunking with 15% overlap")
    lines.append("- One-time license key system")
    lines.append("- MCP tool integration for AI agents (via vectorize-mcp-tool)")
    lines.append("- Interactive dashboard playground")
    lines.append("- Sub-second latency at edge")
    lines.append("")

    # -- endpoints
    lines.append("## API Endpoints")
    lines.append("")
    public = [e for e in ENDPOINTS if not e["auth"]]
    authed = [e for e in ENDPOINTS if e["auth"]]

    lines.append("### Public (no authentication)")
    for ep in public:
        lines.append(f"- {ep['method']} {ep['path']} - {ep['description']}")
    lines.append("")

    lines.append("### Authenticated (Bearer token required)")
    for ep in authed:
        lines.append(f"- {ep['method']} {ep['path']} - {ep['description']}")
    lines.append("")

    # -- operations
    lines.append("## MCP Operations")
    lines.append("")
    lines.append(
        "All MCP operations should be performed through the **vectorize-mcp-tool** "
        "Python package, which provides both a CLI and a FastMCP stdio server for "
        "AI agents (Cursor, Claude Desktop, etc.)."
    )
    lines.append("")
    lines.append("Available operations:")
    lines.append("")
    for op in OPERATIONS:
        req = ", ".join(op["required_params"]) if op["required_params"] else "none"
        opt = ", ".join(op["optional_params"]) if op["optional_params"] else "none"
        lines.append(f"### {op['name']}")
        lines.append(f"{op['description']}")
        lines.append(f"- Required params: {req}")
        lines.append(f"- Optional params: {opt}")
        lines.append("")

    # -- parameters
    lines.append("## Parameters Reference")
    lines.append("")
    for pname, pspec in PARAMETERS.items():
        parts = [f"**{pname}** ({pspec['type']})"]
        if "default" in pspec:
            parts.append(f"default: {pspec['default']}")
        if "range" in pspec:
            parts.append(f"range: {pspec['range'][0]}-{pspec['range'][1]}")
        if "enum" in pspec:
            parts.append(f"enum: {', '.join(str(v) for v in pspec['enum'])}")
        lines.append(f"- {' | '.join(parts)}: {pspec['description']}")
    lines.append("")

    # -- technical stack
    lines.append("## Technical Stack")
    lines.append("- Runtime: Cloudflare Workers (Python / Pyodide)")
    lines.append("- Vector DB: Cloudflare Vectorize (384 dimensions, cosine)")
    lines.append("- SQL: Cloudflare D1")
    lines.append("- Embedding: @cf/baai/bge-small-en-v1.5 (384 dimensions)")
    lines.append("- Reranker: @cf/baai/bge-reranker-base")
    lines.append("- Vision: @cf/meta/llama-4-scout-17b-16e-instruct (via multimodal worker)")
    lines.append("")

    # -- usage examples
    lines.append("## Usage Examples")
    lines.append("")
    lines.append("### Search")
    lines.append("```bash")
    lines.append(
        'curl -X POST /search/multimodal -H "Authorization: Bearer KEY" '
        '-H "Content-Type: application/json" '
        """-d '{"query": "your question", "topK": 5, "rerank": true}'"""
    )
    lines.append("```")
    lines.append("")
    lines.append("### Ingest")
    lines.append("```bash")
    lines.append(
        'curl -X POST /ingest/document -H "Authorization: Bearer KEY" '
        '-H "Content-Type: application/json" '
        """-d '{"id": "doc-1", "content": "...", "category": "docs"}'"""
    )
    lines.append("```")
    lines.append("")

    # -- MCP integration
    lines.append("## MCP Integration")
    lines.append("")
    lines.append(
        "All MCP operations should be performed through the **vectorize-mcp-tool** "
        "Python package. Install with `pip install vectorize-mcp-tool` or "
        "`uv pip install vectorize-mcp-tool`."
    )
    lines.append("")
    lines.append("Configure your AI agent (Cursor, Claude Desktop, etc.) with:")
    lines.append("```json")
    lines.append('{')
    lines.append('  "mcpServers": {')
    lines.append('    "vectorize": {')
    lines.append('      "command": "vectorize-mcp-server",')
    lines.append('      "env": {')
    lines.append('        "VECTORIZE_URL": "https://your-worker.workers.dev",')
    lines.append('        "VECTORIZE_API_KEY": "your-api-key"')
    lines.append('      }')
    lines.append('    }')
    lines.append('  }')
    lines.append('}')
    lines.append("```")
    lines.append("")

    # -- links
    lines.append("## Links")
    lines.append("- GitHub: https://github.com/bruj0/vectorize-mcp-worker-python")
    lines.append("- Dashboard: /dashboard")
    lines.append("")

    return "\n".join(lines)
