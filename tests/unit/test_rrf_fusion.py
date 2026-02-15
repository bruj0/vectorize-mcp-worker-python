"""Tests for Reciprocal Rank Fusion logic in HybridSearchEngine."""

from __future__ import annotations

from src.hybrid_search import HybridSearchEngine
from src.models import SearchResult


class TestReciprocalRankFusion:
    """Test RRF fusion matches the TS original's formula."""

    def test_vector_only(self) -> None:
        """With only vector results, RRF scores are 1/(k+rank+1)."""
        vector_results = [
            SearchResult(id="a", content="doc a", score=0.9, source="vector"),
            SearchResult(id="b", content="doc b", score=0.7, source="vector"),
        ]
        fused = HybridSearchEngine.reciprocal_rank_fusion(vector_results, [])
        assert len(fused) == 2
        # First result: 1/(60+0+1) = 1/61
        assert abs(fused[0].rrf_score - 1.0 / 61) < 1e-9
        assert fused[0].vector_score == 0.9
        assert fused[0].keyword_score is None

    def test_keyword_only(self) -> None:
        """With only keyword results, RRF scores come from keyword ranks."""
        keyword_results = [
            SearchResult(id="x", content="doc x", score=5.0, source="keyword"),
            SearchResult(id="y", content="doc y", score=3.0, source="keyword"),
        ]
        fused = HybridSearchEngine.reciprocal_rank_fusion([], keyword_results)
        assert len(fused) == 2
        assert fused[0].keyword_score == 5.0
        assert fused[0].vector_score is None

    def test_overlapping_results_sum_scores(self) -> None:
        """Documents appearing in both vector and keyword results get summed RRF scores."""
        vector_results = [
            SearchResult(id="shared", content="shared doc", score=0.8, source="vector"),
        ]
        keyword_results = [
            SearchResult(id="shared", content="shared doc", score=4.0, source="keyword"),
        ]
        fused = HybridSearchEngine.reciprocal_rank_fusion(vector_results, keyword_results)
        assert len(fused) == 1
        # Score = 1/(60+0+1) + 1/(60+0+1) = 2/61
        expected = 2.0 / 61
        assert abs(fused[0].rrf_score - expected) < 1e-9
        assert fused[0].vector_score == 0.8
        assert fused[0].keyword_score == 4.0

    def test_results_sorted_by_rrf_score(self) -> None:
        """Output is sorted by RRF score descending."""
        vector_results = [
            SearchResult(id="a", content="a", score=0.9, source="vector"),
            SearchResult(id="b", content="b", score=0.5, source="vector"),
        ]
        keyword_results = [
            SearchResult(id="b", content="b", score=5.0, source="keyword"),
        ]
        fused = HybridSearchEngine.reciprocal_rank_fusion(vector_results, keyword_results)
        # "b" appears in both, "a" only in vector
        # b: 1/(60+1+1) + 1/(60+0+1) = 1/62 + 1/61
        # a: 1/(60+0+1) = 1/61
        assert fused[0].id == "b"

    def test_empty_inputs(self) -> None:
        """Empty inputs return empty list."""
        assert HybridSearchEngine.reciprocal_rank_fusion([], []) == []

    def test_rrf_k_parameter(self) -> None:
        """Custom RRF k value changes the scoring."""
        results = [SearchResult(id="a", content="a", score=1.0, source="vector")]
        fused_default = HybridSearchEngine.reciprocal_rank_fusion(results, [], rrf_k=60)
        fused_small = HybridSearchEngine.reciprocal_rank_fusion(results, [], rrf_k=10)
        # Smaller k gives higher scores: 1/11 > 1/61
        assert fused_small[0].rrf_score > fused_default[0].rrf_score
