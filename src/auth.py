"""Authentication and CORS.

Enforces:
- Public routes: /, /health/check, /dashboard, /llms.txt
- API_KEY secret check via Bearer token
- Dev mode: if API_KEY not set, allow all requests
- CORS: Access-Control-Allow-Origin: *
"""

from __future__ import annotations

import hmac
import json
from urllib.parse import urlparse

from workers import Response

# Routes that skip authentication
PUBLIC_ROUTES: frozenset[str] = frozenset({
    "/", "/health/check", "/dashboard", "/llms.txt",
})


def cors_headers() -> dict[str, str]:
    """CORS headers applied to all responses."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


def json_response(data: dict, status: int = 200, extra_headers: dict | None = None) -> Response:
    """Create a JSON Response with CORS headers."""
    headers = {"Content-Type": "application/json", **cors_headers()}
    if extra_headers:
        headers.update(extra_headers)
    return Response(json.dumps(data), status=status, headers=headers)


def authenticate(request, env) -> Response | None:
    """Authenticate a request. Returns an error Response or None if OK."""
    url = urlparse(str(request.url))
    pathname = url.path

    # Skip auth for public endpoints
    if pathname in PUBLIC_ROUTES:
        return None

    # If API_KEY is not set, allow all requests (development mode)
    api_key = getattr(env, "API_KEY", None)
    if not api_key:
        return None

    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return json_response(
            {
                "error": "Missing Authorization header",
                "hint": "Include 'Authorization: Bearer YOUR_API_KEY' in your request",
            },
            status=401,
        )

    # Validate Bearer token (constant-time comparison to prevent timing attacks)
    token = str(auth_header).replace("Bearer ", "")
    if not hmac.compare_digest(token, str(api_key)):
        return json_response({"error": "Invalid API key"}, status=403)

    return None  # Authentication successful
