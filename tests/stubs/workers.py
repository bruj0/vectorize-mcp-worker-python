"""Stub for the workers module, used in tests outside the Cloudflare runtime.

Only provides the minimal types needed for test imports to work.
"""

from __future__ import annotations


class Response:
    """Minimal Response stub for testing."""

    def __init__(self, body: str = "", status: int = 200, headers: dict | None = None) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {}


class WorkerEntrypoint:
    """Minimal WorkerEntrypoint stub for testing."""

    env = None

    async def fetch(self, request) -> Response:
        raise NotImplementedError
