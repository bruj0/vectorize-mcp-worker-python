"""Multipart form-data parser for Cloudflare Python Workers (Pyodide).

The Python ``workers.Request`` wrapper **does not expose** the JS
``formData()`` method.  This module reads the raw body bytes through the
JS FFI layer and splits on multipart boundaries -- fully in Python.

Usage::

    form = await parse_multipart(request, log)
    name  = form.get_text("name")
    image = form.get_bytes("image")
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from logger import RequestLogger, noop_logger


# ── data classes ──────────────────────────────────────────────────────

@dataclass
class FormField:
    """A single field parsed from a multipart form submission."""

    name: str
    value: bytes
    filename: str | None = None
    content_type: str | None = None

    @property
    def text(self) -> str:
        """Decode value as UTF-8 (lossy)."""
        return self.value.decode("utf-8", errors="replace")


class MultipartFormData:
    """Convenience wrapper around parsed multipart fields."""

    def __init__(self, fields: list[FormField]) -> None:
        self._fields = {f.name: f for f in fields}

    def get(self, name: str) -> FormField | None:
        return self._fields.get(name)

    def get_text(self, name: str, default: str = "") -> str:
        f = self._fields.get(name)
        return f.text if f else default

    def get_bytes(self, name: str) -> bytes | None:
        f = self._fields.get(name)
        return f.value if f else None


# ── public entry point ────────────────────────────────────────────────

async def parse_multipart(
    request,
    log: RequestLogger | None = None,
) -> MultipartFormData:
    """Parse ``multipart/form-data`` from a Cloudflare Workers request.

    Reads raw bytes through the JS FFI (Response intermediary) to avoid
    depending on the Python Request wrapper's ``formData()`` method.
    """
    log = log or noop_logger()

    content_type = (
        request.headers.get("Content-Type")
        or request.headers.get("content-type")
        or ""
    )

    if "multipart/form-data" not in content_type:
        raise ValueError(f"Expected multipart/form-data, got: {content_type}")

    # Extract boundary
    boundary: str | None = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[len("boundary="):].strip('"')
            break

    if not boundary:
        raise ValueError("No boundary found in Content-Type header")

    log.debug_log("multipart boundary extracted", boundary=boundary)

    # Read raw body bytes via JS FFI
    body = await _get_request_bytes(request, log)
    log.debug_log("multipart body read", bodyLength=len(body))

    # Parse
    fields = _parse_body(body, boundary.encode("ascii"))
    log.debug_log(
        "multipart parsed",
        fieldCount=len(fields),
        fieldNames=[f.name for f in fields],
        fileSizes={f.name: len(f.value) for f in fields if f.filename},
    )
    return MultipartFormData(fields)


# ── internals ─────────────────────────────────────────────────────────

async def _get_request_bytes(request, log: RequestLogger) -> bytes:
    """Read raw body bytes trying several Pyodide-compatible methods.

    1. JS ``Response`` intermediary  (wraps ``request.body`` ReadableStream)
    2. ``request.bytes()``           (may exist in newer SDK)
    3. ``request.arrayBuffer()``     (JS-style)
    """
    # Primary: JS Response intermediary
    try:
        from js import Response as JsResponse  # type: ignore[import-untyped]

        js_resp = JsResponse.new(request.body)
        buf = await js_resp.arrayBuffer()
        raw = bytes(buf.to_py())
        log.debug_log("body read via JS Response intermediary", size=len(raw))
        return raw
    except Exception as e:
        log.debug_log("JS Response intermediary failed, trying fallbacks", error=str(e))

    # Fallback 1: request.bytes()
    if hasattr(request, "bytes"):
        try:
            raw = await request.bytes()
            log.debug_log("body read via request.bytes()", size=len(raw))
            return raw
        except Exception as e:
            log.debug_log("request.bytes() failed", error=str(e))

    # Fallback 2: request.arrayBuffer()
    if hasattr(request, "arrayBuffer"):
        try:
            ab = await request.arrayBuffer()
            raw = bytes(ab.to_py()) if hasattr(ab, "to_py") else bytes(ab)
            log.debug_log("body read via request.arrayBuffer()", size=len(raw))
            return raw
        except Exception as e:
            log.debug_log("request.arrayBuffer() failed", error=str(e))

    raise RuntimeError(
        "Unable to read request body as bytes. "
        "None of the Pyodide FFI methods succeeded."
    )


def _parse_body(body: bytes, boundary: bytes) -> list[FormField]:
    """Split raw multipart body on boundaries into ``FormField`` objects."""
    fields: list[FormField] = []
    delimiter = b"--" + boundary
    parts = body.split(delimiter)

    for part in parts[1:]:  # skip preamble
        if part.startswith(b"--"):  # closing boundary
            break

        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue

        header_section = part[2:header_end]  # skip leading \r\n
        body_section = part[header_end + 4 :]

        # Strip trailing \r\n
        if body_section.endswith(b"\r\n"):
            body_section = body_section[:-2]

        # Parse headers
        headers: dict[bytes, bytes] = {}
        for line in header_section.split(b"\r\n"):
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.strip().lower()] = value.strip()

        cd = headers.get(b"content-disposition", b"").decode("utf-8", errors="replace")
        name = _extract_param(cd, "name")
        filename = _extract_param(cd, "filename")
        ct_raw = headers.get(b"content-type", b"")
        ct = ct_raw.decode("utf-8", errors="replace") if ct_raw else None

        if name:
            fields.append(
                FormField(name=name, value=body_section, filename=filename, content_type=ct or None)
            )

    return fields


def _extract_param(header: str, param: str) -> str | None:
    """Extract a quoted or unquoted parameter from a header value."""
    match = re.search(rf'{param}="([^"]*)"', header)
    if match:
        return match.group(1)
    match = re.search(rf"{param}=([^\s;]+)", header)
    return match.group(1) if match else None
