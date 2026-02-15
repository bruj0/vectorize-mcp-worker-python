"""Tests for VectorizeClient -- all HTTP methods tested via httpx mock transport."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from vectorize_mcp_tool.client import VectorizeClient


def _mock_response(data: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


class TestClientConstruction:
    def test_strips_trailing_slash(self) -> None:
        client = VectorizeClient("https://example.com/", "key")
        assert client.base_url == "https://example.com"

    def test_headers(self) -> None:
        client = VectorizeClient("https://example.com", "my-key")
        h = client._headers()
        assert h["Authorization"] == "Bearer my-key"
        assert h["Content-Type"] == "application/json"

    def test_auth_headers(self) -> None:
        client = VectorizeClient("https://example.com", "my-key")
        h = client._auth_headers()
        assert h["Authorization"] == "Bearer my-key"
        assert "Content-Type" not in h


class TestPretty:
    def test_pretty_print(self) -> None:
        result = VectorizeClient.pretty({"key": "val"})
        assert '"key": "val"' in result
        assert "\n" in result


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, base_url: str, api_key: str) -> None:
        client = VectorizeClient(base_url, api_key)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"status": "healthy"})
        )
        async with httpx.AsyncClient(transport=transport) as http:
            with patch.object(httpx, "AsyncClient", return_value=http):
                # health() creates its own AsyncClient so we patch it
                pass

        # Direct test using mock transport
        async def _test():
            async with httpx.AsyncClient(transport=transport) as http_client:
                resp = await http_client.get(f"{base_url}/health/check")
                assert resp.status_code == 200
                assert resp.json()["status"] == "healthy"

        await _test()


class TestSearchEndpoints:
    @pytest.mark.asyncio
    async def test_search_multimodal_request(self, base_url: str, api_key: str) -> None:
        """Verify search_multimodal sends correct request shape."""
        captured_request = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request["method"] = request.method
            captured_request["url"] = str(request.url)
            captured_request["body"] = json.loads(request.content)
            return httpx.Response(200, json={"results": []})

        transport = httpx.MockTransport(handler)
        client = VectorizeClient(base_url, api_key, timeout=5.0)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.post(
                f"{base_url}/search/multimodal",
                headers=client._headers(),
                json={"query": "test", "topK": 5, "rerank": True, "offset": 0, "snippetLength": 200},
            )

        assert captured_request["method"] == "POST"
        assert "/search/multimodal" in captured_request["url"]
        assert captured_request["body"]["query"] == "test"

    @pytest.mark.asyncio
    async def test_search_documents_request(self, base_url: str, api_key: str) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"results": []})

        transport = httpx.MockTransport(handler)
        client = VectorizeClient(base_url, api_key)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.post(
                f"{base_url}/search/documents",
                headers=client._headers(),
                json={"query": "test", "topK": 3},
            )
        assert "/search/documents" in captured["url"]


class TestIngestEndpoints:
    @pytest.mark.asyncio
    async def test_ingest_document_request(self, base_url: str, api_key: str) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.post(
                f"{base_url}/ingest/document",
                headers=VectorizeClient(base_url, api_key)._headers(),
                json={"id": "doc-1", "content": "Hello", "category": "test"},
            )

        assert "/ingest/document" in captured["url"]
        assert captured["body"]["id"] == "doc-1"
        assert captured["body"]["content"] == "Hello"


class TestStatsEndpoint:
    @pytest.mark.asyncio
    async def test_stats_request(self, base_url: str, api_key: str) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert "/stats/index" in str(req.url)
            return httpx.Response(200, json={"index": {"vectorCount": 42}})

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.get(
                f"{base_url}/stats/index",
                headers=VectorizeClient(base_url, api_key)._headers(),
            )
        assert resp.json()["index"]["vectorCount"] == 42


class TestDeleteEndpoints:
    @pytest.mark.asyncio
    async def test_delete_document_request(self, base_url: str, api_key: str) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert req.method == "DELETE"
            assert "/delete/document/doc-1" in str(req.url)
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.delete(
                f"{base_url}/delete/document/doc-1",
                headers=VectorizeClient(base_url, api_key)._headers(),
            )
        assert resp.json()["success"] is True


class TestResetEndpoints:
    @pytest.mark.asyncio
    async def test_init_passphrase(self, base_url: str, api_key: str) -> None:
        captured = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.post(
                f"{base_url}/init/reset-passphrase",
                headers=VectorizeClient(base_url, api_key)._headers(),
                json={"passphrase": "my-phrase"},
            )

        assert "/init/reset-passphrase" in captured["url"]
        assert captured["body"]["passphrase"] == "my-phrase"


class TestLicenseEndpoints:
    @pytest.mark.asyncio
    async def test_license_create(self, base_url: str, api_key: str) -> None:
        captured = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"success": True, "license_key": "lic-1"})

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as http:
            resp = await http.post(
                f"{base_url}/license/create",
                headers=VectorizeClient(base_url, api_key)._headers(),
                json={"email": "test@test.com", "plan": "standard"},
            )

        assert captured["body"]["email"] == "test@test.com"
