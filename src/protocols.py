"""Protocol abstractions for Cloudflare bindings.

Each protocol wraps one Cloudflare binding, isolating JS FFI details
from business logic. Business logic depends on protocols; binding wrappers
implement them with Pyodide's JsProxy/to_js conversions.

Why protocols over direct binding calls:
1. JS FFI isolation -- all to_js()/JsProxy conversion in one place
2. Testability -- mock protocols without the Cloudflare runtime
3. Type safety -- Pydantic models in, Pydantic models out
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from models import (
        DocStats,
        ImageDescription,
        IndexStats,
        KeywordRow,
        License,
        SearchResult,
        VectorMatch,
        VectorRecord,
    )


@runtime_checkable
class VectorStore(Protocol):
    """Wraps env.VECTORIZE -- Cloudflare Vectorize index.

    Methods mirror the Vectorize JS binding API exactly.
    """

    async def upsert(self, vectors: list[VectorRecord]) -> None:
        """Insert or update vectors. Mirrors env.VECTORIZE.upsert()."""
        ...

    async def query(
        self, embedding: list[float], top_k: int, return_metadata: bool = True
    ) -> list[VectorMatch]:
        """Cosine similarity search. Mirrors env.VECTORIZE.query()."""
        ...

    async def delete_by_ids(self, ids: list[str]) -> None:
        """Delete vectors by ID. Mirrors env.VECTORIZE.deleteByIds()."""
        ...

    async def describe(self) -> IndexStats:
        """Index metadata. Mirrors env.VECTORIZE.describe()."""
        ...


@runtime_checkable
class KeywordStore(Protocol):
    """Wraps env.DB for BM25 keyword search tables (documents, keywords, term_stats, doc_stats).

    The underlying D1 database uses the exact SQL schema from schema.sql.
    """

    async def index_document(
        self,
        doc_id: str,
        content: str,
        title: str | None,
        source: str | None,
        category: str | None,
        chunk_index: int,
        parent_id: str,
        word_count: int,
        is_image: bool,
        terms: dict[str, int],
    ) -> None:
        """Store a document and its keyword index in D1."""
        ...

    async def search(self, tokens: list[str], top_k: int) -> tuple[DocStats | None, list[KeywordRow]]:
        """BM25 keyword lookup. Returns corpus stats and matching rows."""
        ...

    async def delete_document(self, doc_id: str) -> list[str]:
        """Delete document and its chunks. Returns deleted IDs for vector cleanup."""
        ...

    async def get_doc_stats(self) -> DocStats | None:
        """Fetch corpus-level BM25 statistics from doc_stats table."""
        ...

    async def document_exists(self, doc_id: str) -> bool:
        """Check if a document or chunk with this ID exists."""
        ...

    async def update_doc_stats_increment(self, token_count: int) -> None:
        """Increment total_documents and update avg_doc_length after ingestion."""
        ...

    async def get_document(self, doc_id: str) -> dict | None:
        """Fetch a single document by ID with all columns."""
        ...

    async def list_documents(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List documents with pagination. Returns metadata (no full content)."""
        ...

    async def get_all_document_ids(self) -> list[str]:
        """Fetch all document IDs. Used by reset to clear Vectorize."""
        ...

    async def get_documents_metadata(self, ids: list[str]) -> dict[str, dict]:
        """Batch fetch metadata for document IDs. Returns {id: {title, source, ...}}."""
        ...

    async def reset(self) -> None:
        """Delete all documents, keywords, term_stats and reset doc_stats."""
        ...


@runtime_checkable
class AIProvider(Protocol):
    """Wraps env.AI -- Cloudflare Workers AI.

    Provides embedding generation and cross-encoder reranking.
    """

    async def embed(self, text: str) -> list[float]:
        """Generate embedding via @cf/baai/bge-small-en-v1.5. Returns 384-dim vector."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding generation. Default: sequential calls to embed()."""
        ...

    async def rerank(self, query: str, contexts: list[str]) -> list[float]:
        """Cross-encoder reranking via @cf/baai/bge-reranker-base. Returns scores."""
        ...


@runtime_checkable
class ImageProcessor(Protocol):
    """Wraps env.MULTIMODAL -- service binding to the multimodal worker.

    Mirrors the POST to http://internal/describe-image with the same
    request/response contract.
    """

    async def describe_image(
        self,
        image_buffer: bytes,
        image_type: str = "auto",
        prompt: str | None = None,
    ) -> ImageDescription:
        """Process an image and return description + vector."""
        ...


@runtime_checkable
class LicenseStore(Protocol):
    """Wraps env.DB for the licenses table.

    CRUD operations for license keys.
    """

    async def validate(self, license_key: str) -> License | None:
        """Validate a license key. Returns License if valid and active, None otherwise."""
        ...

    async def create(
        self,
        email: str,
        plan: str = "standard",
        max_documents: int | None = None,
        max_queries_per_day: int | None = None,
    ) -> License:
        """Create a new license. Returns the created License with generated key."""
        ...

    async def list_all(self, limit: int = 100) -> list[License]:
        """List all licenses ordered by creation date."""
        ...

    async def revoke(self, license_key: str) -> bool:
        """Revoke a license. Returns True if the operation succeeded."""
        ...

    async def delete(self, license_key: str) -> bool:
        """Delete a license row entirely. Returns True if found and deleted."""
        ...

    async def reset(self) -> int:
        """Delete all licenses. Returns count of deleted rows."""
        ...
