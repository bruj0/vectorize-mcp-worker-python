"""CloudflareMultimodalProcessor -- wraps env.MULTIMODAL service binding.

Mirrors the TS original's POST to http://internal/describe-image with
the same request/response contract. The service binding calls the
multimodal-pro-worker (Llama 4 Scout vision) internally.
"""

from __future__ import annotations

import json

from pyodide.ffi import JsProxy

from bindings.ffi_utils import to_js
from logger import RequestLogger, noop_logger
from models import ImageDescription


class CloudflareMultimodalProcessor:
    """Implements ImageProcessor protocol using env.MULTIMODAL."""

    def __init__(
        self,
        multimodal_binding: JsProxy,
        internal_secret: str | None = None,
        logger: RequestLogger | None = None,
    ) -> None:
        self._binding = multimodal_binding
        self._internal_secret = internal_secret
        self._log = logger or noop_logger()

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
        self._log.info(
            "multimodal.describe_image.start",
            imageSize=len(image_buffer),
            imageType=image_type,
            hasPrompt=bool(prompt),
        )

        payload: dict = {
            "imageBuffer": list(image_buffer),
            "imageType": image_type,
        }
        if prompt:
            payload["prompt"] = prompt

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._internal_secret:
            headers["X-Internal-Secret"] = self._internal_secret

        self._log.debug_log("multimodal.fetch", payloadSize=len(json.dumps(payload)))

        response = await self._binding.fetch(
            "http://internal/describe-image",
            to_js({
                "method": "POST",
                "headers": headers,
                "body": json.dumps(payload),
            }),
        )

        result_text = await response.text()
        self._log.debug_log("multimodal.response", status=response.status, bodyLength=len(result_text))

        result = json.loads(result_text)

        desc = ImageDescription(
            success=result.get("success", False),
            description=result.get("description", ""),
            extracted_text=result.get("extractedText"),
            vector=result.get("vector", []),
            processing_time=result.get("metadata", {}).get("processingTime", ""),
            has_extracted_text=result.get("metadata", {}).get("hasExtractedText", False),
            error=result.get("error"),
        )

        if desc.success:
            self._log.info(
                "multimodal.describe_image.ok",
                descriptionLength=len(desc.description),
                hasExtractedText=desc.has_extracted_text,
                vectorDim=len(desc.vector),
                processingTime=desc.processing_time,
            )
        else:
            self._log.error(
                "multimodal.describe_image.failed",
                error=desc.error,
            )

        return desc
