"""CloudflareVectorStore -- wraps env.VECTORIZE binding.

Handles JS FFI conversions for the Vectorize index API.
All methods return Pydantic models, not raw JS objects.
"""

from __future__ import annotations

from typing import Any

from pyodide.ffi import JsProxy

from bindings.ffi_utils import to_js
from logger import RequestLogger, noop_logger
from models import IndexStats, VectorMatch, VectorRecord


class CloudflareVectorStore:
    """Implements the VectorStore protocol using env.VECTORIZE."""

    def __init__(self, vectorize_binding: JsProxy, logger: RequestLogger | None = None) -> None:
        self._binding = vectorize_binding
        self._log = logger or noop_logger()

    async def upsert(self, vectors: list[VectorRecord]) -> None:
        """Insert or update vectors in the Vectorize index."""
        self._log.debug_log("vectorize.upsert", count=len(vectors), ids=[v.id for v in vectors])
        js_vectors = to_js([
            # Explicit float() cast: Pyodide FFI can produce typed-array values
            # that Vectorize may reject. Plain Python floats are always safe.
            {"id": v.id, "values": [float(x) for x in v.values], "metadata": v.metadata}
            for v in vectors
        ])
        await self._binding.upsert(js_vectors)
        self._log.debug_log("vectorize.upsert.ok")

    async def query(
        self, embedding: list[float], top_k: int, return_metadata: bool = True
    ) -> list[VectorMatch]:
        """Cosine similarity search against the Vectorize index."""
        self._log.debug_log("vectorize.query", topK=top_k, embeddingDim=len(embedding))
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
        self._log.debug_log("vectorize.query.ok", matchCount=len(matches))
        return matches

    async def delete_by_ids(self, ids: list[str]) -> None:
        """Delete vectors by their IDs."""
        self._log.debug_log("vectorize.delete", ids=ids)
        await self._binding.deleteByIds(to_js(ids))
        self._log.debug_log("vectorize.delete.ok")

    async def describe(self) -> IndexStats:
        """Get index metadata (vector count, dimensions)."""
        self._log.debug_log("vectorize.describe")
        js_stats = await self._binding.describe()
        stats = IndexStats(
            vectors_count=int(getattr(js_stats, "vectorsCount", 0)),
            dimensions=int(getattr(js_stats, "dimensions", 384)),
        )
        self._log.debug_log("vectorize.describe.ok", vectorCount=stats.vectors_count, dimensions=stats.dimensions)
        return stats
