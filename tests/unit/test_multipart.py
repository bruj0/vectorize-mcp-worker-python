"""Tests for multipart form parser -- _parse_body and helper functions."""

from __future__ import annotations

import pytest

from src.multipart import FormField, MultipartFormData, _extract_param, _parse_body


class TestFormField:
    def test_text_decode(self) -> None:
        f = FormField(name="name", value=b"hello")
        assert f.text == "hello"

    def test_text_decode_binary(self) -> None:
        f = FormField(name="img", value=b"\x89PNG\r\n", filename="img.png")
        # Should decode without raising (lossy)
        assert isinstance(f.text, str)


class TestMultipartFormData:
    def test_get_existing(self) -> None:
        fields = [FormField(name="id", value=b"doc-1")]
        form = MultipartFormData(fields)
        assert form.get("id") is not None
        assert form.get("id").text == "doc-1"

    def test_get_missing(self) -> None:
        form = MultipartFormData([])
        assert form.get("nope") is None

    def test_get_text_default(self) -> None:
        form = MultipartFormData([])
        assert form.get_text("nope", "fallback") == "fallback"

    def test_get_bytes(self) -> None:
        fields = [FormField(name="data", value=b"\x00\x01")]
        form = MultipartFormData(fields)
        assert form.get_bytes("data") == b"\x00\x01"
        assert form.get_bytes("nope") is None


class TestExtractParam:
    def test_quoted(self) -> None:
        assert _extract_param('form-data; name="field1"', "name") == "field1"

    def test_unquoted(self) -> None:
        assert _extract_param("form-data; name=field1", "name") == "field1"

    def test_missing(self) -> None:
        assert _extract_param("form-data", "name") is None

    def test_filename(self) -> None:
        header = 'form-data; name="image"; filename="photo.jpg"'
        assert _extract_param(header, "filename") == "photo.jpg"


class TestParseBody:
    def _build_multipart(self, fields: list[tuple[str, bytes, str | None]]) -> tuple[bytes, bytes]:
        """Build a multipart body from (name, value, filename) tuples."""
        boundary = b"----TestBoundary"
        parts = []
        for name, value, filename in fields:
            headers = f'Content-Disposition: form-data; name="{name}"'
            if filename:
                headers += f'; filename="{filename}"'
            parts.append(
                b"------TestBoundary\r\n"
                + headers.encode() + b"\r\n"
                + b"\r\n"
                + value + b"\r\n"
            )
        body = b"".join(parts) + b"------TestBoundary--\r\n"
        return body, boundary

    def test_single_text_field(self) -> None:
        body, boundary = self._build_multipart([("id", b"doc-1", None)])
        fields = _parse_body(body, boundary)
        assert len(fields) == 1
        assert fields[0].name == "id"
        assert fields[0].text == "doc-1"

    def test_multiple_fields(self) -> None:
        body, boundary = self._build_multipart([
            ("id", b"doc-1", None),
            ("category", b"docs", None),
        ])
        fields = _parse_body(body, boundary)
        assert len(fields) == 2

    def test_file_field(self) -> None:
        body, boundary = self._build_multipart([
            ("image", b"\x89PNG\r\n\x1a\n", "photo.png"),
        ])
        fields = _parse_body(body, boundary)
        assert len(fields) == 1
        assert fields[0].filename == "photo.png"
        assert fields[0].value == b"\x89PNG\r\n\x1a\n"

    def test_empty_body(self) -> None:
        boundary = b"----TestBoundary"
        body = b"------TestBoundary--\r\n"
        fields = _parse_body(body, boundary)
        assert len(fields) == 0
