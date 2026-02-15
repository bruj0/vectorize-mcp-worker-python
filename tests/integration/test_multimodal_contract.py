"""Contract tests: multimodal worker <-> main worker binding sync.

Verifies that the CloudflareMultimodalProcessor (main worker) sends requests
matching what multimodal-pro-worker/src/entry.py expects, and vice versa.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MULTIMODAL_SRC = _PROJECT_ROOT / "multimodal-pro-worker" / "src" / "entry.py"
_BINDING_SRC = _PROJECT_ROOT / "src" / "bindings" / "multimodal.py"


def _read(path: Path) -> str:
    return path.read_text()


class TestRequestContract:
    """The main worker binding must send what the multimodal worker expects."""

    def test_binding_sends_image_buffer(self) -> None:
        """Binding sends 'imageBuffer' field."""
        binding_src = _read(_BINDING_SRC)
        assert '"imageBuffer"' in binding_src

    def test_worker_expects_image_buffer(self) -> None:
        """Worker parses 'imageBuffer' from body."""
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"imageBuffer"' in worker_src or "imageBuffer" in worker_src

    def test_binding_sends_image_type(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"imageType"' in binding_src

    def test_worker_expects_image_type(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"imageType"' in worker_src or "imageType" in worker_src

    def test_binding_sends_prompt(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"prompt"' in binding_src

    def test_worker_expects_prompt(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"prompt"' in worker_src

    def test_binding_sends_to_describe_image_path(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert "/describe-image" in binding_src

    def test_worker_handles_describe_image_path(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert "/describe-image" in worker_src

    def test_binding_sends_internal_secret_header(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert "X-Internal-Secret" in binding_src

    def test_worker_checks_internal_secret_header(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert "X-Internal-Secret" in worker_src


class TestResponseContract:
    """The multimodal worker must return what the binding expects."""

    def test_worker_returns_success(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"success"' in worker_src

    def test_binding_reads_success(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"success"' in binding_src or "success" in binding_src

    def test_worker_returns_description(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"description"' in worker_src

    def test_binding_reads_description(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"description"' in binding_src

    def test_worker_returns_extracted_text(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"extractedText"' in worker_src

    def test_binding_reads_extracted_text(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"extractedText"' in binding_src or "extractedText" in binding_src

    def test_worker_returns_vector(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"vector"' in worker_src

    def test_binding_reads_vector(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"vector"' in binding_src

    def test_worker_returns_metadata(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"metadata"' in worker_src

    def test_binding_reads_metadata(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"metadata"' in binding_src

    def test_worker_returns_processing_time(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"processingTime"' in worker_src

    def test_binding_reads_processing_time(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"processingTime"' in binding_src or "processingTime" in binding_src

    def test_worker_returns_has_extracted_text(self) -> None:
        worker_src = _read(_MULTIMODAL_SRC)
        assert '"hasExtractedText"' in worker_src

    def test_binding_reads_has_extracted_text(self) -> None:
        binding_src = _read(_BINDING_SRC)
        assert '"hasExtractedText"' in binding_src or "hasExtractedText" in binding_src
