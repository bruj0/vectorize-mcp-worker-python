"""Tests for auth module -- authenticate(), cors_headers(), json_response()."""

from __future__ import annotations

import json

import pytest

from src.auth import PUBLIC_ROUTES, authenticate, cors_headers, json_response


# ── Helpers ──────────────────────────────────────────────────────────────


class _FakeRequest:
    """Minimal request stub for auth tests."""

    def __init__(self, url: str, headers: dict | None = None) -> None:
        self.url = url
        self.headers = headers or {}


class _FakeEnv:
    """Minimal env stub with optional API_KEY."""

    def __init__(self, api_key: str | None = None) -> None:
        self.API_KEY = api_key


# ── cors_headers ─────────────────────────────────────────────────────────


class TestCorsHeaders:
    def test_returns_cors_fields(self) -> None:
        h = cors_headers()
        assert h["Access-Control-Allow-Origin"] == "*"
        assert "GET" in h["Access-Control-Allow-Methods"]
        assert "Authorization" in h["Access-Control-Allow-Headers"]


# ── json_response ────────────────────────────────────────────────────────


class TestJsonResponse:
    def test_default_status(self) -> None:
        resp = json_response({"ok": True})
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body == {"ok": True}

    def test_custom_status(self) -> None:
        resp = json_response({"error": "bad"}, status=400)
        assert resp.status == 400

    def test_includes_cors(self) -> None:
        resp = json_response({})
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    def test_content_type_json(self) -> None:
        resp = json_response({})
        assert resp.headers["Content-Type"] == "application/json"

    def test_extra_headers(self) -> None:
        resp = json_response({}, extra_headers={"X-Custom": "val"})
        assert resp.headers["X-Custom"] == "val"


# ── authenticate ─────────────────────────────────────────────────────────


class TestAuthenticate:
    def test_public_routes_skip_auth(self) -> None:
        """All PUBLIC_ROUTES return None (no error) regardless of API key."""
        env = _FakeEnv(api_key="secret")
        for route in PUBLIC_ROUTES:
            req = _FakeRequest(f"https://example.com{route}")
            assert authenticate(req, env) is None, f"Route {route} should be public"

    def test_dev_mode_no_api_key(self) -> None:
        """Without API_KEY set, all routes are allowed."""
        env = _FakeEnv(api_key=None)
        req = _FakeRequest("https://example.com/ingest/document")
        assert authenticate(req, env) is None

    def test_valid_bearer_token(self) -> None:
        env = _FakeEnv(api_key="my-secret")
        req = _FakeRequest(
            "https://example.com/ingest/document",
            headers={"Authorization": "Bearer my-secret"},
        )
        assert authenticate(req, env) is None

    def test_missing_auth_header(self) -> None:
        env = _FakeEnv(api_key="my-secret")
        req = _FakeRequest("https://example.com/ingest/document")
        resp = authenticate(req, env)
        assert resp is not None
        assert resp.status == 401

    def test_invalid_token(self) -> None:
        env = _FakeEnv(api_key="my-secret")
        req = _FakeRequest(
            "https://example.com/ingest/document",
            headers={"Authorization": "Bearer wrong-key"},
        )
        resp = authenticate(req, env)
        assert resp is not None
        assert resp.status == 403
