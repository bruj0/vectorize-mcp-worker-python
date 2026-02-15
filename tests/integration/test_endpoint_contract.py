"""Contract tests: verify the MCP tool stays in sync with the worker.

These tests import from both the worker and the MCP tool to ensure that:
1. The VectorizeClient covers all worker REST endpoints
2. The MCP tool server handles all operations listed in the metadata
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Ensure src/ and stubs are importable
_project_root = Path(__file__).parent.parent.parent
_src_dir = str(_project_root / "src")
_stubs_dir = str(_project_root / "tests" / "stubs")
for p in (_stubs_dir, _src_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# Also make MCP tool importable
_mcp_tool_src = str(_project_root / "vectorize-mcp-tool" / "src")
if _mcp_tool_src not in sys.path:
    sys.path.insert(0, _mcp_tool_src)


# ── Worker endpoint extraction ───────────────────────────────────────────

def _extract_worker_endpoints() -> set[str]:
    """Parse entry.py to extract all endpoint patterns."""
    entry_src = (_project_root / "src" / "entry.py").read_text()
    # Match patterns like: if pathname == "/search/multimodal"
    # and: if pathname.startswith("/delete/document/")
    endpoints = set()
    for match in re.finditer(r'pathname\s*==\s*"(/[^"]+)"', entry_src):
        endpoints.add(match.group(1))
    for match in re.finditer(r'pathname\s*in\s*\(([^)]+)\)', entry_src):
        for sub in re.finditer(r'"(/[^"]+)"', match.group(1)):
            endpoints.add(sub.group(1))
    for match in re.finditer(r'pathname\.startswith\("(/[^"]+)"\)', entry_src):
        endpoints.add(match.group(1) + ":param")
    return endpoints


def _extract_client_endpoints() -> set[str]:
    """Parse client.py to extract endpoint paths from URL construction."""
    client_src = (_project_root / "vectorize-mcp-tool" / "src" / "vectorize_mcp_tool" / "client.py").read_text()
    endpoints = set()
    # Match f-string paths: f"/get/document/{doc_id}" and plain "/search/multimodal"
    for match in re.finditer(r'[f"](/[a-z/_:-]+(?:/\{[^}]+\})?)["\?]?', client_src):
        path = match.group(1)
        path = re.sub(r'\{[^}]+\}', ':param', path)
        endpoints.add(path)
    # Also match paths in f-strings with query params: f"/list/documents?limit=..."
    for match in re.finditer(r'f"(/[a-z/_-]+)\?', client_src):
        endpoints.add(match.group(1))
    # Also match plain URL construction: f"{self.base_url}/health/check"
    for match in re.finditer(r'base_url\}/([a-z/_-]+)', client_src):
        endpoints.add("/" + match.group(1))
    return endpoints


# ── Tests ────────────────────────────────────────────────────────────────


class TestEndpointCoverage:
    """Ensure the MCP tool client covers all worker endpoints."""

    def test_worker_endpoints_exist(self) -> None:
        endpoints = _extract_worker_endpoints()
        assert len(endpoints) > 10, f"Only found {len(endpoints)} endpoints"

    def test_client_endpoints_exist(self) -> None:
        endpoints = _extract_client_endpoints()
        assert len(endpoints) > 10, f"Only found {len(endpoints)} endpoints"

    def test_all_worker_data_endpoints_in_client(self) -> None:
        """Every non-UI worker endpoint should have a client method."""
        worker_eps = _extract_worker_endpoints()
        client_eps = _extract_client_endpoints()

        # UI/metadata endpoints the client doesn't need to cover
        skip = {"/", "/dashboard", "/llms.txt"}

        missing = []
        for ep in worker_eps:
            if ep in skip:
                continue
            # Normalize startsWith patterns
            ep_normalized = ep.replace(":param", "").rstrip("/")
            # Check if any client endpoint contains a matching segment
            found = any(ep_normalized in c for c in client_eps)
            if not found:
                # Also check for query-param style (e.g. /list/documents?...)
                found = any(ep_normalized.split("?")[0] in c for c in client_eps)
            if not found:
                missing.append(ep)

        assert not missing, f"Worker endpoints not in client: {missing}"


class TestMCPToolOperationsMatchMetadata:
    """Verify the MCP server handles every operation from the metadata module."""

    def test_server_handles_all_operations(self) -> None:
        """The MCP server source should reference every operation from metadata."""
        from vectorize_mcp_tool.metadata import OPERATION_NAMES

        server_src = (
            _project_root / "vectorize-mcp-tool" / "src" / "vectorize_mcp_tool" / "server.py"
        ).read_text()

        missing = []
        for op in OPERATION_NAMES:
            if op not in server_src:
                missing.append(op)

        assert not missing, f"MCP server missing operations: {missing}"

    def test_metadata_operations_are_strings(self) -> None:
        from vectorize_mcp_tool.metadata import OPERATION_NAMES
        assert all(isinstance(op, str) for op in OPERATION_NAMES)

    def test_metadata_no_duplicate_operations(self) -> None:
        from vectorize_mcp_tool.metadata import OPERATION_NAMES
        assert len(OPERATION_NAMES) == len(set(OPERATION_NAMES))


class TestClientMethodCompleteness:
    """Ensure VectorizeClient has methods for key operations."""

    def test_has_search_methods(self) -> None:
        from vectorize_mcp_tool.client import VectorizeClient
        assert hasattr(VectorizeClient, "search_multimodal")
        assert hasattr(VectorizeClient, "search_documents")
        assert hasattr(VectorizeClient, "find_similar_images")

    def test_has_ingestion_methods(self) -> None:
        from vectorize_mcp_tool.client import VectorizeClient
        assert hasattr(VectorizeClient, "ingest")
        assert hasattr(VectorizeClient, "ingest_image")

    def test_has_retrieval_methods(self) -> None:
        from vectorize_mcp_tool.client import VectorizeClient
        assert hasattr(VectorizeClient, "get_document")
        assert hasattr(VectorizeClient, "get_image")
        assert hasattr(VectorizeClient, "list_documents")

    def test_has_delete_methods(self) -> None:
        from vectorize_mcp_tool.client import VectorizeClient
        assert hasattr(VectorizeClient, "delete")
        assert hasattr(VectorizeClient, "delete_license")

    def test_has_license_methods(self) -> None:
        from vectorize_mcp_tool.client import VectorizeClient
        assert hasattr(VectorizeClient, "license_create")
        assert hasattr(VectorizeClient, "license_validate")
        assert hasattr(VectorizeClient, "license_list")
        assert hasattr(VectorizeClient, "license_revoke")

    def test_has_reset_methods(self) -> None:
        from vectorize_mcp_tool.client import VectorizeClient
        assert hasattr(VectorizeClient, "init_reset_passphrase")
        assert hasattr(VectorizeClient, "reset_all")
        assert hasattr(VectorizeClient, "reset_documents")
        assert hasattr(VectorizeClient, "reset_licenses")

    def test_no_mcp_call_method(self) -> None:
        """mcp_call was removed -- ensure it stays removed."""
        from vectorize_mcp_tool.client import VectorizeClient
        assert not hasattr(VectorizeClient, "mcp_call")
