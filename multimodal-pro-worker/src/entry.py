"""Multimodal Pro Worker -- image description, OCR, and embedding via Llama 4 Scout.

This is a standalone Cloudflare Python Worker that processes images using
Workers AI. It exposes a single endpoint:

  POST /describe-image

The main vectorize-mcp-worker-python calls this via a Service Binding
(env.MULTIMODAL) so no public HTTP traffic is involved.

Models used:
  - @cf/meta/llama-4-scout-17b-16e-instruct  (vision: description + OCR)
  - @cf/baai/bge-small-en-v1.5               (text embedding: 384 dims)
"""

from __future__ import annotations

import json
import time

from js import Object
from pyodide.ffi import to_js as _to_js
from workers import Response, WorkerEntrypoint

from logger import RequestLogger


# ---------------------------------------------------------------------------
# FFI helpers (inline -- this worker is standalone, no shared bindings/)
# ---------------------------------------------------------------------------

def to_js(obj: dict | list):
    """Convert Python dict/list to JS Object/Array using Object.fromEntries."""
    return _to_js(obj, dict_converter=Object.fromEntries)


def json_response(data: dict, status: int = 200) -> Response:
    """Return a JSON response."""
    return Response(
        json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"},
    )


# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------

VISION_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
EMBEDDING_MODEL = "@cf/baai/bge-small-en-v1.5"

# Minimum chars of OCR output to consider it meaningful
OCR_MIN_LENGTH = 100


# ---------------------------------------------------------------------------
# Prompt templates keyed by imageType
# ---------------------------------------------------------------------------

DESCRIPTION_PROMPTS: dict[str, str] = {
    "screenshot": (
        "Describe this UI screenshot in detail for search indexing. "
        "Note the layout, buttons, forms, navigation elements, and any visible data."
    ),
    "diagram": (
        "Describe this diagram in detail for search indexing. "
        "Note the components, connections, flow, and any labels."
    ),
    "document": (
        "Describe this document in detail for search indexing. "
        "Summarize the content, structure, headings, and key information."
    ),
    "chart": (
        "Describe this data visualization in detail for search indexing. "
        "Note the chart type, axes, trends, data points, and key takeaways."
    ),
    "photo": (
        "Describe this photograph in detail for search indexing. "
        "Note the subjects, setting, actions, and any notable details."
    ),
    "auto": (
        "Describe this image in detail for search indexing. "
        "Include all relevant visual information."
    ),
}

OCR_PROMPT = (
    "Extract all visible text from this image verbatim. "
    "Return only the extracted text, nothing else. "
    "If there is no visible text, return an empty string."
)


# ---------------------------------------------------------------------------
# Worker entry point
# ---------------------------------------------------------------------------

class Default(WorkerEntrypoint):
    """Multimodal Pro Worker -- processes images via Workers AI."""

    async def fetch(self, request) -> Response:
        method = str(request.method)

        # ── Logger setup ──────────────────────────────────────────────
        debug_flag = str(getattr(self.env, "DEBUG_LOGGING", "") or "").lower()
        debug_enabled = debug_flag in ("true", "1", "yes")
        log = RequestLogger(debug=debug_enabled)

        url_str = str(request.url)
        log.info("request.start", method=method, url=url_str)

        # Only POST is supported
        if method == "OPTIONS":
            log.debug_log("CORS preflight")
            return Response("", status=204)

        if method != "POST":
            log.warn("method_not_allowed", method=method)
            return json_response({"error": "Method not allowed"}, status=405)

        # Shared-secret auth: reject requests without a valid INTERNAL_SECRET
        internal_secret = getattr(self.env, "INTERNAL_SECRET", None)
        if internal_secret:
            auth_header = request.headers.get("X-Internal-Secret") or ""
            if str(auth_header) != str(internal_secret):
                log.warn("auth.rejected", hasHeader=bool(auth_header))
                return json_response(
                    {"error": "Unauthorized. This worker is internal-only."},
                    status=403,
                )
            log.debug_log("auth.ok")
        else:
            log.debug_log("auth.skipped", reason="no INTERNAL_SECRET set")

        # Parse path
        path = "/"
        if "://" in url_str:
            after_scheme = url_str.split("://", 1)[1]
            slash_idx = after_scheme.find("/")
            if slash_idx != -1:
                path = after_scheme[slash_idx:]
                q_idx = path.find("?")
                if q_idx != -1:
                    path = path[:q_idx]

        if path != "/describe-image":
            log.warn("route.not_found", path=path)
            return json_response(
                {"error": f"Not found: {path}", "hint": "Use POST /describe-image"},
                status=404,
            )

        # Parse request body
        try:
            body_text = await request.text()
            log.debug_log("body.read", bodyLength=len(body_text))
            body = json.loads(body_text)
        except Exception as e:
            log.error("body.parse_failed", exc=e)
            return json_response(
                {"success": False, "error": f"Invalid JSON body: {e}"},
                status=400,
            )

        image_buffer = body.get("imageBuffer")
        if not image_buffer or not isinstance(image_buffer, list):
            log.warn("validation.missing_image_buffer", hasBuffer=bool(image_buffer))
            return json_response(
                {"success": False, "error": "Missing or invalid imageBuffer (expected number[])"},
                status=400,
            )

        image_type = body.get("imageType", "auto")
        custom_prompt = body.get("prompt")
        log.info(
            "describe_image.start",
            imageSize=len(image_buffer),
            imageType=image_type,
            hasCustomPrompt=bool(custom_prompt),
        )

        # Process the image
        try:
            result = await self._process_image(image_buffer, image_type, custom_prompt, log)
            log.info("describe_image.ok", processingTime=result.get("metadata", {}).get("processingTime"))
            return json_response(result)
        except Exception as e:
            log.error("describe_image.failed", exc=e)
            return json_response({"success": False, "error": str(e)}, status=500)

    async def _process_image(
        self,
        image_buffer: list[int],
        image_type: str,
        custom_prompt: str | None,
        log: RequestLogger,
    ) -> dict:
        """Run vision description, OCR, and embedding pipeline.

        Returns the full response dict matching the API contract.
        """
        start = time.time()

        # Convert image buffer to bytes for the vision model
        image_bytes = bytes(image_buffer)
        log.debug_log("pipeline.image_converted", byteLength=len(image_bytes))

        # --- Step 1: Describe the image ---
        description_prompt = custom_prompt or DESCRIPTION_PROMPTS.get(
            image_type, DESCRIPTION_PROMPTS["auto"]
        )
        log.info("pipeline.step1_description.start", imageType=image_type)
        desc_start = time.time()
        description = await self._run_vision(image_bytes, description_prompt, log)
        desc_time = int((time.time() - desc_start) * 1000)
        log.info("pipeline.step1_description.ok", descriptionLength=len(description), timeMs=desc_time)

        # --- Step 2: OCR extraction ---
        extracted_text: str | None = None
        has_extracted_text = False
        log.info("pipeline.step2_ocr.start")
        ocr_start = time.time()
        try:
            ocr_result = await self._run_vision(image_bytes, OCR_PROMPT, log)
            ocr_time = int((time.time() - ocr_start) * 1000)
            if ocr_result and len(ocr_result.strip()) >= OCR_MIN_LENGTH:
                extracted_text = ocr_result.strip()
                has_extracted_text = True
                log.info("pipeline.step2_ocr.ok", textLength=len(extracted_text), timeMs=ocr_time)
            else:
                log.info(
                    "pipeline.step2_ocr.below_threshold",
                    resultLength=len(ocr_result.strip()) if ocr_result else 0,
                    threshold=OCR_MIN_LENGTH,
                    timeMs=ocr_time,
                )
        except Exception as exc:
            # OCR is best-effort; don't fail the whole request
            log.warn("pipeline.step2_ocr.failed", exc=exc)

        # --- Step 3: Generate embedding from description ---
        embed_text = description
        if extracted_text:
            embed_text = f"{description}\n\n{extracted_text}"
        log.info("pipeline.step3_embedding.start", textLength=len(embed_text))
        emb_start = time.time()
        vector = await self._run_embedding(embed_text, log)
        emb_time = int((time.time() - emb_start) * 1000)
        log.info("pipeline.step3_embedding.ok", vectorDim=len(vector), timeMs=emb_time)

        processing_time = f"{int((time.time() - start) * 1000)}ms"
        log.info("pipeline.complete", processingTime=processing_time, hasExtractedText=has_extracted_text)

        return {
            "success": True,
            "description": description,
            "extractedText": extracted_text,
            "vector": vector,
            "metadata": {
                "processingTime": processing_time,
                "hasExtractedText": has_extracted_text,
            },
        }

    async def _run_vision(self, image_bytes: bytes, prompt: str, log: RequestLogger) -> str:
        """Call Llama 4 Scout with an image and text prompt."""
        log.debug_log("ai.vision.call", model=VISION_MODEL, promptLength=len(prompt))
        # Workers AI vision expects messages with image as a list of ints
        input_data = to_js({
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "image": list(image_bytes),
        })

        result = await self.env.AI.run(VISION_MODEL, input_data)

        # Workers AI returns { response: "..." } for text generation models
        if hasattr(result, "response"):
            text = str(result.response)
            log.debug_log("ai.vision.ok", responseLength=len(text))
            return text
        # Fallback: try to convert the whole result
        if hasattr(result, "to_py"):
            py_result = result.to_py()
            if isinstance(py_result, dict) and "response" in py_result:
                text = str(py_result["response"])
                log.debug_log("ai.vision.ok_fallback", responseLength=len(text))
                return text
        log.warn("ai.vision.unexpected_format", resultType=type(result).__name__)
        return str(result)

    async def _run_embedding(self, text: str, log: RequestLogger) -> list[float]:
        """Generate a 384-dim BGE embedding for text."""
        log.debug_log("ai.embed.call", model=EMBEDDING_MODEL, textLength=len(text))
        result = await self.env.AI.run(EMBEDDING_MODEL, to_js({"text": text}))

        # Workers AI returns either { data: [[...]] } or a flat array
        if hasattr(result, "data"):
            js_data = result.data
            if hasattr(js_data, "length") and js_data.length > 0:
                vec = list(js_data[0].to_py())
                log.debug_log("ai.embed.ok", dimensions=len(vec))
                return vec
        if hasattr(result, "to_py"):
            vec = list(result.to_py())
            log.debug_log("ai.embed.ok_fallback", dimensions=len(vec))
            return vec
        log.warn("ai.embed.unexpected_format", resultType=type(result).__name__)
        return list(result)
