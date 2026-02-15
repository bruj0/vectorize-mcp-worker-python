"""MCP tool definition and dispatch -- one tool with operations.

Follows the cerebrov2 pattern: one tool 'vectorize' with an 'operation'
parameter that dispatches to search, ingest, ingest_image, stats, delete,
license_validate, license_create, license_list, license_revoke.

The /mcp/tools endpoint returns the tool schema.
The /mcp/call endpoint dispatches { tool: "vectorize", arguments: { operation: "...", ... } }.
"""

from __future__ import annotations

import json
from typing import Any

from src.auth import json_response


# MCP tool schema -- returned by GET /mcp/tools
TOOL_SCHEMA: dict[str, Any] = {
    "tools": [
        {
            "name": "vectorize",
            "description": (
                "Interact with the Vectorize knowledge base. Supports hybrid semantic + keyword "
                "search with reranking, document ingestion with automatic chunking, image ingestion "
                "with AI-generated descriptions, index statistics, document deletion, and license "
                "management. Use the 'operation' parameter to select the action."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": (
                            "Operation to perform: 'search' (hybrid semantic + keyword search), "
                            "'ingest' (add document with auto-chunking), "
                            "'ingest_image' (ingest image with AI description), "
                            "'stats' (knowledge base statistics), "
                            "'delete' (remove document by ID), "
                            "'license_validate' (validate a license key), "
                            "'license_create' (create a new license), "
                            "'license_list' (list all licenses), "
                            "'license_revoke' (revoke a license)"
                        ),
                        "enum": [
                            "search", "ingest", "ingest_image", "stats", "delete",
                            "license_validate", "license_create", "license_list", "license_revoke",
                        ],
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (required for 'search' operation)",
                    },
                    "top_k": {
                        "type": "number",
                        "description": "Number of results (1-20, default 5). Used by 'search'.",
                        "default": 5,
                    },
                    "rerank": {
                        "type": "boolean",
                        "description": "Use cross-encoder reranking (default true). Used by 'search'.",
                        "default": True,
                    },
                    "id": {
                        "type": "string",
                        "description": (
                            "Document ID. Required for 'ingest', 'ingest_image', 'delete'."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Document content. Required for 'ingest'.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category for 'ingest' and 'ingest_image'.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional title for 'ingest' and 'ingest_image'.",
                    },
                    "image_url": {
                        "type": "string",
                        "description": "Image URL for 'ingest_image'.",
                    },
                    "image_type": {
                        "type": "string",
                        "description": (
                            "Image type hint for 'ingest_image': "
                            "'screenshot', 'diagram', 'photo', 'document', 'chart', 'auto'."
                        ),
                        "default": "auto",
                    },
                    "license_key": {
                        "type": "string",
                        "description": "License key for 'license_validate' and 'license_revoke'.",
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address for 'license_create'.",
                    },
                    "plan": {
                        "type": "string",
                        "description": "Plan tier for 'license_create': 'standard', 'pro', 'enterprise'.",
                        "default": "standard",
                    },
                    "max_documents": {
                        "type": "number",
                        "description": "Max documents limit for 'license_create'.",
                    },
                    "max_queries_per_day": {
                        "type": "number",
                        "description": "Max daily queries for 'license_create'.",
                    },
                },
                "required": ["operation"],
            },
        }
    ]
}


async def dispatch_mcp_call(args: dict[str, Any], ctx: dict[str, Any]) -> Any:
    """Dispatch an MCP tool call to the appropriate operation.

    Args:
        args: Tool arguments including 'operation' and operation-specific params.
        ctx: Context dict with protocol implementations:
            - vector_store, keyword_store, ai_provider, image_processor, license_store
            - hybrid_search, ingestion_engine

    Returns:
        Response object or dict with operation results.
    """
    operation = args.get("operation")
    if not operation:
        return json_response({"error": "Missing 'operation' parameter"}, status=400)

    hybrid_search = ctx["hybrid_search"]
    ingestion_engine = ctx["ingestion_engine"]
    vector_store = ctx["vector_store"]
    keyword_store = ctx["keyword_store"]
    ai_provider = ctx["ai_provider"]
    license_store = ctx["license_store"]

    if operation == "search":
        query = args.get("query")
        if not query:
            return {"error": "query required for search operation"}
        top_k = min(max(int(args.get("top_k", 5)), 1), 20)
        rerank = args.get("rerank", True)
        result = await hybrid_search.search(
            query, vector_store, keyword_store, ai_provider, top_k, rerank,
        )
        return {
            "result": {
                "results": [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.rrf_score,
                        "category": r.category,
                    }
                    for r in result["results"]
                ],
                "performance": result["performance"],
            }
        }

    elif operation == "ingest":
        doc_id = args.get("id")
        content = args.get("content")
        if not doc_id or not content:
            return {"error": "id and content required for ingest operation"}
        from src.models import Document
        doc = Document(
            id=doc_id,
            content=content,
            category=args.get("category"),
            title=args.get("title"),
        )
        result = await ingestion_engine.ingest(doc, vector_store, keyword_store, ai_provider)
        return {"result": {"success": True, "chunks": result["chunks"], "performance": result["performance"]}}

    elif operation == "ingest_image":
        return {"error": "ingest_image via MCP requires image upload through /ingest-image HTTP endpoint"}

    elif operation == "stats":
        index_stats = await vector_store.describe()
        doc_stats = await keyword_store.get_doc_stats()
        return {
            "result": {
                "vectors": index_stats.vectors_count,
                "documents": doc_stats.total_documents if doc_stats else 0,
                "dimensions": index_stats.dimensions,
            }
        }

    elif operation == "delete":
        doc_id = args.get("id")
        if not doc_id:
            return {"error": "id required for delete operation"}
        await ingestion_engine.delete(doc_id, vector_store, keyword_store)
        return {"result": {"success": True, "deleted": doc_id}}

    elif operation == "license_validate":
        license_key = args.get("license_key")
        if not license_key:
            return {"error": "license_key required for license_validate operation"}
        license_obj = await license_store.validate(license_key)
        if not license_obj:
            return {"result": {"valid": False, "error": "Invalid or inactive license"}}
        return {
            "result": {
                "valid": True,
                "plan": license_obj.plan,
                "limits": {
                    "maxDocuments": license_obj.max_documents,
                    "maxQueriesPerDay": license_obj.max_queries_per_day,
                },
            }
        }

    elif operation == "license_create":
        email = args.get("email")
        if not email:
            return {"error": "email required for license_create operation"}
        license_obj = await license_store.create(
            email=email,
            plan=args.get("plan", "standard"),
            max_documents=args.get("max_documents"),
            max_queries_per_day=args.get("max_queries_per_day"),
        )
        return {
            "result": {
                "success": True,
                "license_key": license_obj.license_key,
                "email": license_obj.email,
                "plan": license_obj.plan,
                "limits": {
                    "maxDocuments": license_obj.max_documents,
                    "maxQueriesPerDay": license_obj.max_queries_per_day,
                },
            }
        }

    elif operation == "license_list":
        licenses = await license_store.list_all()
        return {"result": {"licenses": [lic.model_dump() for lic in licenses]}}

    elif operation == "license_revoke":
        license_key = args.get("license_key")
        if not license_key:
            return {"error": "license_key required for license_revoke operation"}
        await license_store.revoke(license_key)
        return {"result": {"success": True, "revoked": license_key}}

    else:
        return {"error": f"Unknown operation: {operation}"}
