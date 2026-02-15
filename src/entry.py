"""Cloudflare Worker entry point -- mirrors the TS export default { async fetch }.

This is the main routing handler. It creates binding wrappers on each request,
delegates to business logic engines, and returns JSON responses. Structurally
identical to the TS original, using the Python Workers runtime (Pyodide).
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint

from src.auth import authenticate, cors_headers, json_response
from src.bindings.ai import CloudflareAIProvider
from src.bindings.d1 import CloudflareD1KeywordStore, CloudflareD1LicenseStore
from src.bindings.multimodal import CloudflareMultimodalProcessor
from src.bindings.vectorize import CloudflareVectorStore
from src.dashboard import get_dashboard_html
from src.hybrid_search import HybridSearchEngine
from src.ingestion import IngestionEngine
from src.llms_txt import get_llms_txt
from src.mcp import TOOL_SCHEMA, dispatch_mcp_call
from src.models import Document, ImageDocument


# Singletons for stateful engines (same pattern as TS module-level instances)
_hybrid_search = HybridSearchEngine()
_ingestion = IngestionEngine()


class Default(WorkerEntrypoint):
    """Main Worker entry point. Handles all HTTP routing."""

    async def fetch(self, request) -> Response:
        url = urlparse(str(request.url))
        pathname = url.path
        method = str(request.method)

        # CORS preflight
        if method == "OPTIONS":
            return Response("", headers=cors_headers())

        # Authenticate
        auth_error = authenticate(request, self.env)
        if auth_error:
            return auth_error

        # Initialize binding wrappers
        vector_store = CloudflareVectorStore(self.env.VECTORIZE)
        keyword_store = CloudflareD1KeywordStore(self.env.DB)
        ai_provider = CloudflareAIProvider(self.env.AI)
        image_processor = CloudflareMultimodalProcessor(self.env.MULTIMODAL)
        license_store = CloudflareD1LicenseStore(self.env.DB)

        # Context dict for MCP dispatch
        ctx = {
            "vector_store": vector_store,
            "keyword_store": keyword_store,
            "ai_provider": ai_provider,
            "image_processor": image_processor,
            "license_store": license_store,
            "hybrid_search": _hybrid_search,
            "ingestion_engine": _ingestion,
        }

        try:
            # --- Root: API documentation ---
            if pathname == "/" and method == "GET":
                api_key = getattr(self.env, "API_KEY", None)
                return json_response({
                    "name": "Vectorize MCP Worker",
                    "version": "2.1.0",
                    "runtime": "Python Workers (Pyodide)",
                    "description": "Production-Grade Hybrid RAG with Multimodal Support",
                    "features": [
                        "Hybrid Search (Vector + BM25)",
                        "Multimodal Image Processing (Llama 4 Scout)",
                        "Visual Search",
                        "Reciprocal Rank Fusion (RRF)",
                        "Cross-Encoder Reranking",
                        "Recursive Chunking with 15% overlap",
                        "One-time License System",
                    ],
                    "endpoints": {
                        "GET /": "API documentation",
                        "GET /dashboard": "Interactive playground UI",
                        "GET /llms.txt": "AI search engine info",
                        "GET /test": "Health check",
                        "GET /stats": "Index statistics",
                        "POST /search": "Hybrid search (query, topK, rerank)",
                        "POST /ingest": "Ingest document with auto-chunking",
                        "POST /ingest-image": "Ingest image with AI-generated description",
                        "DELETE /documents/:id": "Delete document",
                        "POST /license/validate": "Validate a license key",
                        "POST /license/create": "Create license (admin)",
                        "GET /license/list": "List all licenses (admin)",
                        "POST /license/revoke": "Revoke a license (admin)",
                        "GET /mcp/tools": "List MCP tools",
                        "POST /mcp/call": "Execute MCP tool",
                    },
                    "models": {
                        "embedding": "@cf/baai/bge-small-en-v1.5",
                        "reranker": "@cf/baai/bge-reranker-base",
                        "vision": "@cf/meta/llama-4-scout-17b-16e-instruct",
                    },
                    "authentication": "required" if api_key else "disabled (dev mode)",
                    "docs": "https://github.com/dannwaneri/vectorize-mcp-worker",
                })

            # --- Dashboard ---
            if pathname == "/dashboard" and method == "GET":
                return Response(get_dashboard_html(), headers={"Content-Type": "text/html"})

            # --- llms.txt ---
            if pathname == "/llms.txt" and method == "GET":
                return Response(get_llms_txt(), headers={"Content-Type": "text/plain"})

            # --- Health check ---
            if pathname == "/test" and method == "GET":
                db_ok = False
                try:
                    await self.env.DB.prepare("SELECT 1").first()
                    db_ok = True
                except Exception:
                    pass
                api_key = getattr(self.env, "API_KEY", None)
                return json_response({
                    "status": "healthy",
                    "bindings": {
                        "hasAI": bool(self.env.AI),
                        "hasVectorize": bool(self.env.VECTORIZE),
                        "hasD1": bool(self.env.DB) and db_ok,
                        "hasAPIKey": bool(api_key),
                    },
                    "mode": "production" if api_key else "development",
                })

            # --- Stats ---
            if pathname == "/stats" and method == "GET":
                try:
                    index_stats = await vector_store.describe()
                    doc_stats = await keyword_store.get_doc_stats()
                    return json_response({
                        "index": {
                            "vectorCount": index_stats.vectors_count,
                            "dimensions": index_stats.dimensions,
                        },
                        "documents": {
                            "total_documents": doc_stats.total_documents if doc_stats else 0,
                            "avg_doc_length": doc_stats.avg_doc_length if doc_stats else 0,
                        },
                        "model": "@cf/baai/bge-small-en-v1.5",
                        "dimensions": 384,
                    })
                except Exception as e:
                    return json_response(
                        {"error": "Failed to get stats", "message": str(e)}, status=500
                    )

            # --- Hybrid Search ---
            if pathname == "/search" and method == "POST":
                try:
                    body_text = await request.text()
                    body = json.loads(body_text)
                    query = body.get("query")
                    if not query:
                        return json_response(
                            {"error": "Missing 'query' field in request body"}, status=400
                        )
                    top_k = body.get("topK", 5)
                    if top_k < 1 or top_k > 20:
                        return json_response(
                            {"error": "topK must be between 1 and 20"}, status=400
                        )
                    offset = body.get("offset", 0)
                    total_to_fetch = offset + top_k
                    result = await _hybrid_search.search(
                        query, vector_store, keyword_store, ai_provider,
                        total_to_fetch, body.get("rerank", True),
                    )
                    sliced = result["results"][offset:offset + top_k]
                    return json_response({
                        "query": query,
                        "topK": top_k,
                        "offset": offset,
                        "resultsCount": len(result["results"]),
                        "results": [
                            {
                                "id": r.id,
                                "score": r.rrf_score,
                                "content": r.content,
                                "category": r.category,
                                "isImage": r.is_image,
                                "scores": {
                                    "vector": r.vector_score,
                                    "keyword": r.keyword_score,
                                    "reranker": r.reranker_score,
                                },
                            }
                            for r in sliced
                        ],
                        "performance": result["performance"],
                    })
                except json.JSONDecodeError:
                    return json_response(
                        {"error": "Invalid JSON in request body"}, status=400
                    )

            # --- Ingest Document ---
            if pathname == "/ingest" and method == "POST":
                try:
                    body_text = await request.text()
                    body = json.loads(body_text)
                    doc_id = body.get("id")
                    content = body.get("content")
                    if not doc_id or not isinstance(doc_id, str):
                        return json_response(
                            {"error": "Missing or invalid id"}, status=400
                        )
                    if not content or not isinstance(content, str):
                        return json_response(
                            {"error": "Missing or invalid content"}, status=400
                        )
                    doc = Document(
                        id=doc_id,
                        content=content,
                        category=body.get("category"),
                        title=body.get("title"),
                    )
                    result = await _ingestion.ingest(
                        doc, vector_store, keyword_store, ai_provider
                    )
                    return json_response({
                        "success": True,
                        "documentId": doc_id,
                        "chunksCreated": result["chunks"],
                        "performance": result["performance"],
                    })
                except Exception as e:
                    return json_response(
                        {"error": "Ingest failed", "message": str(e)}, status=500
                    )

            # --- Delete Document ---
            if pathname.startswith("/documents/") and method == "DELETE":
                doc_id = pathname.replace("/documents/", "")
                if not doc_id:
                    return json_response({"error": "Document ID required"}, status=400)
                await _ingestion.delete(doc_id, vector_store, keyword_store)
                return json_response({"success": True, "deleted": doc_id})

            # --- Ingest Image ---
            if pathname == "/ingest-image" and method == "POST":
                try:
                    form_data = await request.formData()
                    img_id = str(form_data.get("id") or "")
                    image_file = form_data.get("image")
                    category = str(form_data.get("category") or "images")
                    title = str(form_data.get("title") or "") or None
                    image_type = str(form_data.get("imageType") or "auto")

                    if not img_id or not image_file:
                        return json_response(
                            {"error": "Missing id or image"}, status=400
                        )

                    image_buffer = bytes(await image_file.arrayBuffer())
                    doc = ImageDocument(
                        id=img_id,
                        content="",
                        image_buffer=image_buffer,
                        category=category,
                        title=title,
                        image_type=image_type,
                    )
                    result = await _ingestion.ingest_image(
                        doc, vector_store, keyword_store, image_processor
                    )
                    return json_response({
                        "success": True,
                        "documentId": img_id,
                        "description": result.get("description"),
                        "extractedText": result.get("extractedText"),
                        "performance": result["performance"],
                    })
                except Exception as e:
                    return json_response(
                        {"error": "Image ingest failed", "message": str(e)}, status=500
                    )

            # --- Find Similar Images ---
            if pathname == "/find-similar-images" and method == "POST":
                try:
                    form_data = await request.formData()
                    image_file = form_data.get("image")
                    top_k = int(str(form_data.get("topK") or "5"))

                    if not image_file:
                        return json_response({"error": "Missing image"}, status=400)

                    image_buffer = bytes(await image_file.arrayBuffer())
                    description_result = await image_processor.describe_image(
                        image_buffer=image_buffer, image_type="auto"
                    )
                    if not description_result.success:
                        raise RuntimeError(
                            description_result.error or "Failed to process image"
                        )

                    search_result = await _hybrid_search.search(
                        description_result.description,
                        vector_store, keyword_store, ai_provider, top_k, True,
                    )
                    image_results = [
                        r for r in search_result["results"] if r.is_image
                    ]
                    return json_response({
                        "query": description_result.description,
                        "results": [
                            {
                                "id": r.id,
                                "content": r.content,
                                "score": r.rrf_score,
                                "category": r.category,
                            }
                            for r in image_results
                        ],
                        "performance": search_result["performance"],
                    })
                except Exception as e:
                    return json_response({"error": str(e)}, status=500)

            # --- License: Validate ---
            if pathname == "/license/validate" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    key = body.get("license_key")
                    if not key:
                        return json_response(
                            {"valid": False, "error": "Missing license_key"}, status=400
                        )
                    lic = await license_store.validate(key)
                    if not lic:
                        return json_response(
                            {"valid": False, "error": "Invalid or inactive license"},
                            status=403,
                        )
                    return json_response({
                        "valid": True,
                        "plan": lic.plan,
                        "limits": {
                            "maxDocuments": lic.max_documents,
                            "maxQueriesPerDay": lic.max_queries_per_day,
                        },
                        "createdAt": lic.created_at,
                    })
                except Exception:
                    return json_response(
                        {"valid": False, "error": "Validation failed"}, status=500
                    )

            # --- License: Create ---
            if pathname == "/license/create" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    email = body.get("email")
                    if not email:
                        return json_response({"error": "Email required"}, status=400)
                    lic = await license_store.create(
                        email=email,
                        plan=body.get("plan", "standard"),
                        max_documents=body.get("max_documents"),
                        max_queries_per_day=body.get("max_queries_per_day"),
                    )
                    return json_response({
                        "success": True,
                        "license_key": lic.license_key,
                        "email": lic.email,
                        "plan": lic.plan,
                        "limits": {
                            "maxDocuments": lic.max_documents,
                            "maxQueriesPerDay": lic.max_queries_per_day,
                        },
                    })
                except Exception as e:
                    return json_response(
                        {"error": "Failed to create license", "message": str(e)},
                        status=500,
                    )

            # --- License: List ---
            if pathname == "/license/list" and method == "GET":
                try:
                    licenses = await license_store.list_all()
                    return json_response({
                        "licenses": [lic.model_dump() for lic in licenses]
                    })
                except Exception:
                    return json_response(
                        {"error": "Failed to list licenses"}, status=500
                    )

            # --- License: Revoke ---
            if pathname == "/license/revoke" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    key = body.get("license_key")
                    if not key:
                        return json_response(
                            {"error": "license_key required"}, status=400
                        )
                    await license_store.revoke(key)
                    return json_response({"success": True, "revoked": key})
                except Exception:
                    return json_response(
                        {"error": "Failed to revoke license"}, status=500
                    )

            # --- MCP: List Tools ---
            if pathname == "/mcp/tools" and method == "GET":
                return json_response(TOOL_SCHEMA)

            # --- MCP: Call Tool ---
            if pathname == "/mcp/call" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    tool_name = body.get("tool")
                    if not tool_name:
                        return json_response(
                            {"error": "Missing tool name"}, status=400
                        )
                    if tool_name != "vectorize":
                        return json_response(
                            {"error": f"Unknown tool: {tool_name}"}, status=400
                        )
                    args = body.get("arguments", {})
                    result = await dispatch_mcp_call(args, ctx)

                    # dispatch_mcp_call may return a Response or a dict
                    if isinstance(result, Response):
                        return result
                    return json_response(result)
                except Exception as e:
                    return json_response(
                        {"error": "Tool execution failed", "message": str(e)},
                        status=500,
                    )

            # --- 404 ---
            return json_response(
                {"error": "Not found", "hint": "Visit GET / for API documentation"},
                status=404,
            )

        except Exception as e:
            return json_response(
                {"error": "Internal server error", "message": str(e)}, status=500
            )
