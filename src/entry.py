"""Cloudflare Worker entry point -- mirrors the TS export default { async fetch }.

This is the main routing handler. It creates binding wrappers on each request,
delegates to business logic engines, and returns JSON responses. Structurally
identical to the TS original, using the Python Workers runtime (Pyodide).
"""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint

from auth import authenticate, cors_headers, json_response
from bindings.ai import CloudflareAIProvider
from bindings.d1 import CloudflareD1KeywordStore, CloudflareD1LicenseStore, CloudflareD1SettingsStore
from bindings.multimodal import CloudflareMultimodalProcessor
from bindings.vectorize import CloudflareVectorStore
from dashboard import get_dashboard_html
from hybrid_search import HybridSearchEngine
from ingestion import IngestionEngine
from llms_txt import get_llms_txt
from logger import RequestLogger
from models import Document, ImageDocument
from multipart import parse_multipart


# Singletons for stateful engines (same pattern as TS module-level instances)
_hybrid_search = HybridSearchEngine()
_ingestion = IngestionEngine()


def _snippet(content: str, max_len: int = 200) -> str:
    """Truncate content to a snippet for search results."""
    if len(content) <= max_len:
        return content
    return content[:max_len] + "..."


class Default(WorkerEntrypoint):
    """Main Worker entry point. Handles all HTTP routing."""

    async def fetch(self, request) -> Response:
        url = urlparse(str(request.url))
        pathname = url.path
        method = str(request.method)

        # ── Logger setup ──────────────────────────────────────────────
        debug_flag = str(getattr(self.env, "DEBUG_LOGGING", "") or "").lower()
        debug_enabled = debug_flag in ("true", "1", "yes")
        log = RequestLogger(debug=debug_enabled)

        log.info("request.start", method=method, path=pathname)

        # CORS preflight
        if method == "OPTIONS":
            log.debug_log("CORS preflight")
            return Response("", headers=cors_headers())

        # Authenticate
        auth_error = authenticate(request, self.env)
        if auth_error:
            log.warn("auth.rejected", path=pathname)
            return auth_error

        log.debug_log("auth.ok")

        # ── Initialize binding wrappers (per-request) ─────────────────
        vector_store = CloudflareVectorStore(self.env.VECTORIZE, logger=log)
        keyword_store = CloudflareD1KeywordStore(self.env.DB, logger=log)
        ai_provider = CloudflareAIProvider(self.env.AI, logger=log)
        multimodal_binding = getattr(self.env, "MULTIMODAL", None)
        internal_secret = str(getattr(self.env, "INTERNAL_SECRET", "") or "")
        image_processor = (
            CloudflareMultimodalProcessor(multimodal_binding, internal_secret or None, logger=log)
            if multimodal_binding
            else None
        )
        license_store = CloudflareD1LicenseStore(self.env.DB, logger=log)
        settings_store = CloudflareD1SettingsStore(self.env.DB, logger=log)

        # Context dict for MCP dispatch
        ctx = {
            "vector_store": vector_store,
            "keyword_store": keyword_store,
            "ai_provider": ai_provider,
            "image_processor": image_processor,
            "license_store": license_store,
            "hybrid_search": _hybrid_search,
            "ingestion_engine": _ingestion,
            "settings_store": settings_store,
            "logger": log,
        }

        try:
            # ── Root: API documentation ───────────────────────────────
            if pathname == "/" and method == "GET":
                api_key = getattr(self.env, "API_KEY", None)
                log.debug_log("route.root")
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
                        "GET /health/check": "Health check",
                        "GET /stats/index": "Index statistics",
                        "POST /search/multimodal": "Hybrid search -- docs + images (snippet + metadata)",
                        "POST /search/documents": "Hybrid search -- documents only (snippet + metadata)",
                        "POST /search/similar-images": "Visual similarity search (image input)",
                        "POST /ingest/document": "Ingest document with auto-chunking",
                        "POST /ingest/image": "Ingest image with AI-generated description",
                        "DELETE /delete/document/:id": "Delete document by ID",
                        "GET /get/document/:id": "Get full document by ID",
                        "GET /get/image/:id": "Get full image document by ID",
                        "GET /list/documents": "List documents with pagination",
                        "POST /init/reset-passphrase": "Set/rotate reset passphrase",
                        "POST /reset/all": "Wipe all databases (requires passphrase)",
                        "POST /reset/documents": "Wipe documents + vectors (requires passphrase)",
                        "POST /reset/licenses": "Wipe licenses (requires passphrase)",
                        "POST /license/validate": "Validate a license key",
                        "POST /license/create": "Create license (admin)",
                        "GET /license/list": "List all licenses (admin)",
                        "POST /license/revoke": "Revoke a license (admin)",
                        "DELETE /delete/license/:key": "Delete a license by key",
                    },
                    "models": {
                        "embedding": "@cf/baai/bge-small-en-v1.5",
                        "reranker": "@cf/baai/bge-reranker-base",
                        "vision": "@cf/meta/llama-4-scout-17b-16e-instruct",
                    },
                    "authentication": "required" if api_key else "disabled (dev mode)",
                    "docs": "https://github.com/bruj0/vectorize-mcp-worker-python",
                })

            # ── Dashboard ─────────────────────────────────────────────
            if pathname == "/dashboard" and method == "GET":
                log.debug_log("route.dashboard")
                return Response(get_dashboard_html(), headers={"Content-Type": "text/html"})

            # ── llms.txt ──────────────────────────────────────────────
            if pathname == "/llms.txt" and method == "GET":
                log.debug_log("route.llms_txt")
                return Response(get_llms_txt(), headers={"Content-Type": "text/plain"})

            # ── Health check ──────────────────────────────────────────
            if pathname == "/health/check" and method == "GET":
                log.info("health.check")
                db_ok = False
                try:
                    await self.env.DB.prepare("SELECT 1").first()
                    db_ok = True
                except Exception as exc:
                    log.warn("health.d1_fail", exc=exc)
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

            # ── Stats ─────────────────────────────────────────────────
            if pathname == "/stats/index" and method == "GET":
                log.info("stats.start")
                try:
                    index_stats = await vector_store.describe()
                    doc_stats = await keyword_store.get_doc_stats()
                    log.info(
                        "stats.ok",
                        vectorCount=index_stats.vectors_count,
                        totalDocs=doc_stats.total_documents if doc_stats else 0,
                    )
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
                    log.error("stats.failed", exc=e)
                    return json_response(
                        {"error": "Failed to get stats"}, status=500
                    )

            # ── Search: Multimodal (docs + images) ────────────────────
            if pathname in ("/search/multimodal", "/search/documents") and method == "POST":
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
                    offset = max(int(body.get("offset", 0)), 0)
                    total_to_fetch = offset + top_k
                    log.info("search.start", query=query, topK=top_k, offset=offset, rerank=body.get("rerank", True))
                    result = await _hybrid_search.search(
                        query, vector_store, keyword_store, ai_provider,
                        total_to_fetch, body.get("rerank", True), logger=log,
                    )
                    all_results = result["results"]
                    # /search/documents filters out images
                    if pathname == "/search/documents":
                        all_results = [r for r in all_results if not r.is_image]
                    sliced = all_results[offset:offset + top_k]
                    log.info("search.ok", resultsCount=len(sliced))

                    # Enrich with metadata from D1
                    result_ids = [r.id for r in sliced]
                    metadata_map = await keyword_store.get_documents_metadata(result_ids) if result_ids else {}
                    snippet_len = min(max(int(body.get("snippetLength", 200)), 50), 500)

                    return json_response({
                        "query": query,
                        "topK": top_k,
                        "offset": offset,
                        "resultsCount": len(all_results),
                        "results": [
                            {
                                "id": r.id,
                                "score": r.rrf_score,
                                "snippet": _snippet(r.content, snippet_len),
                                "category": r.category,
                                "isImage": r.is_image,
                                "title": metadata_map.get(r.id, {}).get("title"),
                                "source": metadata_map.get(r.id, {}).get("source"),
                                "wordCount": metadata_map.get(r.id, {}).get("word_count"),
                                "chunkIndex": metadata_map.get(r.id, {}).get("chunk_index"),
                                "parentId": metadata_map.get(r.id, {}).get("parent_id"),
                                "createdAt": metadata_map.get(r.id, {}).get("created_at"),
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
                    log.warn("search.invalid_json")
                    return json_response(
                        {"error": "Invalid JSON in request body"}, status=400
                    )

            # ── Ingest Document ───────────────────────────────────────
            if pathname == "/ingest/document" and method == "POST":
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
                    log.info("ingest.start", docId=doc_id, contentLength=len(content))
                    doc = Document(
                        id=doc_id,
                        content=content,
                        category=body.get("category"),
                        title=body.get("title"),
                    )
                    result = await _ingestion.ingest(
                        doc, vector_store, keyword_store, ai_provider, logger=log,
                    )
                    log.info("ingest.ok", docId=doc_id, chunks=result["chunks"])
                    return json_response({
                        "success": True,
                        "documentId": doc_id,
                        "chunksCreated": result["chunks"],
                        "performance": result["performance"],
                    })
                except Exception as e:
                    log.error("ingest.failed", exc=e)
                    return json_response(
                        {"error": "Ingest failed"}, status=500
                    )

            # ── Delete Document ───────────────────────────────────────
            if pathname.startswith("/delete/document/") and method == "DELETE":
                doc_id = pathname.replace("/delete/document/", "")
                if not doc_id:
                    return json_response({"error": "Document ID required"}, status=400)
                log.info("delete.start", docId=doc_id)
                await _ingestion.delete(doc_id, vector_store, keyword_store, logger=log)
                log.info("delete.ok", docId=doc_id)
                return json_response({"success": True, "deleted": doc_id})

            # ── Ingest Image ──────────────────────────────────────────
            if pathname == "/ingest/image" and method == "POST":
                if not image_processor:
                    log.warn("ingest_image.no_processor")
                    return json_response(
                        {"error": "Image processing unavailable. Deploy multimodal-pro-worker and configure the MULTIMODAL service binding."},
                        status=501,
                    )
                try:
                    log.info("ingest_image.parsing_form")
                    form = await parse_multipart(request, log)

                    img_id = form.get_text("id")
                    image_field = form.get("image")
                    category = form.get_text("category", "images")
                    title = form.get_text("title") or None
                    image_type = form.get_text("imageType", "auto")

                    if not img_id or not image_field:
                        log.warn("ingest_image.missing_fields", hasId=bool(img_id), hasImage=bool(image_field))
                        return json_response(
                            {"error": "Missing id or image"}, status=400
                        )

                    image_buffer = image_field.value
                    log.info(
                        "ingest_image.start",
                        imgId=img_id,
                        imageSize=len(image_buffer),
                        imageType=image_type,
                        category=category,
                    )
                    doc = ImageDocument(
                        id=img_id,
                        content="",
                        image_buffer=image_buffer,
                        category=category,
                        title=title,
                        image_type=image_type,
                    )
                    result = await _ingestion.ingest_image(
                        doc, vector_store, keyword_store, image_processor, logger=log,
                    )
                    log.info(
                        "ingest_image.ok",
                        imgId=img_id,
                        hasDescription=bool(result.get("description")),
                        hasExtractedText=bool(result.get("extractedText")),
                    )
                    return json_response({
                        "success": True,
                        "documentId": img_id,
                        "description": result.get("description"),
                        "extractedText": result.get("extractedText"),
                        "performance": result["performance"],
                    })
                except Exception as e:
                    log.error("ingest_image.failed", exc=e)
                    return json_response(
                        {"error": "Image ingest failed"}, status=500
                    )

            # ── Search: Similar Images (image input) ──────────────────
            if pathname == "/search/similar-images" and method == "POST":
                if not image_processor:
                    log.warn("find_similar.no_processor")
                    return json_response(
                        {"error": "Image processing unavailable. Deploy multimodal-pro-worker and configure the MULTIMODAL service binding."},
                        status=501,
                    )
                try:
                    log.info("find_similar.parsing_form")
                    form = await parse_multipart(request, log)

                    image_field = form.get("image")
                    top_k = min(max(int(form.get_text("topK", "5")), 1), 20)

                    if not image_field:
                        log.warn("find_similar.missing_image")
                        return json_response({"error": "Missing image"}, status=400)

                    image_buffer = image_field.value
                    log.info("find_similar.start", imageSize=len(image_buffer), topK=top_k)

                    description_result = await image_processor.describe_image(
                        image_buffer=image_buffer, image_type="auto"
                    )
                    if not description_result.success:
                        raise RuntimeError(
                            description_result.error or "Failed to process image"
                        )

                    log.debug_log("find_similar.description_ok", descriptionLength=len(description_result.description))

                    search_result = await _hybrid_search.search(
                        description_result.description,
                        vector_store, keyword_store, ai_provider, top_k, True, logger=log,
                    )
                    image_results = [
                        r for r in search_result["results"] if r.is_image
                    ]
                    log.info("find_similar.ok", totalResults=len(image_results))

                    # Enrich with metadata from D1
                    img_ids = [r.id for r in image_results]
                    meta_map = await keyword_store.get_documents_metadata(img_ids) if img_ids else {}

                    return json_response({
                        "query": description_result.description,
                        "results": [
                            {
                                "id": r.id,
                                "score": r.rrf_score,
                                "snippet": _snippet(r.content, 200),
                                "category": r.category,
                                "isImage": True,
                                "title": meta_map.get(r.id, {}).get("title"),
                                "source": meta_map.get(r.id, {}).get("source"),
                                "wordCount": meta_map.get(r.id, {}).get("word_count"),
                                "parentId": meta_map.get(r.id, {}).get("parent_id"),
                                "createdAt": meta_map.get(r.id, {}).get("created_at"),
                            }
                            for r in image_results
                        ],
                        "performance": search_result["performance"],
                    })
                except Exception as e:
                    log.error("find_similar.failed", exc=e)
                    return json_response({"error": "Similar image search failed"}, status=500)

            # ── License: Validate ─────────────────────────────────────
            if pathname == "/license/validate" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    key = body.get("license_key")
                    if not key:
                        return json_response(
                            {"valid": False, "error": "Missing license_key"}, status=400
                        )
                    log.info("license.validate", keyPrefix=key[:8])
                    lic = await license_store.validate(key)
                    if not lic:
                        log.info("license.invalid", keyPrefix=key[:8])
                        return json_response(
                            {"valid": False, "error": "Invalid or inactive license"},
                            status=403,
                        )
                    log.info("license.valid", plan=lic.plan)
                    return json_response({
                        "valid": True,
                        "plan": lic.plan,
                        "limits": {
                            "maxDocuments": lic.max_documents,
                            "maxQueriesPerDay": lic.max_queries_per_day,
                        },
                        "createdAt": lic.created_at,
                    })
                except Exception as exc:
                    log.error("license.validate_failed", exc=exc)
                    return json_response(
                        {"valid": False, "error": "Validation failed"}, status=500
                    )

            # ── License: Create ───────────────────────────────────────
            if pathname == "/license/create" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    email = body.get("email")
                    if not email:
                        return json_response({"error": "Email required"}, status=400)
                    log.info("license.create", email=email, plan=body.get("plan", "standard"))
                    lic = await license_store.create(
                        email=email,
                        plan=body.get("plan", "standard"),
                        max_documents=body.get("max_documents"),
                        max_queries_per_day=body.get("max_queries_per_day"),
                    )
                    log.info("license.created", keyPrefix=lic.license_key[:8])
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
                    log.error("license.create_failed", exc=e)
                    return json_response(
                        {"error": "Failed to create license"},
                        status=500,
                    )

            # ── License: List ─────────────────────────────────────────
            if pathname == "/license/list" and method == "GET":
                try:
                    log.info("license.list")
                    licenses = await license_store.list_all()
                    log.info("license.list_ok", count=len(licenses))
                    return json_response({
                        "licenses": [lic.model_dump() for lic in licenses]
                    })
                except Exception as exc:
                    log.error("license.list_failed", exc=exc)
                    return json_response(
                        {"error": "Failed to list licenses"}, status=500
                    )

            # ── License: Revoke ───────────────────────────────────────
            if pathname == "/license/revoke" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    key = body.get("license_key")
                    if not key:
                        return json_response(
                            {"error": "license_key required"}, status=400
                        )
                    log.info("license.revoke", keyPrefix=key[:8])
                    await license_store.revoke(key)
                    log.info("license.revoked", keyPrefix=key[:8])
                    return json_response({"success": True, "revoked": key})
                except Exception as exc:
                    log.error("license.revoke_failed", exc=exc)
                    return json_response(
                        {"error": "Failed to revoke license"}, status=500
                    )

            # ── Delete License ────────────────────────────────────────
            if pathname.startswith("/delete/license/") and method == "DELETE":
                license_key = pathname.replace("/delete/license/", "")
                if not license_key:
                    return json_response({"error": "License key required"}, status=400)
                try:
                    log.info("license.delete", keyPrefix=license_key[:8])
                    deleted = await license_store.delete(license_key)
                    if not deleted:
                        return json_response({"error": "License not found"}, status=404)
                    log.info("license.deleted", keyPrefix=license_key[:8])
                    return json_response({"success": True, "deleted": license_key})
                except Exception as exc:
                    log.error("license.delete_failed", exc=exc)
                    return json_response(
                        {"error": "Failed to delete license"}, status=500
                    )

            # ── Get Document ──────────────────────────────────────────
            if pathname.startswith("/get/document/") and method == "GET":
                doc_id = pathname.replace("/get/document/", "")
                if not doc_id:
                    return json_response({"error": "Document ID required"}, status=400)
                try:
                    log.info("get_document.start", docId=doc_id)
                    doc = await keyword_store.get_document(doc_id)
                    if not doc:
                        return json_response({"error": "Document not found"}, status=404)
                    if doc.get("is_image"):
                        return json_response(
                            {"error": "This is an image document. Use GET /get/image/:id instead."},
                            status=400,
                        )
                    log.info("get_document.ok", docId=doc_id)
                    return json_response(doc)
                except Exception as exc:
                    log.error("get_document.failed", exc=exc)
                    return json_response({"error": "Failed to get document"}, status=500)

            # ── Get Image ─────────────────────────────────────────────
            if pathname.startswith("/get/image/") and method == "GET":
                img_id = pathname.replace("/get/image/", "")
                if not img_id:
                    return json_response({"error": "Image ID required"}, status=400)
                try:
                    log.info("get_image.start", imgId=img_id)
                    doc = await keyword_store.get_document(img_id)
                    if not doc:
                        return json_response({"error": "Image not found"}, status=404)
                    if not doc.get("is_image"):
                        return json_response(
                            {"error": "This is a text document. Use GET /get/document/:id instead."},
                            status=400,
                        )
                    log.info("get_image.ok", imgId=img_id)
                    return json_response(doc)
                except Exception as exc:
                    log.error("get_image.failed", exc=exc)
                    return json_response({"error": "Failed to get image"}, status=500)

            # ── List Documents ────────────────────────────────────────
            if pathname == "/list/documents" and method == "GET":
                try:
                    from urllib.parse import parse_qs
                    qs = parse_qs(url.query or "")
                    limit = min(max(int(qs.get("limit", ["50"])[0]), 1), 200)
                    offset_val = max(int(qs.get("offset", ["0"])[0]), 0)
                    log.info("list_documents.start", limit=limit, offset=offset_val)
                    docs = await keyword_store.list_documents(limit=limit, offset=offset_val)
                    log.info("list_documents.ok", count=len(docs))
                    return json_response({"documents": docs, "limit": limit, "offset": offset_val})
                except Exception as exc:
                    log.error("list_documents.failed", exc=exc)
                    return json_response({"error": "Failed to list documents"}, status=500)

            # ── Init Reset Passphrase ─────────────────────────────────
            if pathname == "/init/reset-passphrase" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    passphrase = body.get("passphrase")
                    if not passphrase or not isinstance(passphrase, str) or len(passphrase) < 8:
                        return json_response(
                            {"error": "Passphrase required (minimum 8 characters)"}, status=400
                        )
                    log.info("init.reset_passphrase")
                    phrase_hash = hashlib.sha256(passphrase.encode()).hexdigest()
                    await settings_store.set("reset_passphrase_hash", phrase_hash)
                    log.info("init.reset_passphrase.ok")
                    return json_response({"success": True, "message": "Reset passphrase configured"})
                except Exception as exc:
                    log.error("init.reset_passphrase.failed", exc=exc)
                    return json_response({"error": "Failed to set reset passphrase"}, status=500)

            # ── Reset: All ────────────────────────────────────────────
            if pathname == "/reset/all" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    passphrase = body.get("passphrase")
                    if not passphrase:
                        return json_response({"error": "Passphrase required"}, status=400)
                    stored_hash = await settings_store.get("reset_passphrase_hash")
                    if not stored_hash:
                        return json_response(
                            {"error": "Reset passphrase not configured. Call POST /init/reset-passphrase first."},
                            status=403,
                        )
                    if hashlib.sha256(passphrase.encode()).hexdigest() != stored_hash:
                        return json_response({"error": "Invalid passphrase"}, status=403)

                    log.info("reset.all.start")
                    all_ids = await keyword_store.get_all_document_ids()
                    if all_ids:
                        await vector_store.delete_by_ids(all_ids)
                    doc_count = len(all_ids)
                    await keyword_store.reset()
                    lic_count = await license_store.reset()
                    log.info("reset.all.ok", documents=doc_count, licenses=lic_count)
                    return json_response({
                        "success": True,
                        "deleted": {"documents": doc_count, "licenses": lic_count},
                    })
                except Exception as exc:
                    log.error("reset.all.failed", exc=exc)
                    return json_response({"error": "Reset failed"}, status=500)

            # ── Reset: Documents ──────────────────────────────────────
            if pathname == "/reset/documents" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    passphrase = body.get("passphrase")
                    if not passphrase:
                        return json_response({"error": "Passphrase required"}, status=400)
                    stored_hash = await settings_store.get("reset_passphrase_hash")
                    if not stored_hash:
                        return json_response(
                            {"error": "Reset passphrase not configured. Call POST /init/reset-passphrase first."},
                            status=403,
                        )
                    if hashlib.sha256(passphrase.encode()).hexdigest() != stored_hash:
                        return json_response({"error": "Invalid passphrase"}, status=403)

                    log.info("reset.documents.start")
                    all_ids = await keyword_store.get_all_document_ids()
                    if all_ids:
                        await vector_store.delete_by_ids(all_ids)
                    doc_count = len(all_ids)
                    await keyword_store.reset()
                    log.info("reset.documents.ok", documents=doc_count)
                    return json_response({"success": True, "deleted": {"documents": doc_count}})
                except Exception as exc:
                    log.error("reset.documents.failed", exc=exc)
                    return json_response({"error": "Document reset failed"}, status=500)

            # ── Reset: Licenses ───────────────────────────────────────
            if pathname == "/reset/licenses" and method == "POST":
                try:
                    body = json.loads(await request.text())
                    passphrase = body.get("passphrase")
                    if not passphrase:
                        return json_response({"error": "Passphrase required"}, status=400)
                    stored_hash = await settings_store.get("reset_passphrase_hash")
                    if not stored_hash:
                        return json_response(
                            {"error": "Reset passphrase not configured. Call POST /init/reset-passphrase first."},
                            status=403,
                        )
                    if hashlib.sha256(passphrase.encode()).hexdigest() != stored_hash:
                        return json_response({"error": "Invalid passphrase"}, status=403)

                    log.info("reset.licenses.start")
                    lic_count = await license_store.reset()
                    log.info("reset.licenses.ok", licenses=lic_count)
                    return json_response({"success": True, "deleted": {"licenses": lic_count}})
                except Exception as exc:
                    log.error("reset.licenses.failed", exc=exc)
                    return json_response({"error": "License reset failed"}, status=500)

            # ── 404 ───────────────────────────────────────────────────
            log.warn("route.not_found", path=pathname, method=method)
            return json_response(
                {"error": "Not found", "hint": "Visit GET / for API documentation"},
                status=404,
            )

        except Exception as e:
            log.error("unhandled_exception", exc=e, path=pathname, method=method)
            return json_response(
                {"error": "Internal server error"}, status=500
            )
