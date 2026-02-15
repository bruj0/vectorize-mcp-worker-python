"""Tests for the FastMCP server -- verifies schema, validation, and dispatch.

Replaces the old worker-side test_mcp_dispatch.py and test_mcp_operations.py
with equivalent coverage for the refactored server.py that dispatches directly
to VectorizeClient REST methods.
"""

from __future__ import annotations

import inspect
import json
import os
from unittest.mock import AsyncMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _set_env():
    """Ensure env vars are set so _require_env doesn't sys.exit."""
    os.environ.setdefault("VECTORIZE_URL", "https://test.workers.dev")
    os.environ.setdefault("VECTORIZE_API_KEY", "test-key")


_set_env()

from vectorize_mcp_tool.metadata import OPERATION_NAMES, OPERATIONS, PARAMETERS  # noqa: E402
from vectorize_mcp_tool.server import vectorize  # noqa: E402


def _mock_client(**overrides):
    """Return an AsyncMock VectorizeClient with sensible defaults."""
    client = AsyncMock()
    client.search_multimodal = AsyncMock(return_value={"result": {"results": [], "performance": {}}})
    client.search_documents = AsyncMock(return_value={"result": {"results": [], "performance": {}}})
    client.ingest = AsyncMock(return_value={"result": {"success": True, "chunks": 1}})
    client.ingest_image = AsyncMock(return_value={"result": {"success": True}})
    client.stats = AsyncMock(return_value={"result": {"vectors": 42, "documents": 10, "dimensions": 384}})
    client.delete = AsyncMock(return_value={"result": {"success": True, "deleted": "doc-1"}})
    client.get_document = AsyncMock(return_value={"result": {"id": "doc-1", "content": "hello"}})
    client.get_image = AsyncMock(return_value={"result": {"id": "img-1", "content": "desc"}})
    client.list_documents = AsyncMock(return_value={"result": {"documents": [], "limit": 50, "offset": 0}})
    client.license_validate = AsyncMock(return_value={"result": {"valid": True, "plan": "standard"}})
    client.license_create = AsyncMock(return_value={"result": {"success": True, "license_key": "lic-new"}})
    client.license_list = AsyncMock(return_value={"result": {"licenses": []}})
    client.license_revoke = AsyncMock(return_value={"result": {"success": True, "revoked": "lic-1"}})
    client.delete_license = AsyncMock(return_value={"result": {"success": True, "deleted": "lic-1"}})
    client.reset_all = AsyncMock(return_value={"result": {"success": True}})
    client.reset_documents = AsyncMock(return_value={"result": {"success": True}})
    client.reset_licenses = AsyncMock(return_value={"result": {"success": True}})
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


async def _call(operation: str, client=None, **kwargs):
    """Call the vectorize tool function with a mocked client."""
    if client is None:
        client = _mock_client()
    with patch("vectorize_mcp_tool.server.VectorizeClient", return_value=client):
        result_str = await vectorize(operation=operation, **kwargs)
    return json.loads(result_str)


# ── 7a: Schema / metadata tests ─────────────────────────────────────────────


class TestToolSchema:
    """Equivalent of the old TestToolSchema from test_mcp_dispatch.py."""

    def test_tool_function_exists(self) -> None:
        assert callable(vectorize)

    def test_all_17_operations_in_metadata(self) -> None:
        assert len(OPERATION_NAMES) == 17

    def test_all_operations_handled_in_server(self) -> None:
        """The server source must reference every operation name."""
        import vectorize_mcp_tool.server as srv_mod
        src = inspect.getsource(srv_mod)
        missing = [op for op in OPERATION_NAMES if op not in src]
        assert not missing, f"Server missing operations: {missing}"

    def test_expected_parameters_in_signature(self) -> None:
        sig = inspect.signature(vectorize)
        expected = {
            "operation", "query", "top_k", "rerank", "snippet_length",
            "id", "content", "category", "title", "image_url", "image_type",
            "license_key", "email", "plan", "max_documents",
            "max_queries_per_day", "limit", "offset", "passphrase",
        }
        assert expected == set(sig.parameters.keys())

    def test_metadata_operations_have_descriptions(self) -> None:
        for op in OPERATIONS:
            assert "description" in op, f"Operation {op['name']} missing description"
            assert len(op["description"]) > 10

    def test_default_values(self) -> None:
        sig = inspect.signature(vectorize)
        assert sig.parameters["top_k"].default == 5
        assert sig.parameters["rerank"].default is True
        assert sig.parameters["snippet_length"].default == 200
        assert sig.parameters["image_type"].default == "auto"
        assert sig.parameters["plan"].default == "standard"
        assert sig.parameters["limit"].default == 50
        assert sig.parameters["offset"].default == 0


# ── 7b: Input validation tests ──────────────────────────────────────────────


class TestDispatchValidation:
    """Equivalent of the old TestDispatchValidation from test_mcp_dispatch.py."""

    @pytest.mark.asyncio
    async def test_search_multimodal_missing_query(self) -> None:
        result = await _call("search_multimodal")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_documents_missing_query(self) -> None:
        result = await _call("search_documents")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ingest_missing_id(self) -> None:
        result = await _call("ingest", content="hello")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ingest_missing_content(self) -> None:
        result = await _call("ingest", id="doc-1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_missing_id(self) -> None:
        result = await _call("delete")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_document_missing_id(self) -> None:
        result = await _call("get_document")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_image_missing_id(self) -> None:
        result = await _call("get_image")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_license_validate_missing_key(self) -> None:
        result = await _call("license_validate")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_license_create_missing_email(self) -> None:
        result = await _call("license_create")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_license_revoke_missing_key(self) -> None:
        result = await _call("license_revoke")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_license_missing_key(self) -> None:
        result = await _call("delete_license")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reset_all_missing_passphrase(self) -> None:
        result = await _call("reset_all")
        assert "error" in result
        assert "passphrase" in result["error"]

    @pytest.mark.asyncio
    async def test_reset_documents_missing_passphrase(self) -> None:
        result = await _call("reset_documents")
        assert "error" in result
        assert "passphrase" in result["error"]

    @pytest.mark.asyncio
    async def test_reset_licenses_missing_passphrase(self) -> None:
        result = await _call("reset_licenses")
        assert "error" in result
        assert "passphrase" in result["error"]

    @pytest.mark.asyncio
    async def test_ingest_image_missing_fields(self) -> None:
        result = await _call("ingest_image")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ingest_image_guidance(self) -> None:
        """ingest_image with id+url returns guidance about HTTP endpoint."""
        result = await _call("ingest_image", id="img-1", image_url="https://example.com/img.png")
        assert "error" in result
        assert "/ingest/image" in result["error"]


# ── 7c: Successful operation dispatch tests ──────────────────────────────────


class TestSearchOperations:
    @pytest.mark.asyncio
    async def test_search_multimodal_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("search_multimodal", client=client, query="test")
        client.search_multimodal.assert_awaited_once()
        call_kwargs = client.search_multimodal.call_args
        assert call_kwargs[0][0] == "test"  # query positional

    @pytest.mark.asyncio
    async def test_search_documents_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("search_documents", client=client, query="test")
        client.search_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_forwards_params(self) -> None:
        client = _mock_client()
        result = await _call(
            "search_multimodal", client=client,
            query="q", top_k=10, rerank=False, snippet_length=100,
        )
        _, kwargs = client.search_multimodal.call_args
        assert kwargs["top_k"] == 10
        assert kwargs["rerank"] is False
        assert kwargs["snippet_length"] == 100


class TestIngestOperations:
    @pytest.mark.asyncio
    async def test_ingest_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("ingest", client=client, id="doc-1", content="hello world")
        client.ingest.assert_awaited_once_with("doc-1", "hello world", category=None, title=None)

    @pytest.mark.asyncio
    async def test_ingest_with_metadata(self) -> None:
        client = _mock_client()
        result = await _call(
            "ingest", client=client,
            id="doc-1", content="hello", category="docs", title="Test",
        )
        client.ingest.assert_awaited_once_with("doc-1", "hello", category="docs", title="Test")


class TestStatsOperation:
    @pytest.mark.asyncio
    async def test_stats_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("stats", client=client)
        client.stats.assert_awaited_once()
        assert result["result"]["vectors"] == 42


class TestDeleteOperations:
    @pytest.mark.asyncio
    async def test_delete_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("delete", client=client, id="doc-1")
        client.delete.assert_awaited_once_with("doc-1")

    @pytest.mark.asyncio
    async def test_delete_license_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("delete_license", client=client, license_key="lic-1")
        client.delete_license.assert_awaited_once_with("lic-1")


class TestGetOperations:
    @pytest.mark.asyncio
    async def test_get_document_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("get_document", client=client, id="doc-1")
        client.get_document.assert_awaited_once_with("doc-1")

    @pytest.mark.asyncio
    async def test_get_image_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("get_image", client=client, id="img-1")
        client.get_image.assert_awaited_once_with("img-1")

    @pytest.mark.asyncio
    async def test_list_documents_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("list_documents", client=client, limit=20, offset=5)
        client.list_documents.assert_awaited_once_with(limit=20, offset=5)


class TestLicenseOperations:
    @pytest.mark.asyncio
    async def test_license_validate_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("license_validate", client=client, license_key="lic-1")
        client.license_validate.assert_awaited_once_with("lic-1")

    @pytest.mark.asyncio
    async def test_license_create_dispatches(self) -> None:
        client = _mock_client()
        result = await _call(
            "license_create", client=client,
            email="user@test.com", plan="pro",
            max_documents=1000, max_queries_per_day=500,
        )
        client.license_create.assert_awaited_once_with(
            "user@test.com", plan="pro",
            max_documents=1000, max_queries_per_day=500,
        )

    @pytest.mark.asyncio
    async def test_license_list_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("license_list", client=client)
        client.license_list.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_license_revoke_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("license_revoke", client=client, license_key="lic-1")
        client.license_revoke.assert_awaited_once_with("lic-1")


class TestResetOperations:
    @pytest.mark.asyncio
    async def test_reset_all_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("reset_all", client=client, passphrase="secret")
        client.reset_all.assert_awaited_once_with("secret")

    @pytest.mark.asyncio
    async def test_reset_documents_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("reset_documents", client=client, passphrase="secret")
        client.reset_documents.assert_awaited_once_with("secret")

    @pytest.mark.asyncio
    async def test_reset_licenses_dispatches(self) -> None:
        client = _mock_client()
        result = await _call("reset_licenses", client=client, passphrase="secret")
        client.reset_licenses.assert_awaited_once_with("secret")
