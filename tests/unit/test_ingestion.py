"""Tests for IngestionEngine with mocked protocol implementations."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.ingestion import IngestionEngine
from src.models import Document, ImageDescription, ImageDocument


def _mock_vector_store() -> AsyncMock:
    store = AsyncMock()
    store.upsert = AsyncMock()
    store.delete_by_ids = AsyncMock()
    return store


def _mock_keyword_store(*, exists: bool = False) -> AsyncMock:
    store = AsyncMock()
    store.document_exists = AsyncMock(return_value=exists)
    store.index_document = AsyncMock()
    store.update_doc_stats_increment = AsyncMock()
    store.delete_document = AsyncMock(return_value=[])
    return store


def _mock_ai_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1] * 384)
    return provider


def _mock_image_processor(
    *, success: bool = True, description: str = "A cat photo"
) -> AsyncMock:
    proc = AsyncMock()
    proc.describe_image = AsyncMock(
        return_value=ImageDescription(
            success=success,
            description=description,
            extracted_text="some text" if success else None,
            vector=[0.1] * 384,
            processing_time="100ms",
            has_extracted_text=success,
            error=None if success else "failed",
        )
    )
    return proc


class TestIngestDocument:
    @pytest.mark.asyncio
    async def test_basic_ingest(self) -> None:
        engine = IngestionEngine()
        doc = Document(id="doc-1", content="Hello world.")
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ai = _mock_ai_provider()

        result = await engine.ingest(doc, vs, ks, ai)

        assert result["success"] is True
        assert result["chunks"] >= 1
        assert "performance" in result
        vs.upsert.assert_called_once()
        ks.index_document.assert_called()

    @pytest.mark.asyncio
    async def test_deduplication(self) -> None:
        """If document exists, it should be deleted before re-ingesting."""
        engine = IngestionEngine()
        doc = Document(id="doc-1", content="Hello world.")
        vs = _mock_vector_store()
        ks = _mock_keyword_store(exists=True)
        ks.delete_document = AsyncMock(return_value=["doc-1-chunk-0"])
        ai = _mock_ai_provider()

        result = await engine.ingest(doc, vs, ks, ai)

        assert result["success"] is True
        ks.delete_document.assert_called_once_with("doc-1")

    @pytest.mark.asyncio
    async def test_ingest_with_metadata(self) -> None:
        engine = IngestionEngine()
        doc = Document(
            id="doc-2",
            content="Content here.",
            title="Title",
            category="docs",
            source="upload",
        )
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ai = _mock_ai_provider()

        result = await engine.ingest(doc, vs, ks, ai)
        assert result["success"] is True


class TestIngestImage:
    @pytest.mark.asyncio
    async def test_basic_image_ingest(self) -> None:
        engine = IngestionEngine()
        doc = ImageDocument(
            id="img-1", content="", image_buffer=b"\x89PNG", category="images"
        )
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ip = _mock_image_processor()

        result = await engine.ingest_image(doc, vs, ks, ip)

        assert result["success"] is True
        assert result["description"] == "A cat photo"
        ip.describe_image.assert_called_once()
        vs.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_image_ingest_failure(self) -> None:
        engine = IngestionEngine()
        doc = ImageDocument(id="img-2", content="", image_buffer=b"\x89PNG")
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ip = _mock_image_processor(success=False)

        with pytest.raises(RuntimeError, match="failed"):
            await engine.ingest_image(doc, vs, ks, ip)


class TestDeleteDocument:
    @pytest.mark.asyncio
    async def test_delete_with_chunks(self) -> None:
        engine = IngestionEngine()
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ks.delete_document = AsyncMock(return_value=["d1-chunk-0", "d1-chunk-1"])

        await engine.delete("d1", vs, ks)

        ks.delete_document.assert_called_once_with("d1")
        vs.delete_by_ids.assert_called_once_with(["d1-chunk-0", "d1-chunk-1"])

    @pytest.mark.asyncio
    async def test_delete_no_chunks(self) -> None:
        engine = IngestionEngine()
        vs = _mock_vector_store()
        ks = _mock_keyword_store()
        ks.delete_document = AsyncMock(return_value=[])

        await engine.delete("d1", vs, ks)

        vs.delete_by_ids.assert_not_called()
