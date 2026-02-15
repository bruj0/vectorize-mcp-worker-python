"""Pydantic data models -- mirrors TypeScript interfaces from the original.

Each model maps 1:1 to a TS interface in src/index.ts, providing type safety
and validation that the original gets from TypeScript's type system.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Mirrors the TS `Document` interface."""

    id: str
    content: str
    title: str | None = None
    source: str | None = None
    category: str | None = None


class ImageDocument(Document):
    """Mirrors the TS `ImageDocument` interface.

    Extends Document with image-specific fields for multimodal ingestion.
    """

    image_buffer: bytes = Field(exclude=True)
    image_description: str | None = None
    image_type: Literal["screenshot", "diagram", "photo", "document", "chart", "auto"] = "auto"


class Chunk(BaseModel):
    """Mirrors the TS `Chunk` interface.

    Represents a text segment produced by the ChunkingEngine.
    """

    id: str
    content: str
    parent_id: str
    chunk_index: int


class SearchResult(BaseModel):
    """Mirrors the TS `SearchResult` interface."""

    id: str
    content: str
    score: float
    category: str | None = None
    source: Literal["vector", "keyword", "hybrid"] = "hybrid"
    is_image: bool = False


class HybridSearchResult(SearchResult):
    """Mirrors the TS `HybridSearchResult` interface.

    Extends SearchResult with per-source scores and the fused RRF score.
    """

    vector_score: float | None = None
    keyword_score: float | None = None
    reranker_score: float | None = None
    rrf_score: float = 0.0


class VectorRecord(BaseModel):
    """A vector to upsert into Vectorize. Mirrors the shape passed to env.VECTORIZE.upsert()."""

    id: str
    values: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorMatch(BaseModel):
    """A single match returned from env.VECTORIZE.query()."""

    id: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexStats(BaseModel):
    """Stats returned from env.VECTORIZE.describe() and D1 doc_stats."""

    vectors_count: int = 0
    dimensions: int = 384
    total_documents: int = 0
    avg_doc_length: float = 0.0


class ImageDescription(BaseModel):
    """Response from the MULTIMODAL service binding for image processing."""

    success: bool
    description: str = ""
    extracted_text: str | None = None
    vector: list[float] = Field(default_factory=list)
    processing_time: str = ""
    has_extracted_text: bool = False
    error: str | None = None


class License(BaseModel):
    """Mirrors the inline license type used in D1 queries."""

    license_key: str
    email: str | None = None
    plan: str = "standard"
    max_documents: int = 10000
    max_queries_per_day: int = 1000
    created_at: str | None = None
    is_active: bool = True


class DocStats(BaseModel):
    """Row from the doc_stats table (BM25 corpus statistics)."""

    total_documents: int = 0
    avg_doc_length: float = 0.0


class KeywordRow(BaseModel):
    """Joined row from documents + keywords + term_stats for BM25 scoring."""

    id: str
    content: str
    category: str | None = None
    is_image: bool = False
    term_frequency: int = 0
    doc_length: int = 0
    document_frequency: int = 0
