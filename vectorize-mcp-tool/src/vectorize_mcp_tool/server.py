"""FastMCP stdio server -- single ``vectorize`` tool for Cursor / AI agents.

Reads configuration from environment variables:
    VECTORIZE_URL  -- deployed worker URL (required)
    VECTORIZE_API_KEY -- Bearer token (required)

Entry point ``main()`` is registered as ``vectorize-mcp-server`` in pyproject.toml.

All MCP operations dispatch directly to the worker's REST endpoints via
``VectorizeClient``.  There is no /mcp proxy -- the MCP tool IS the interface.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Literal

from mcp.server.fastmcp import FastMCP

from vectorize_mcp_tool.client import VectorizeClient
from vectorize_mcp_tool.metadata import (
    OPERATIONS,
    OPERATION_NAMES,
    TOOL_DESCRIPTION,
)

# ── Configuration ─────────────────────────────────────────────────────────────

_OperationType = Literal[
    "search_multimodal", "search_documents",
    "ingest", "ingest_image", "stats", "delete",
    "get_document", "get_image", "list_documents",
    "license_validate", "license_create", "license_list",
    "license_revoke", "delete_license",
    "reset_all", "reset_documents", "reset_licenses",
]


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"ERROR: {name} environment variable is required", file=sys.stderr)
        sys.exit(1)
    return value


# ── Server instance ───────────────────────────────────────────────────────────

server = FastMCP(
    "vectorize-knowledge-base",
    instructions=(
        "Interact with a Vectorize knowledge base deployed on Cloudflare Workers. "
        "Supports hybrid semantic + keyword search with reranking, document ingestion "
        "with automatic chunking, image ingestion with AI-generated descriptions, "
        "index statistics, document/image retrieval, listing, deletion, license "
        "management, and database reset (requires passphrase)."
    ),
)


def _build_operations_doc() -> str:
    """Build the operations section of the tool docstring from metadata."""
    lines: list[str] = []
    for op in OPERATIONS:
        req = ", ".join(op["required_params"]) if op["required_params"] else "none"
        lines.append(f"  - {op['name']}: {op['description']} (required: {req})")
    return "\n".join(lines)


_OPERATIONS_DOC = _build_operations_doc()


@server.tool()
async def vectorize(
    operation: _OperationType,
    query: str | None = None,
    top_k: int = 5,
    rerank: bool = True,
    snippet_length: int = 200,
    id: str | None = None,
    content: str | None = None,
    category: str | None = None,
    title: str | None = None,
    image_url: str | None = None,
    image_type: str = "auto",
    license_key: str | None = None,
    email: str | None = None,
    plan: str = "standard",
    max_documents: int | None = None,
    max_queries_per_day: int | None = None,
    limit: int = 50,
    offset: int = 0,
    passphrase: str | None = None,
) -> str:
    """Interact with the Vectorize knowledge base.

    This tool provides access to a production-grade hybrid RAG system deployed
    on Cloudflare Workers.  It combines vector similarity search (384-dim
    embeddings via @cf/baai/bge-small-en-v1.5) with BM25 keyword matching using
    Reciprocal Rank Fusion (RRF).  Results can optionally be reranked by a
    cross-encoder model (@cf/baai/bge-reranker-base) for higher quality.

    The knowledge base supports multimodal content: text documents are
    recursively chunked (15 % overlap) and embedded; images are described by
    Llama 4 Scout vision, OCR'd, and embedded alongside text content.

    Operations:
{operations}

    Parameters:
        operation: The operation to perform (see list above).  Required.
        query: Search query text.  Required for search_multimodal and
            search_documents.
        top_k: Number of results to return (1-20, default 5).  Used by search
            operations.
        rerank: Whether to apply cross-encoder reranking via
            @cf/baai/bge-reranker-base (default true).  Improves relevance at
            slight latency cost.  Used by search operations.
        snippet_length: Maximum snippet length in characters (50-500,
            default 200).  Controls how much of each matching document is
            returned in search results.
        id: Document or image ID.  Required for ingest, ingest_image, delete,
            get_document, and get_image.
        content: Full text content of the document.  Required for 'ingest'.
        category: Optional category tag for ingest and ingest_image.
        title: Optional title for ingest and ingest_image.
        image_url: Publicly accessible image URL for ingest_image.
        image_type: Image type hint for ingest_image that influences the vision
            model prompt: 'screenshot', 'diagram', 'photo', 'document',
            'chart', or 'auto' (default: 'auto').
        license_key: License key string.  Required for license_validate,
            license_revoke, and delete_license.
        email: Email address for license_create.
        plan: Plan tier for license_create: 'standard', 'pro', or 'enterprise'
            (default: 'standard').
        max_documents: Maximum documents limit for license_create.
        max_queries_per_day: Maximum daily queries for license_create.
        limit: Pagination limit for list_documents (1-200, default 50).
        offset: Pagination offset for list_documents (default 0).
        passphrase: Reset passphrase.  Required for reset_all,
            reset_documents, and reset_licenses.  Must be configured first
            via POST /init/reset-passphrase on the worker.

    Returns:
        JSON string with the operation result.  Structure depends on operation:
        - search_*: {{"result": {{"results": [...], "performance": {{...}}}}}}
          Each result has id, snippet, score, category, isImage, title, source.
        - ingest: {{"result": {{"success": true, "chunks": N, "performance": {{...}}}}}}
        - stats: {{"result": {{"vectors": N, "documents": N, "dimensions": N}}}}
        - delete: {{"result": {{"success": true, "deleted": "id"}}}}
        - get_document / get_image: {{"result": {{...document fields...}}}}
        - list_documents: {{"result": {{"documents": [...], "limit": N, "offset": N}}}}
        - license_validate: {{"result": {{"valid": bool, "plan": "...", "limits": {{...}}}}}}
        - license_create: {{"result": {{"success": true, "license_key": "...", ...}}}}
        - license_list: {{"result": {{"licenses": [...]}}}}
        - license_revoke: {{"result": {{"success": true, "revoked": "key"}}}}
        - delete_license: {{"result": {{"success": true, "deleted": "key"}}}}
        - reset_*: {{"result": {{"success": true, "deleted": {{...counts...}}}}}}

    Examples:
        >>> await vectorize(operation="search_multimodal", query="authentication flow", top_k=5)
        >>> await vectorize(operation="ingest", id="doc-1", content="...", category="docs", title="Guide")
        >>> await vectorize(operation="get_document", id="doc-1")
        >>> await vectorize(operation="stats")
        >>> await vectorize(operation="list_documents", limit=20, offset=0)
    """.format(operations=_OPERATIONS_DOC)

    url = _require_env("VECTORIZE_URL")
    api_key = _require_env("VECTORIZE_API_KEY")
    client = VectorizeClient(url, api_key)

    # ── Dispatch to the appropriate REST endpoint ────────────────────────

    # Search
    if operation == "search_multimodal":
        if not query:
            return json.dumps({"error": "query is required for search_multimodal"})
        result = await client.search_multimodal(
            query, top_k=top_k, rerank=rerank, snippet_length=snippet_length,
        )
    elif operation == "search_documents":
        if not query:
            return json.dumps({"error": "query is required for search_documents"})
        result = await client.search_documents(
            query, top_k=top_k, rerank=rerank, snippet_length=snippet_length,
        )

    # Ingest
    elif operation == "ingest":
        if not id or not content:
            return json.dumps({"error": "id and content are required for ingest"})
        result = await client.ingest(
            id, content, category=category, title=title,
        )
    elif operation == "ingest_image":
        if not id or not image_url:
            return json.dumps({"error": "id and image_url are required for ingest_image. "
                               "Use the REST endpoint POST /ingest/image for file uploads."})
        # The MCP tool cannot do multipart file upload; guide the user.
        result = {"error": (
            "ingest_image via MCP requires image upload through the "
            "POST /ingest/image HTTP endpoint directly. "
            "Provide id, image_url, category, title, and imageType in "
            "multipart form data."
        )}

    # Stats
    elif operation == "stats":
        result = await client.stats()

    # Retrieval
    elif operation == "get_document":
        if not id:
            return json.dumps({"error": "id is required for get_document"})
        result = await client.get_document(id)
    elif operation == "get_image":
        if not id:
            return json.dumps({"error": "id is required for get_image"})
        result = await client.get_image(id)
    elif operation == "list_documents":
        result = await client.list_documents(limit=limit, offset=offset)

    # Deletion
    elif operation == "delete":
        if not id:
            return json.dumps({"error": "id is required for delete"})
        result = await client.delete(id)

    # License
    elif operation == "license_validate":
        if not license_key:
            return json.dumps({"error": "license_key is required for license_validate"})
        result = await client.license_validate(license_key)
    elif operation == "license_create":
        if not email:
            return json.dumps({"error": "email is required for license_create"})
        result = await client.license_create(
            email, plan=plan,
            max_documents=max_documents,
            max_queries_per_day=max_queries_per_day,
        )
    elif operation == "license_list":
        result = await client.license_list()
    elif operation == "license_revoke":
        if not license_key:
            return json.dumps({"error": "license_key is required for license_revoke"})
        result = await client.license_revoke(license_key)
    elif operation == "delete_license":
        if not license_key:
            return json.dumps({"error": "license_key is required for delete_license"})
        result = await client.delete_license(license_key)

    # Reset (passphrase-gated)
    elif operation == "reset_all":
        if not passphrase:
            return json.dumps({"error": "passphrase is required for reset_all"})
        result = await client.reset_all(passphrase)
    elif operation == "reset_documents":
        if not passphrase:
            return json.dumps({"error": "passphrase is required for reset_documents"})
        result = await client.reset_documents(passphrase)
    elif operation == "reset_licenses":
        if not passphrase:
            return json.dumps({"error": "passphrase is required for reset_licenses"})
        result = await client.reset_licenses(passphrase)

    else:
        result = {"error": f"Unknown operation: {operation}"}

    return json.dumps(result, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Start the MCP server over stdio."""
    # Validate env vars early so errors surface before the server blocks on stdin
    _require_env("VECTORIZE_URL")
    _require_env("VECTORIZE_API_KEY")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
