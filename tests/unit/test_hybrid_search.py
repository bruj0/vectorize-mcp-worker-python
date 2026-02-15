"""Tests for HybridSearchEngine with mocked protocol implementations."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.hybrid_search import HybridSearchEngine
from src.models import DocStats, KeywordRow, SearchResult, VectorMatch


def _mock_vector_store(matches: list[VectorMatch] | None = None) -> AsyncMock:
    store = AsyncMock()
    store.query = AsyncMock(return_value=matches or [])
    return store


def _mock_keyword_store(
    rows: list[KeywordRow] | None = None,
    doc_stats: DocStats | None = None,
) -> AsyncMock:
    store = AsyncMock()
    # KeywordSearchEngine.search calls keyword_store.search internally, but
    # the engine itself wraps it. We mock at the keyword_store level.
    stats = doc_stats or DocStats(total_documents=10, avg_doc_length=50.0)
    store.search = AsyncMock(return_value=(stats, rows or []))
    store.get_doc_stats = AsyncMock(return_value=stats)
    return store


def _mock_ai_provider(rerank_scores: list[float] | None = None) -> AsyncMock:
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1] * 384)
    provider.rerank = AsyncMock(return_value=rerank_scores or [0.9, 0.7, 0.5])
    return provider


class TestHybridSearchEngine:
    @pytest.mark.asyncio
    async def test_search_returns_results_and_performance(self) -> None:
        engine = HybridSearchEngine()
        vs = _mock_vector_store([
            VectorMatch(id="v1", score=0.95, metadata={"content": "hello", "isImage": False}),
        ])
        ks = _mock_keyword_store()
        ai = _mock_ai_provider()

        result = await engine.search("hello", vs, ks, ai, top_k=5, use_reranker=False)

        assert "results" in result
        assert "performance" in result
        assert isinstance(result["performance"], dict)
        ai.embed.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_search_with_reranker(self) -> None:
        engine = HybridSearchEngine()
        vs = _mock_vector_store([
            VectorMatch(id="v1", score=0.95, metadata={"content": "hello", "isImage": False}),
            VectorMatch(id="v2", score=0.80, metadata={"content": "world", "isImage": False}),
        ])
        ks = _mock_keyword_store()
        ai = _mock_ai_provider(rerank_scores=[0.9, 0.1])

        result = await engine.search("hello", vs, ks, ai, top_k=5, use_reranker=True)

        ai.rerank.assert_called_once()
        # Reranker should have modified rrf_scores
        for r in result["results"]:
            assert r.reranker_score is not None

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        engine = HybridSearchEngine()
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ai = _mock_ai_provider()

        # First call populates cache
        await engine.search("q", vs, ks, ai, top_k=5, use_reranker=True)
        # Second call should hit cache
        result = await engine.search("q", vs, ks, ai, top_k=5, use_reranker=True)

        assert "cached" in result["performance"]["totalTime"]
        # embed should only be called once (first call)
        assert ai.embed.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        engine = HybridSearchEngine()
        vs = _mock_vector_store([])
        ks = _mock_keyword_store()
        ai = _mock_ai_provider()

        result = await engine.search("nothing", vs, ks, ai, top_k=5, use_reranker=False)
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_reranker_failure_graceful(self) -> None:
        """If reranker raises, search still returns results."""
        engine = HybridSearchEngine()
        vs = _mock_vector_store([
            VectorMatch(id="v1", score=0.95, metadata={"content": "hello", "isImage": False}),
        ])
        ks = _mock_keyword_store()
        ai = _mock_ai_provider()
        ai.rerank = AsyncMock(side_effect=RuntimeError("AI down"))

        result = await engine.search("hello", vs, ks, ai, top_k=5, use_reranker=True)
        # Should still return results despite reranker failure
        assert len(result["results"]) >= 1
