"""Tests for MCP tool dispatch -- verifies the one-tool-with-operations pattern."""

from __future__ import annotations

import pytest

from src.mcp import TOOL_SCHEMA, dispatch_mcp_call


class TestToolSchema:
    """Test the MCP tool schema definition."""

    def test_single_tool(self) -> None:
        """Schema defines exactly one tool named 'vectorize'."""
        tools = TOOL_SCHEMA["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "vectorize"

    def test_operation_is_required(self) -> None:
        """The 'operation' parameter is required."""
        schema = TOOL_SCHEMA["tools"][0]["inputSchema"]
        assert "operation" in schema["required"]

    def test_all_operations_listed(self) -> None:
        """All 9 operations are in the enum."""
        ops = TOOL_SCHEMA["tools"][0]["inputSchema"]["properties"]["operation"]["enum"]
        expected = {
            "search", "ingest", "ingest_image", "stats", "delete",
            "license_validate", "license_create", "license_list", "license_revoke",
        }
        assert set(ops) == expected

    def test_search_params_defined(self) -> None:
        """Search-specific parameters (query, top_k, rerank) are defined."""
        props = TOOL_SCHEMA["tools"][0]["inputSchema"]["properties"]
        assert "query" in props
        assert "top_k" in props
        assert "rerank" in props

    def test_ingest_params_defined(self) -> None:
        """Ingest-specific parameters (id, content, category, title) are defined."""
        props = TOOL_SCHEMA["tools"][0]["inputSchema"]["properties"]
        assert "id" in props
        assert "content" in props
        assert "category" in props
        assert "title" in props


class TestDispatchValidation:
    """Test dispatch_mcp_call input validation (no Cloudflare runtime needed)."""

    @pytest.mark.asyncio
    async def test_missing_operation(self) -> None:
        """Missing operation returns error response."""
        from workers import Response
        result = await dispatch_mcp_call({}, _mock_ctx())
        assert isinstance(result, Response)

    @pytest.mark.asyncio
    async def test_unknown_operation(self) -> None:
        """Unknown operation returns error dict."""
        result = await dispatch_mcp_call({"operation": "foobar"}, _mock_ctx())
        assert "error" in result
        assert "Unknown operation" in result["error"]

    @pytest.mark.asyncio
    async def test_search_missing_query(self) -> None:
        """Search without query returns error."""
        result = await dispatch_mcp_call({"operation": "search"}, _mock_ctx())
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ingest_missing_fields(self) -> None:
        """Ingest without id/content returns error."""
        result = await dispatch_mcp_call({"operation": "ingest"}, _mock_ctx())
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_missing_id(self) -> None:
        """Delete without id returns error."""
        result = await dispatch_mcp_call({"operation": "delete"}, _mock_ctx())
        assert "error" in result

    @pytest.mark.asyncio
    async def test_license_validate_missing_key(self) -> None:
        """license_validate without license_key returns error."""
        result = await dispatch_mcp_call(
            {"operation": "license_validate"}, _mock_ctx()
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_license_create_missing_email(self) -> None:
        """license_create without email returns error."""
        result = await dispatch_mcp_call(
            {"operation": "license_create"}, _mock_ctx()
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_license_revoke_missing_key(self) -> None:
        """license_revoke without license_key returns error."""
        result = await dispatch_mcp_call(
            {"operation": "license_revoke"}, _mock_ctx()
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ingest_image_returns_guidance(self) -> None:
        """ingest_image via MCP returns guidance to use HTTP endpoint."""
        result = await dispatch_mcp_call(
            {"operation": "ingest_image"}, _mock_ctx()
        )
        assert "error" in result
        assert "/ingest-image" in result["error"]


def _mock_ctx() -> dict:
    """Minimal mock context for validation-only tests.

    Operations that need actual protocol calls will fail, but validation
    checks happen before those calls.
    """
    return {
        "vector_store": None,
        "keyword_store": None,
        "ai_provider": None,
        "image_processor": None,
        "license_store": None,
        "hybrid_search": None,
        "ingestion_engine": None,
    }
