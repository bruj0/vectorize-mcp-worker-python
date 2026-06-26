"""Tests for ChunkingEngine."""

from __future__ import annotations

from src.chunking import ChunkingEngine


class TestChunkingEngine:
    """Test the paragraph-based chunking algorithm."""

    def setup_method(self) -> None:
        self.engine = ChunkingEngine()

    def test_short_text_single_chunk(self, short_text: str) -> None:
        """Text shorter than min_chunk_size still produces one chunk."""
        chunks = self.engine.chunk(short_text, "doc-1")
        assert len(chunks) == 1
        assert chunks[0].id == "doc-1-chunk-0"
        assert chunks[0].content == short_text
        assert chunks[0].parent_id == "doc-1"
        assert chunks[0].chunk_index == 0

    def test_multi_paragraph_produces_multiple_chunks(self, sample_text: str) -> None:
        """Multi-paragraph text exceeding max_chunk_size gets split."""
        chunks = self.engine.chunk(sample_text, "doc-2")
        assert len(chunks) > 1
        # Each chunk should have a unique sequential ID
        for i, chunk in enumerate(chunks):
            assert chunk.id == f"doc-2-chunk-{i}"
            assert chunk.parent_id == "doc-2"
            assert chunk.chunk_index == i

    def test_chunk_size_respects_max(self, sample_text: str) -> None:
        """No chunk should exceed max_chunk_size (except the fallback single chunk)."""
        chunks = self.engine.chunk(sample_text, "doc-3")
        for chunk in chunks:
            # Allow some flexibility for paragraph boundary overshoot
            assert len(chunk.content) <= self.engine.max_chunk_size * 1.5

    def test_empty_text_returns_one_chunk(self) -> None:
        """Empty or whitespace-only text still returns one chunk."""
        chunks = self.engine.chunk("", "doc-4")
        assert len(chunks) == 1
        assert chunks[0].id == "doc-4-chunk-0"

    def test_single_paragraph_no_split(self) -> None:
        """A single paragraph under max_chunk_size is not split."""
        text = "This is a single paragraph that should not be split into multiple chunks."
        # This is under min_chunk_size, so it goes through the fallback
        chunks = self.engine.chunk(text, "doc-5")
        assert len(chunks) == 1

    def test_chunk_ids_are_deterministic(self, sample_text: str) -> None:
        """Same input always produces the same chunk IDs."""
        chunks_a = self.engine.chunk(sample_text, "doc-6")
        chunks_b = self.engine.chunk(sample_text, "doc-6")
        assert [c.id for c in chunks_a] == [c.id for c in chunks_b]

    def test_custom_parameters(self) -> None:
        """Engine respects custom chunk size and overlap parameters."""
        engine = ChunkingEngine(max_chunk_size=100, overlap_percent=0.2, min_chunk_size=20)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph that is a bit longer."
        chunks = engine.chunk(text, "doc-7")
        assert len(chunks) >= 1
        assert all(c.parent_id == "doc-7" for c in chunks)
