"""Tests for Pydantic data models."""

from __future__ import annotations

import pytest

from src.models import (
    Chunk,
    DocStats,
    Document,
    HybridSearchResult,
    ImageDescription,
    ImageDocument,
    IndexStats,
    KeywordRow,
    License,
    SearchResult,
    VectorMatch,
    VectorRecord,
)


class TestDocument:
    def test_required_fields(self) -> None:
        doc = Document(id="d1", content="hello")
        assert doc.id == "d1"
        assert doc.content == "hello"

    def test_optional_fields_default_none(self) -> None:
        doc = Document(id="d1", content="hello")
        assert doc.title is None
        assert doc.source is None
        assert doc.category is None

    def test_all_fields(self) -> None:
        doc = Document(id="d1", content="hello", title="T", source="S", category="C")
        assert doc.title == "T"


class TestImageDocument:
    def test_inherits_document(self) -> None:
        img = ImageDocument(id="i1", content="", image_buffer=b"\x89PNG")
        assert isinstance(img, Document)

    def test_image_type_default(self) -> None:
        img = ImageDocument(id="i1", content="", image_buffer=b"\x89PNG")
        assert img.image_type == "auto"

    def test_image_buffer_excluded_from_dict(self) -> None:
        img = ImageDocument(id="i1", content="", image_buffer=b"\x89PNG")
        d = img.model_dump()
        assert "image_buffer" not in d

    def test_valid_image_types(self) -> None:
        for t in ("screenshot", "diagram", "photo", "document", "chart", "auto"):
            img = ImageDocument(id="i1", content="", image_buffer=b"x", image_type=t)
            assert img.image_type == t


class TestChunk:
    def test_fields(self) -> None:
        c = Chunk(id="c1", content="text", parent_id="p1", chunk_index=0)
        assert c.parent_id == "p1"
        assert c.chunk_index == 0


class TestSearchResult:
    def test_defaults(self) -> None:
        r = SearchResult(id="r1", content="text", score=0.9)
        assert r.source == "hybrid"
        assert r.is_image is False

    def test_is_image(self) -> None:
        r = SearchResult(id="r1", content="text", score=0.9, is_image=True)
        assert r.is_image is True


class TestHybridSearchResult:
    def test_inherits_search_result(self) -> None:
        h = HybridSearchResult(id="h1", content="text", score=0.9)
        assert isinstance(h, SearchResult)

    def test_score_defaults(self) -> None:
        h = HybridSearchResult(id="h1", content="text", score=0.9)
        assert h.vector_score is None
        assert h.keyword_score is None
        assert h.reranker_score is None
        assert h.rrf_score == 0.0


class TestVectorRecord:
    def test_metadata_default_empty(self) -> None:
        v = VectorRecord(id="v1", values=[0.1, 0.2])
        assert v.metadata == {}


class TestVectorMatch:
    def test_fields(self) -> None:
        m = VectorMatch(id="m1", score=0.95)
        assert m.metadata == {}


class TestIndexStats:
    def test_defaults(self) -> None:
        s = IndexStats()
        assert s.vectors_count == 0
        assert s.dimensions == 384


class TestImageDescription:
    def test_success(self) -> None:
        d = ImageDescription(success=True, description="A cat", vector=[0.1, 0.2])
        assert d.success is True
        assert d.has_extracted_text is False

    def test_error(self) -> None:
        d = ImageDescription(success=False, error="timeout")
        assert d.error == "timeout"


class TestLicense:
    def test_defaults(self) -> None:
        lic = License(license_key="abc-123")
        assert lic.plan == "standard"
        assert lic.max_documents == 10000
        assert lic.is_active is True


class TestDocStats:
    def test_defaults(self) -> None:
        ds = DocStats()
        assert ds.total_documents == 0
        assert ds.avg_doc_length == 0.0


class TestKeywordRow:
    def test_defaults(self) -> None:
        kr = KeywordRow(id="k1", content="text")
        assert kr.term_frequency == 0
        assert kr.is_image is False
