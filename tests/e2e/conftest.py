"""E2E test fixtures -- requires VECTORIZE_E2E_URL and VECTORIZE_E2E_API_KEY."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure MCP tool is importable
from pathlib import Path

_mcp_tool_src = str(Path(__file__).parent.parent.parent / "vectorize-mcp-tool" / "src")
if _mcp_tool_src not in sys.path:
    sys.path.insert(0, _mcp_tool_src)


def _require_env(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        pytest.skip(f"{name} not set -- skipping E2E tests")
    return val


@pytest.fixture(scope="session")
def e2e_url() -> str:
    return _require_env("VECTORIZE_E2E_URL")


@pytest.fixture(scope="session")
def e2e_api_key() -> str:
    return _require_env("VECTORIZE_E2E_API_KEY")


@pytest.fixture(scope="session")
def e2e_client(e2e_url: str, e2e_api_key: str):
    from vectorize_mcp_tool.client import VectorizeClient
    return VectorizeClient(e2e_url, e2e_api_key, timeout=60.0)
