"""Async HTTP client for the Vectorize MCP Worker REST API.

Shared by both the CLI and the MCP server. All methods return parsed dicts
and raise ``httpx.HTTPStatusError`` on non-2xx responses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


class VectorizeClient:
    """Async wrapper around the deployed Vectorize worker's REST endpoints."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _auth_headers(self) -> dict[str, str]:
        """Auth header only (no Content-Type) -- for multipart requests."""
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
    ) -> dict[str, Any]:
        """Send a request and return the parsed JSON response."""
        url = f"{self.base_url}{path}"
        headers = self._auth_headers() if files else self._headers()

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.request(
                method,
                url,
                headers=headers,
                json=json_body,
                data=data,
                files=files,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Public endpoints ──────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """GET /health/check -- health check (no auth required)."""
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.get(f"{self.base_url}/health/check")
            resp.raise_for_status()
            return resp.json()

    # ── Search & retrieval ────────────────────────────────────────────────

    async def search_multimodal(
        self,
        query: str,
        *,
        top_k: int = 5,
        rerank: bool = True,
        offset: int = 0,
        snippet_length: int = 200,
    ) -> dict[str, Any]:
        """POST /search/multimodal -- hybrid search returning docs + images (snippet + metadata)."""
        return await self._request(
            "POST",
            "/search/multimodal",
            json_body={
                "query": query, "topK": top_k, "rerank": rerank,
                "offset": offset, "snippetLength": snippet_length,
            },
        )

    async def search_documents(
        self,
        query: str,
        *,
        top_k: int = 5,
        rerank: bool = True,
        offset: int = 0,
        snippet_length: int = 200,
    ) -> dict[str, Any]:
        """POST /search/documents -- hybrid search returning documents only (snippet + metadata)."""
        return await self._request(
            "POST",
            "/search/documents",
            json_body={
                "query": query, "topK": top_k, "rerank": rerank,
                "offset": offset, "snippetLength": snippet_length,
            },
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        rerank: bool = True,
        offset: int = 0,
        snippet_length: int = 200,
    ) -> dict[str, Any]:
        """Alias for search_multimodal (backward compatibility)."""
        return await self.search_multimodal(
            query, top_k=top_k, rerank=rerank, offset=offset,
            snippet_length=snippet_length,
        )

    async def find_similar_images(
        self,
        image_path: str | Path,
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """POST /search/similar-images -- visual similarity search."""
        image_path = Path(image_path)
        with image_path.open("rb") as f:
            files = {"image": (image_path.name, f, "application/octet-stream")}
            data = {"topK": str(top_k)}
            return await self._request("POST", "/search/similar-images", data=data, files=files)

    # ── Ingestion ─────────────────────────────────────────────────────────

    async def ingest(
        self,
        doc_id: str,
        content: str,
        *,
        category: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """POST /ingest/document -- ingest a text document with auto-chunking."""
        body: dict[str, Any] = {"id": doc_id, "content": content}
        if category is not None:
            body["category"] = category
        if title is not None:
            body["title"] = title
        return await self._request("POST", "/ingest/document", json_body=body)

    async def ingest_image(
        self,
        doc_id: str,
        image_path: str | Path,
        *,
        category: str = "images",
        title: str | None = None,
        image_type: str = "auto",
    ) -> dict[str, Any]:
        """POST /ingest/image -- ingest an image via multipart upload."""
        image_path = Path(image_path)
        with image_path.open("rb") as f:
            files = {"image": (image_path.name, f, "application/octet-stream")}
            data: dict[str, str] = {
                "id": doc_id,
                "category": category,
                "imageType": image_type,
            }
            if title is not None:
                data["title"] = title
            return await self._request("POST", "/ingest/image", data=data, files=files)

    # ── Statistics ────────────────────────────────────────────────────────

    async def stats(self) -> dict[str, Any]:
        """GET /stats/index -- index statistics."""
        return await self._request("GET", "/stats/index")

    # ── Retrieval ─────────────────────────────────────────────────────────

    async def get_document(self, doc_id: str) -> dict[str, Any]:
        """GET /get/document/:id -- get full document by ID."""
        return await self._request("GET", f"/get/document/{doc_id}")

    async def get_image(self, img_id: str) -> dict[str, Any]:
        """GET /get/image/:id -- get full image document by ID."""
        return await self._request("GET", f"/get/image/{img_id}")

    async def list_documents(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /list/documents -- list documents with pagination."""
        return await self._request("GET", f"/list/documents?limit={limit}&offset={offset}")

    # ── Deletion ──────────────────────────────────────────────────────────

    async def delete(self, doc_id: str) -> dict[str, Any]:
        """DELETE /delete/document/:id -- delete a document by ID."""
        return await self._request("DELETE", f"/delete/document/{doc_id}")

    async def delete_license(self, license_key: str) -> dict[str, Any]:
        """DELETE /delete/license/:key -- delete a license by key."""
        return await self._request("DELETE", f"/delete/license/{license_key}")

    # ── Reset (passphrase-gated) ──────────────────────────────────────────

    async def init_reset_passphrase(self, passphrase: str) -> dict[str, Any]:
        """POST /init/reset-passphrase -- set or rotate the reset passphrase."""
        return await self._request(
            "POST", "/init/reset-passphrase", json_body={"passphrase": passphrase}
        )

    async def reset_all(self, passphrase: str) -> dict[str, Any]:
        """POST /reset/all -- wipe all databases (requires passphrase)."""
        return await self._request(
            "POST", "/reset/all", json_body={"passphrase": passphrase}
        )

    async def reset_documents(self, passphrase: str) -> dict[str, Any]:
        """POST /reset/documents -- wipe documents + vectors (requires passphrase)."""
        return await self._request(
            "POST", "/reset/documents", json_body={"passphrase": passphrase}
        )

    async def reset_licenses(self, passphrase: str) -> dict[str, Any]:
        """POST /reset/licenses -- wipe licenses (requires passphrase)."""
        return await self._request(
            "POST", "/reset/licenses", json_body={"passphrase": passphrase}
        )

    # ── License management ────────────────────────────────────────────────

    async def license_create(
        self,
        email: str,
        *,
        plan: str = "standard",
        max_documents: int | None = None,
        max_queries_per_day: int | None = None,
    ) -> dict[str, Any]:
        """POST /license/create -- create a new license."""
        body: dict[str, Any] = {"email": email, "plan": plan}
        if max_documents is not None:
            body["max_documents"] = max_documents
        if max_queries_per_day is not None:
            body["max_queries_per_day"] = max_queries_per_day
        return await self._request("POST", "/license/create", json_body=body)

    async def license_validate(self, license_key: str) -> dict[str, Any]:
        """POST /license/validate -- validate a license key."""
        return await self._request(
            "POST", "/license/validate", json_body={"license_key": license_key}
        )

    async def license_list(self) -> dict[str, Any]:
        """GET /license/list -- list all licenses."""
        return await self._request("GET", "/license/list")

    async def license_revoke(self, license_key: str) -> dict[str, Any]:
        """POST /license/revoke -- revoke a license."""
        return await self._request(
            "POST", "/license/revoke", json_body={"license_key": license_key}
        )

    # ── Convenience ───────────────────────────────────────────────────────

    @staticmethod
    def pretty(data: dict[str, Any]) -> str:
        """Return pretty-printed JSON string."""
        return json.dumps(data, indent=2)
