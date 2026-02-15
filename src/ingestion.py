"""IngestionEngine -- document and image ingestion with chunking and dedup.

Mirrors the TS IngestionEngine class. Handles:
- Text document ingestion with automatic chunking
- Image ingestion via the ImageProcessor protocol (MULTIMODAL binding)
- Document deletion with vector cleanup
- De-duplication (delete existing before re-ingesting)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.chunking import ChunkingEngine
from src.keyword_search import compute_term_frequencies, tokenize
from src.models import VectorRecord

if TYPE_CHECKING:
    from src.models import Document, ImageDocument
    from src.protocols import AIProvider, ImageProcessor, KeywordStore, VectorStore


class IngestionEngine:
    """Ingest documents into Vectorize + D1.

    Mirrors the TS IngestionEngine class exactly.
    """

    def __init__(self) -> None:
        self._chunker = ChunkingEngine()

    async def ingest(
        self,
        doc: Document,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
        ai_provider: AIProvider,
    ) -> dict[str, Any]:
        """Ingest a text document with automatic chunking.

        Steps (same as TS original):
        1. De-duplicate: delete existing document if present
        2. Chunk the content
        3. Generate embeddings for each chunk (parallel in TS, sequential here)
        4. Store in D1 (document row + keyword index)
        5. Upsert vectors into Vectorize

        Returns:
            Dict with success, chunks count, and performance timings.
        """
        import time

        start = time.time()
        perf: dict[str, str] = {}

        # De-duplicate
        if await keyword_store.document_exists(doc.id):
            await self.delete(doc.id, vector_store, keyword_store)

        chunks = self._chunker.chunk(doc.content, doc.id)
        vectors: list[VectorRecord] = []

        emb_start = time.time()
        for chunk in chunks:
            embedding = await ai_provider.embed(chunk.content)
            tokens = tokenize(chunk.content)
            terms = compute_term_frequencies(tokens)

            # Store in D1
            await keyword_store.index_document(
                doc_id=chunk.id,
                content=chunk.content,
                title=doc.title,
                source=doc.source,
                category=doc.category,
                chunk_index=chunk.chunk_index,
                parent_id=chunk.parent_id,
                word_count=len(chunk.content.split()),
                is_image=False,
                terms=terms,
            )
            await keyword_store.update_doc_stats_increment(len(tokens))

            vectors.append(VectorRecord(
                id=chunk.id,
                values=embedding,
                metadata={
                    "content": chunk.content,
                    "category": doc.category or "",
                    "parentId": chunk.parent_id,
                    "chunkIndex": chunk.chunk_index,
                    "isImage": False,
                },
            ))

        perf["embeddingTime"] = f"{int((time.time() - emb_start) * 1000)}ms"

        if vectors:
            await vector_store.upsert(vectors)

        perf["totalTime"] = f"{int((time.time() - start) * 1000)}ms"

        return {"success": True, "chunks": len(chunks), "performance": perf}

    async def ingest_image(
        self,
        doc: ImageDocument,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
        image_processor: ImageProcessor,
    ) -> dict[str, Any]:
        """Ingest an image via the multimodal worker.

        Steps (same as TS original):
        1. Send image to MULTIMODAL service for description + vector
        2. Combine description with extracted text
        3. Store in D1 and Vectorize

        Returns:
            Dict with success, description, extracted_text, and performance.
        """
        import time

        start = time.time()
        perf: dict[str, str] = {}

        multimodal_start = time.time()
        result = await image_processor.describe_image(
            image_buffer=doc.image_buffer,
            image_type=doc.image_type,
            prompt=doc.content or None,
        )
        perf["multimodalProcessing"] = result.processing_time

        if not result.success:
            raise RuntimeError(result.error or "Multimodal processing failed")

        # Combine description with extracted text (same as TS original)
        full_content = result.description
        if result.extracted_text:
            full_content = f"{result.description}\n\nExtracted Text: {result.extracted_text}"

        # Store in D1
        tokens = tokenize(full_content)
        terms = compute_term_frequencies(tokens)

        await keyword_store.index_document(
            doc_id=doc.id,
            content=full_content,
            title=doc.title or "Image Document",
            source=doc.source or "image",
            category=doc.category or "images",
            chunk_index=0,
            parent_id=doc.id,
            word_count=len(full_content.split()),
            is_image=True,
            terms=terms,
        )
        await keyword_store.update_doc_stats_increment(len(tokens))

        # Store vector from multimodal response
        await vector_store.upsert([VectorRecord(
            id=doc.id,
            values=result.vector,
            metadata={
                "content": full_content,
                "category": doc.category or "images",
                "parentId": doc.id,
                "chunkIndex": 0,
                "isImage": True,
                "hasExtractedText": result.has_extracted_text,
            },
        )])

        perf["totalTime"] = f"{int((time.time() - start) * 1000)}ms"

        return {
            "success": True,
            "description": result.description,
            "extractedText": result.extracted_text,
            "performance": perf,
        }

    async def delete(
        self,
        doc_id: str,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
    ) -> None:
        """Delete a document and all its chunks from D1 and Vectorize."""
        ids = await keyword_store.delete_document(doc_id)
        if ids:
            await vector_store.delete_by_ids(ids)
