"""KeywordSearchEngine -- BM25 keyword search.

Identical parameters to the TS original:
- k1 = 1.2
- b = 0.75
- Same stop words list
- Same tokenization (lowercase, strip non-word chars, filter length > 2)

The engine handles tokenization and BM25 scoring. Storage operations
are delegated to the KeywordStore protocol.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from models import SearchResult

if TYPE_CHECKING:
    from protocols import KeywordStore


# Same stop words as the TS original
STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "this", "that",
    "it", "they", "have", "has", "had",
})


def tokenize(text: str) -> list[str]:
    """Tokenize text using the same rules as the TS original.

    Lowercase, replace non-word chars with spaces, split on whitespace,
    filter tokens shorter than 3 chars and stop words.
    """
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [
        t for t in cleaned.split()
        if len(t) > 2 and t not in STOP_WORDS
    ]


def compute_term_frequencies(tokens: list[str]) -> dict[str, int]:
    """Count term frequencies for a token list."""
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return freq


class KeywordSearchEngine:
    """BM25 scoring engine. Delegates storage to KeywordStore protocol.

    Mirrors the TS KeywordSearchEngine class.
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    async def search(
        self, keyword_store: KeywordStore, query: str, top_k: int
    ) -> list[SearchResult]:
        """Perform BM25 keyword search.

        Args:
            keyword_store: Protocol implementation for D1 access.
            query: Raw search query text.
            top_k: Maximum number of results.

        Returns:
            Ranked list of SearchResult with source='keyword'.
        """
        tokens = tokenize(query)
        if not tokens:
            return []

        doc_stats, rows = await keyword_store.search(tokens, top_k * 2)
        if not doc_stats or not doc_stats.total_documents:
            return []

        # Aggregate BM25 scores per document
        scores: dict[str, dict] = {}
        for r in rows:
            idf = math.log(
                (doc_stats.total_documents - r.document_frequency + 0.5)
                / (r.document_frequency + 0.5)
                + 1
            )
            tf = (r.term_frequency * (self.k1 + 1)) / (
                r.term_frequency
                + self.k1
                * (1 - self.b + self.b * (r.doc_length / doc_stats.avg_doc_length))
            )

            if r.id in scores:
                scores[r.id]["score"] += idf * tf
            else:
                scores[r.id] = {
                    "score": idf * tf,
                    "content": r.content,
                    "category": r.category,
                    "is_image": r.is_image,
                }

        # Sort by score descending, take top_k
        sorted_results = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
        return [
            SearchResult(
                id=doc_id,
                content=data["content"],
                score=data["score"],
                category=data["category"],
                source="keyword",
                is_image=data["is_image"],
            )
            for doc_id, data in sorted_results[:top_k]
        ]
