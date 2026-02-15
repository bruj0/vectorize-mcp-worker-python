"""CloudflareAIProvider -- wraps env.AI binding.

Provides embedding generation and cross-encoder reranking using
Workers AI with the same models as the TS original:
- Embedding: @cf/baai/bge-small-en-v1.5 (384 dimensions)
- Reranker: @cf/baai/bge-reranker-base
"""

from __future__ import annotations

from pyodide.ffi import JsProxy

from src.bindings.ffi_utils import to_js


class CloudflareAIProvider:
    """Implements AIProvider protocol using env.AI."""

    EMBEDDING_MODEL = "@cf/baai/bge-small-en-v1.5"
    RERANKER_MODEL = "@cf/baai/bge-reranker-base"

    def __init__(self, ai_binding: JsProxy) -> None:
        self._ai = ai_binding

    async def embed(self, text: str) -> list[float]:
        """Generate a 384-dim embedding for a single text."""
        result = await self._ai.run(self.EMBEDDING_MODEL, to_js({"text": text}))

        # Workers AI returns either a flat array or { data: [[...]] }
        if hasattr(result, "data"):
            js_data = result.data
            if hasattr(js_data, "length") and js_data.length > 0:
                return list(js_data[0].to_py())
        # Flat array case
        return list(result.to_py()) if hasattr(result, "to_py") else list(result)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts. Sequential calls to embed()."""
        return [await self.embed(text) for text in texts]

    async def rerank(self, query: str, contexts: list[str]) -> list[float]:
        """Cross-encoder reranking. Returns a score per context."""
        js_input = to_js({
            "query": query,
            "contexts": [{"text": ctx} for ctx in contexts],
        })
        result = await self._ai.run(self.RERANKER_MODEL, js_input)

        scores: list[float] = []
        if hasattr(result, "data"):
            js_data = result.data
            for i in range(js_data.length):
                score = js_data[i].score if hasattr(js_data[i], "score") else 0.0
                scores.append(float(score))
        else:
            # Fallback: zeros if reranker response is unexpected
            scores = [0.0] * len(contexts)

        return scores
