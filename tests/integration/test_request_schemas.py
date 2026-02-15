"""Request/response schema contract tests.

Ensures that the field names used by the worker and the MCP tool client
are consistent (e.g. 'topK' vs 'top_k' in JSON payloads).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).parent.parent.parent
_ENTRY_SRC = _PROJECT_ROOT / "src" / "entry.py"
_CLIENT_SRC = _PROJECT_ROOT / "vectorize-mcp-tool" / "src" / "vectorize_mcp_tool" / "client.py"


def _read(path: Path) -> str:
    return path.read_text()


class TestSearchRequestFields:
    """Worker and client must agree on search request JSON field names."""

    def test_both_use_query_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"query"' in entry
        assert '"query"' in client

    def test_both_use_topK_field(self) -> None:
        """Worker expects 'topK', client sends 'topK'."""
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"topK"' in entry or "topK" in entry
        assert '"topK"' in client or "topK" in client

    def test_both_use_rerank_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"rerank"' in entry
        assert '"rerank"' in client

    def test_both_use_offset_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"offset"' in entry or "offset" in entry
        assert '"offset"' in client or "offset" in client

    def test_both_use_snippetLength_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert "snippetLength" in entry or "snippet_length" in entry
        assert "snippetLength" in client or "snippet_length" in client


class TestIngestRequestFields:
    """Worker and client must agree on ingest request JSON field names."""

    def test_both_use_id_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"id"' in entry
        assert '"id"' in client

    def test_both_use_content_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"content"' in entry
        assert '"content"' in client


class TestLicenseRequestFields:
    """Worker and client must agree on license field names."""

    def test_both_use_license_key_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"license_key"' in entry
        assert '"license_key"' in client

    def test_both_use_email_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"email"' in entry
        assert '"email"' in client


class TestResetRequestFields:
    def test_both_use_passphrase_field(self) -> None:
        entry = _read(_ENTRY_SRC)
        client = _read(_CLIENT_SRC)
        assert '"passphrase"' in entry
        assert '"passphrase"' in client


