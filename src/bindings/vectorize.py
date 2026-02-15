"""CloudflareVectorStore -- wraps env.VECTORIZE binding.

Handles JS FFI conversions for the Vectorize index API.
All methods return Pydantic models, not raw JS objects.
"""

from __future__ import annotations

from typing import Any

from pyodide.ffi import JsProxy

from src.bindings.ffi_utils import to_js
from src.models import IndexStats, VectorMatch, VectorRecord


class CloudflareVectorStore:
    """Implements the VectorStore protocol using env.VECTORIZE."""

    def __init__(self, vectorize_binding: JsProxy) -> None:
        self._binding = vectorize_binding

    async def upsert(self, vectors: list[VectorRecord]) -> None:
        """Insert or update vectors in the Vectorize index."""
        js_vectors = to_js([
            {"id": v.id, "values": v.values, "metadata": v.metadata}
            for v in vectors
        ])
        await self._binding.upsert(js_vectors)

    async def query(
        self, embedding: list[float], top_k: int, return_metadata: bool = True
    ) -> list[VectorMatch]:
        """Cosine similarity search against the Vectorize index."""
        js_options = to_js({"topK": top_k, "returnMetadata": return_metadata})
        js_result = await self._binding.query(to_js(embedding), js_options)

        matches: list[VectorMatch] = []
        js_matches = js_result.matches
        for i in range(js_matches.length):
            m = js_matches[i]
            metadata: dict[str, Any] = {}
            if m.metadata:
                metadata = m.metadata.to_py()
            matches.append(VectorMatch(
                id=str(m.id),
                score=float(m.score),
                metadata=metadata,
            ))
        return matches

    async def delete_by_ids(self, ids: list[str]) -> None:
        """Delete vectors by their IDs."""
        await self._binding.deleteByIds(to_js(ids))

    async def describe(self) -> IndexStats:
        """Get index metadata (vector count, dimensions)."""
        js_stats = await self._binding.describe()
        return IndexStats(
            vectors_count=int(getattr(js_stats, "vectorsCount", 0)),
            dimensions=int(getattr(js_stats, "dimensions", 384)),
        )
