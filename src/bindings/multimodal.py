"""CloudflareMultimodalProcessor -- wraps env.MULTIMODAL service binding.

Mirrors the TS original's POST to http://internal/describe-image with
the same request/response contract. The service binding calls the
multimodal-pro-worker (Llama 4 Scout vision) internally.
"""

from __future__ import annotations

import json

from pyodide.ffi import JsProxy

from src.bindings.ffi_utils import to_js
from src.models import ImageDescription


class CloudflareMultimodalProcessor:
    """Implements ImageProcessor protocol using env.MULTIMODAL."""

    def __init__(self, multimodal_binding: JsProxy) -> None:
        self._binding = multimodal_binding

    async def describe_image(
        self,
        image_buffer: bytes,
        image_type: str = "auto",
        prompt: str | None = None,
    ) -> ImageDescription:
        """Process an image via the multimodal worker service binding.

        Sends the same payload as the TS original:
        { imageBuffer: number[], prompt?: string, imageType: string }
        """
        payload: dict = {
            "imageBuffer": list(image_buffer),
            "imageType": image_type,
        }
        if prompt:
            payload["prompt"] = prompt

        response = await self._binding.fetch(
            "http://internal/describe-image",
            to_js({
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload),
            }),
        )

        result_text = await response.text()
        result = json.loads(result_text)

        return ImageDescription(
            success=result.get("success", False),
            description=result.get("description", ""),
            extracted_text=result.get("extractedText"),
            vector=result.get("vector", []),
            processing_time=result.get("metadata", {}).get("processingTime", ""),
            has_extracted_text=result.get("metadata", {}).get("hasExtractedText", False),
            error=result.get("error"),
        )
