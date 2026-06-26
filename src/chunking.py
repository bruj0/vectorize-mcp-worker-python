"""ChunkingEngine -- paragraph-based recursive chunking with overlap.

Chunking algorithm settings:
- Max chunk size: 512 characters
- Overlap: 15% of max chunk size
- Min chunk size: 100 characters
- Splits on double newlines (paragraph boundaries)
"""

from __future__ import annotations

import re

from models import Chunk


class ChunkingEngine:
    """Respects semantic boundaries with 15% overlap."""

    def __init__(
        self,
        max_chunk_size: int = 512,
        overlap_percent: float = 0.15,
        min_chunk_size: int = 100,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.overlap_percent = overlap_percent
        self.min_chunk_size = min_chunk_size

    def chunk(self, text: str, document_id: str) -> list[Chunk]:
        """Split text into overlapping chunks at paragraph boundaries.

        Args:
            text: Raw document text.
            document_id: Parent document ID used to generate chunk IDs.

        Returns:
            List of Chunk objects. Always returns at least one chunk.
        """
        chunks: list[Chunk] = []
        # Split on double newlines, filter empty paragraphs
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

        current_chunk = ""
        chunk_index = 0
        overlap_size = int(self.max_chunk_size * self.overlap_percent)

        for paragraph in paragraphs:
            combined = f"{current_chunk}\n\n{paragraph}" if current_chunk else paragraph

            if len(combined) > self.max_chunk_size and current_chunk.strip():
                chunks.append(Chunk(
                    id=f"{document_id}-chunk-{chunk_index}",
                    content=current_chunk.strip(),
                    parent_id=document_id,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1
                # Keep overlap from the end of the previous chunk
                current_chunk = current_chunk[-overlap_size:]

            current_chunk = f"{current_chunk}\n\n{paragraph}" if current_chunk else paragraph

        # Flush remaining content
        if current_chunk.strip() and len(current_chunk.strip()) >= self.min_chunk_size:
            chunks.append(Chunk(
                id=f"{document_id}-chunk-{chunk_index}",
                content=current_chunk.strip(),
                parent_id=document_id,
                chunk_index=chunk_index,
            ))

        # Always return at least one chunk
        if not chunks:
            return [Chunk(
                id=f"{document_id}-chunk-0",
                content=text.strip(),
                parent_id=document_id,
                chunk_index=0,
            )]

        return chunks
