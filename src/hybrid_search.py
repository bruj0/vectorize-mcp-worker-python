"""HybridSearchEngine -- Reciprocal Rank Fusion with optional reranking.

Identical algorithm to the TS original:
- RRF constant k = 60
- Reranker weight: 0.4 * RRF + 0.6 * reranker score
- In-memory cache with 60s TTL
- Combines vector similarity search with BM25 keyword search
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from src.keyword_search import KeywordSearchEngine
from src.models import HybridSearchResult, SearchResult

if TYPE_CHECKING:
    from src.protocols import AIProvider, KeywordStore, VectorStore


class HybridSearchEngine:
    """Hybrid search combining vector + BM25 with RRF fusion.

    Mirrors the TS HybridSearchEngine class.
    """

    RRF_K = 60
    CACHE_TTL = 60.0  # seconds

    def __init__(self) -> None:
        self._keyword_engine = KeywordSearchEngine()
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def reciprocal_rank_fusion(
        vector_results: list[SearchResult],
        keyword_results: list[SearchResult],
        rrf_k: int = 60,
    ) -> list[HybridSearchResult]:
        """Merge vector and keyword results using Reciprocal Rank Fusion.

        Same formula as the TS original: score = sum(1 / (k + rank + 1)).
        """
        scores: dict[str, HybridSearchResult] = {}

        for rank, r in enumerate(vector_results):
            scores[r.id] = HybridSearchResult(
                id=r.id,
                content=r.content,
                score=r.score,
                category=r.category,
                source="hybrid",
                is_image=r.is_image,
                vector_score=r.score,
                rrf_score=1.0 / (rrf_k + rank + 1),
            )

        for rank, r in enumerate(keyword_results):
            if r.id in scores:
                existing = scores[r.id]
                existing.keyword_score = r.score
                existing.rrf_score += 1.0 / (rrf_k + rank + 1)
            else:
                scores[r.id] = HybridSearchResult(
                    id=r.id,
                    content=r.content,
                    score=r.score,
                    category=r.category,
                    source="hybrid",
                    is_image=r.is_image,
                    keyword_score=r.score,
                    rrf_score=1.0 / (rrf_k + rank + 1),
                )

        return sorted(scores.values(), key=lambda x: x.rrf_score, reverse=True)

    async def search(
        self,
        query: str,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
        ai_provider: AIProvider,
        top_k: int,
        use_reranker: bool,
    ) -> dict[str, Any]:
        """Full hybrid search pipeline: embed -> vector search + BM25 -> RRF -> rerank.

        Returns:
            Dict with 'results' (list[HybridSearchResult]) and 'performance' (timing dict).
        """
        # Check cache
        cache_key = f"{query}-{top_k}-{use_reranker}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached["timestamp"]) < self.CACHE_TTL:
            return {
                "results": cached["results"],
                "performance": {"totalTime": "0ms (cached)"},
            }

        start = time.time()
        perf: dict[str, str] = {}

        # Vector search: embed query, then search Vectorize
        emb_start = time.time()
        embedding = await ai_provider.embed(query)
        perf["embeddingTime"] = f"{int((time.time() - emb_start) * 1000)}ms"

        vec_start = time.time()
        vec_matches = await vector_store.query(embedding, top_k=top_k * 2)
        perf["vectorSearchTime"] = f"{int((time.time() - vec_start) * 1000)}ms"

        vector_results: list[SearchResult] = [
            SearchResult(
                id=m.id,
                content=m.metadata.get("content", ""),
                score=m.score,
                category=m.metadata.get("category"),
                source="vector",
                is_image=bool(m.metadata.get("isImage", False)),
            )
            for m in vec_matches
        ]

        # BM25 keyword search
        kw_start = time.time()
        keyword_results = await self._keyword_engine.search(keyword_store, query, top_k * 2)
        perf["keywordSearchTime"] = f"{int((time.time() - kw_start) * 1000)}ms"

        # Reciprocal Rank Fusion
        results = self.reciprocal_rank_fusion(vector_results, keyword_results, self.RRF_K)

        # Optional cross-encoder reranking
        if use_reranker and results:
            re_start = time.time()
            try:
                top_results = results[:10]
                reranker_scores = await ai_provider.rerank(
                    query, [r.content for r in top_results]
                )
                for i, r in enumerate(top_results):
                    score = reranker_scores[i] if i < len(reranker_scores) else 0.0
                    r.reranker_score = score
                    r.rrf_score = r.rrf_score * 0.4 + score * 0.6
                results = sorted(top_results, key=lambda x: x.rrf_score, reverse=True)
            except Exception:
                pass  # Use results without reranking on error, same as TS original
            perf["rerankerTime"] = f"{int((time.time() - re_start) * 1000)}ms"

        perf["totalTime"] = f"{int((time.time() - start) * 1000)}ms"

        # Cache results
        final_results = results[:top_k]
        self._cache[cache_key] = {"results": final_results, "timestamp": time.time()}

        return {"results": final_results, "performance": perf}
