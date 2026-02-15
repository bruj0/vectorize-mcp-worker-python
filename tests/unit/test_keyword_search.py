"""Tests for keyword search -- BM25 engine with mocked KeywordStore."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.keyword_search import (
    STOP_WORDS,
    KeywordSearchEngine,
    compute_term_frequencies,
    tokenize,
)
from src.models import DocStats, KeywordRow


class TestTokenize:
    def test_basic_tokenization(self) -> None:
        tokens = tokenize("Hello World Python")
        assert "hello" in tokens
        assert "world" in tokens
        assert "python" in tokens

    def test_stop_words_removed(self) -> None:
        tokens = tokenize("the quick brown fox and the lazy dog")
        for sw in ("the", "and"):
            assert sw not in tokens
        assert "quick" in tokens

    def test_short_tokens_removed(self) -> None:
        tokens = tokenize("I am ok not sure at all")
        # "am", "ok", "at" are <= 2 chars
        for short in ("am", "ok", "at"):
            assert short not in tokens

    def test_punctuation_handling(self) -> None:
        tokens = tokenize("Hello, world! How's it going?")
        assert "hello" in tokens
        assert "world" in tokens

    def test_empty_input(self) -> None:
        assert tokenize("") == []

    def test_only_stop_words(self) -> None:
        assert tokenize("the and or but") == []


class TestTermFrequencies:
    def test_basic_frequencies(self) -> None:
        tokens = ["apple", "banana", "apple", "cherry", "apple"]
        freqs = compute_term_frequencies(tokens)
        assert freqs["apple"] == 3
        assert freqs["banana"] == 1

    def test_empty_list(self) -> None:
        assert compute_term_frequencies([]) == {}


class TestKeywordSearchEngine:
    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        engine = KeywordSearchEngine()
        store = AsyncMock()
        # "the and" tokenizes to empty list
        results = await engine.search(store, "the and", top_k=5)
        assert results == []
        store.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_doc_stats(self) -> None:
        engine = KeywordSearchEngine()
        store = AsyncMock()
        store.search = AsyncMock(return_value=(None, []))
        results = await engine.search(store, "machine learning", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_bm25_scoring(self) -> None:
        engine = KeywordSearchEngine()
        store = AsyncMock()
        stats = DocStats(total_documents=100, avg_doc_length=50.0)
        rows = [
            KeywordRow(
                id="doc1", content="machine learning intro",
                term_frequency=3, doc_length=50, document_frequency=10,
            ),
            KeywordRow(
                id="doc2", content="machine learning advanced",
                term_frequency=1, doc_length=50, document_frequency=10,
            ),
        ]
        store.search = AsyncMock(return_value=(stats, rows))

        results = await engine.search(store, "machine learning", top_k=5)

        assert len(results) == 2
        assert results[0].source == "keyword"
        # Higher TF should score higher
        assert results[0].id == "doc1"
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_top_k_limit(self) -> None:
        engine = KeywordSearchEngine()
        store = AsyncMock()
        stats = DocStats(total_documents=100, avg_doc_length=50.0)
        rows = [
            KeywordRow(
                id=f"doc{i}", content=f"content {i}",
                term_frequency=10 - i, doc_length=50, document_frequency=5,
            )
            for i in range(5)
        ]
        store.search = AsyncMock(return_value=(stats, rows))

        results = await engine.search(store, "content search", top_k=2)
        assert len(results) == 2
