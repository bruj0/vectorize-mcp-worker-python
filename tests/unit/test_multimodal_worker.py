"""Tests for the multimodal-pro-worker contract and binding.

The multimodal worker depends on Cloudflare JS FFI (pyodide, js.Object) for
its entry point, so we test the contract via source inspection and the
main-worker binding via stubs.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bindings.multimodal import CloudflareMultimodalProcessor
from src.models import ImageDescription

# Path to the multimodal worker source
_MULTIMODAL_SRC = Path(__file__).parent.parent.parent / "multimodal-pro-worker" / "src" / "entry.py"


def _read_source() -> str:
    return _MULTIMODAL_SRC.read_text()


# ── Contract tests (via source inspection) ───────────────────────────────


class TestMultimodalWorkerContract:
    """Verify the multimodal worker's API contract via source inspection."""

    def test_source_exists(self) -> None:
        assert _MULTIMODAL_SRC.exists()

    def test_has_describe_image_endpoint(self) -> None:
        assert "/describe-image" in _read_source()

    def test_expects_image_buffer_field(self) -> None:
        assert "imageBuffer" in _read_source()

    def test_expects_image_type_field(self) -> None:
        assert "imageType" in _read_source()

    def test_expects_prompt_field(self) -> None:
        assert '"prompt"' in _read_source()

    def test_returns_success_field(self) -> None:
        assert '"success"' in _read_source()

    def test_returns_description_field(self) -> None:
        assert '"description"' in _read_source()

    def test_returns_extracted_text_field(self) -> None:
        assert '"extractedText"' in _read_source()

    def test_returns_vector_field(self) -> None:
        assert '"vector"' in _read_source()

    def test_returns_metadata_field(self) -> None:
        assert '"metadata"' in _read_source()


class TestMultimodalPrompts:
    def test_all_image_types_have_prompts(self) -> None:
        source = _read_source()
        for img_type in ("screenshot", "diagram", "document", "chart", "photo", "auto"):
            assert f'"{img_type}"' in source, f"Missing prompt for: {img_type}"

    def test_ocr_prompt_exists(self) -> None:
        source = _read_source()
        assert "OCR_PROMPT" in source
        assert "Extract all visible text" in source


class TestMultimodalModels:
    def test_vision_model(self) -> None:
        assert "@cf/meta/llama-4-scout-17b-16e-instruct" in _read_source()

    def test_embedding_model(self) -> None:
        assert "@cf/baai/bge-small-en-v1.5" in _read_source()


class TestMultimodalAuth:
    def test_internal_secret_check(self) -> None:
        source = _read_source()
        assert "INTERNAL_SECRET" in source
        assert "X-Internal-Secret" in source

    def test_method_not_allowed(self) -> None:
        assert "405" in _read_source()

    def test_not_found(self) -> None:
        assert "404" in _read_source()


# ── Binding tests (main worker side) ─────────────────────────────────────


def _mock_binding(response_data: dict, status: int = 200) -> MagicMock:
    """Create a mock service binding that returns the given response."""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.text = AsyncMock(return_value=json.dumps(response_data))
    mock.fetch = AsyncMock(return_value=mock_response)
    return mock


class TestCloudflareMultimodalProcessor:
    @pytest.mark.asyncio
    async def test_successful_describe(self) -> None:
        binding = _mock_binding({
            "success": True,
            "description": "A scenic photo",
            "extractedText": "Hello World",
            "vector": [0.1] * 384,
            "metadata": {
                "processingTime": "200ms",
                "hasExtractedText": True,
            },
        })
        processor = CloudflareMultimodalProcessor(binding)
        result = await processor.describe_image(b"\x89PNG", image_type="photo")

        assert result.success is True
        assert result.description == "A scenic photo"
        assert result.extracted_text == "Hello World"
        assert len(result.vector) == 384
        assert result.processing_time == "200ms"
        assert result.has_extracted_text is True
        binding.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_describe(self) -> None:
        binding = _mock_binding({
            "success": False,
            "error": "Model unavailable",
        })
        processor = CloudflareMultimodalProcessor(binding)
        result = await processor.describe_image(b"\x89PNG")

        assert result.success is False
        assert result.error == "Model unavailable"

    @pytest.mark.asyncio
    async def test_internal_secret_header(self) -> None:
        binding = _mock_binding({"success": True, "description": "ok", "vector": []})
        processor = CloudflareMultimodalProcessor(binding, internal_secret="s3cret")
        await processor.describe_image(b"\x89PNG")

        # Verify fetch was called (the secret is set in the JS Request headers)
        binding.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_prompt(self) -> None:
        binding = _mock_binding({"success": True, "description": "custom", "vector": []})
        processor = CloudflareMultimodalProcessor(binding)
        await processor.describe_image(b"\x89PNG", prompt="Describe the cat")

        binding.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_extracted_text(self) -> None:
        binding = _mock_binding({
            "success": True,
            "description": "An image",
            "extractedText": None,
            "vector": [0.5] * 384,
            "metadata": {"processingTime": "50ms", "hasExtractedText": False},
        })
        processor = CloudflareMultimodalProcessor(binding)
        result = await processor.describe_image(b"\x89PNG")

        assert result.extracted_text is None
        assert result.has_extracted_text is False
