"""Shared fixtures for vectorize-mcp-tool tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def base_url() -> str:
    return "https://test-worker.example.com"


@pytest.fixture
def api_key() -> str:
    return "test-api-key-123"
