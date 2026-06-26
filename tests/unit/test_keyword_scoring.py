"""Tests for keyword search tokenization and BM25 scoring logic."""

from __future__ import annotations

from src.keyword_search import STOP_WORDS, compute_term_frequencies, tokenize


class TestTokenize:
    """Test tokenization."""

    def test_basic_tokenization(self) -> None:
        """Lowercase, strip punctuation, filter short tokens and stop words."""
        tokens = tokenize("The Quick Brown Fox jumped!")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens
        assert "jumped" in tokens
        # "the" is a stop word, removed
        assert "the" not in tokens

    def test_stop_words_removed(self) -> None:
        """All standard stop words are filtered."""
        text = " ".join(STOP_WORDS)
        tokens = tokenize(text)
        # All stop words plus short ones (<= 2 chars) should be removed
        assert len(tokens) == 0

    def test_short_tokens_removed(self) -> None:
        """Tokens with 2 or fewer characters are removed."""
        tokens = tokenize("I am an AI tool")
        assert "ai" not in tokens  # 2 chars
        assert "am" not in tokens  # 2 chars, also stop word
        assert "tool" in tokens

    def test_punctuation_handling(self) -> None:
        """Non-word characters are replaced with spaces."""
        tokens = tokenize("hello-world foo_bar baz.qux")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo_bar" in tokens  # underscore is a word char
        assert "baz" in tokens
        assert "qux" in tokens

    def test_empty_input(self) -> None:
        """Empty string returns empty list."""
        assert tokenize("") == []
        assert tokenize("   ") == []


class TestTermFrequencies:
    """Test term frequency computation."""

    def test_basic_frequencies(self) -> None:
        """Counts occurrences of each token."""
        tokens = ["hello", "world", "hello", "foo", "hello"]
        freq = compute_term_frequencies(tokens)
        assert freq["hello"] == 3
        assert freq["world"] == 1
        assert freq["foo"] == 1

    def test_empty_list(self) -> None:
        """Empty token list returns empty dict."""
        assert compute_term_frequencies([]) == {}
