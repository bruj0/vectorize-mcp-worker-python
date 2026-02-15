"""Cloudflare D1 binding wrappers for keyword search and license storage.

Wraps env.DB (D1 SQLite) with two classes:
- CloudflareD1KeywordStore: BM25 keyword index (documents, keywords, term_stats, doc_stats)
- CloudflareD1LicenseStore: License CRUD (licenses table)

Both use the same D1 binding but operate on separate tables.
"""

from __future__ import annotations

import uuid

from pyodide.ffi import JsProxy

from bindings.ffi_utils import to_js
from logger import RequestLogger, noop_logger
from models import DocStats, KeywordRow, License


class CloudflareD1KeywordStore:
    """Implements KeywordStore protocol using env.DB (D1)."""

    def __init__(self, db_binding: JsProxy, logger: RequestLogger | None = None) -> None:
        self._db = db_binding
        self._log = logger or noop_logger()

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
        """Store document row + keyword index + term stats in a D1 batch."""
        self._log.debug_log(
            "d1.index_document",
            docId=doc_id,
            wordCount=word_count,
            termCount=len(terms),
            isImage=is_image,
        )
        batch_stmts = []

        # Insert document row
        # D1 via Pyodide FFI: Python None becomes JS undefined which D1 rejects.
        # Convert None to empty string for nullable text columns.
        batch_stmts.append(
            self._db.prepare(
                "INSERT INTO documents (id, content, title, source, category, "
                "chunk_index, parent_id, word_count, is_image) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ).bind(
                doc_id, content, title or "", source or "", category or "",
                chunk_index, parent_id, word_count, 1 if is_image else 0,
            )
        )

        # Insert keyword rows and update term stats
        for term, count in terms.items():
            batch_stmts.append(
                self._db.prepare(
                    "INSERT INTO keywords (document_id, term, term_frequency) "
                    "VALUES (?, ?, ?)"
                ).bind(doc_id, term, count)
            )
            batch_stmts.append(
                self._db.prepare(
                    "INSERT INTO term_stats (term, document_frequency) VALUES (?, 1) "
                    "ON CONFLICT(term) DO UPDATE SET document_frequency = document_frequency + 1"
                ).bind(term)
            )

        if batch_stmts:
            self._log.debug_log("d1.batch", statementCount=len(batch_stmts))
            await self._db.batch(to_js(batch_stmts))
            self._log.debug_log("d1.batch.ok")

    async def update_doc_stats_increment(self, token_count: int) -> None:
        """Increment total_documents and update rolling avg_doc_length."""
        self._log.debug_log("d1.update_doc_stats", tokenCount=token_count)
        await self._db.prepare(
            "UPDATE doc_stats SET total_documents = total_documents + 1, "
            "avg_doc_length = ((avg_doc_length * total_documents) + ?) / (total_documents + 1) "
            "WHERE id = 1"
        ).bind(token_count).run()

    async def search(
        self, tokens: list[str], top_k: int
    ) -> tuple[DocStats | None, list[KeywordRow]]:
        """BM25 keyword lookup using D1 SQL. Returns corpus stats and matching rows."""
        self._log.debug_log("d1.search", tokenCount=len(tokens), topK=top_k)
        stats_row = await self._db.prepare(
            "SELECT total_documents, avg_doc_length FROM doc_stats WHERE id = 1"
        ).first()

        if not stats_row or not stats_row.total_documents:
            self._log.debug_log("d1.search.no_stats")
            return None, []

        doc_stats = DocStats(
            total_documents=int(stats_row.total_documents),
            avg_doc_length=float(stats_row.avg_doc_length),
        )

        # Limit tokens to avoid SQLite variable limit (~999)
        limited_tokens = tokens[:100]
        if not limited_tokens:
            return doc_stats, []

        placeholders = ",".join("?" for _ in limited_tokens)
        sql = (
            f"SELECT d.id, d.content, d.category, d.is_image, "
            f"k.term, k.term_frequency, LENGTH(d.content) as doc_length, "
            f"ts.document_frequency "
            f"FROM documents d "
            f"JOIN keywords k ON d.id = k.document_id "
            f"JOIN term_stats ts ON k.term = ts.term "
            f"WHERE k.term IN ({placeholders})"
        )

        # D1 .bind() takes all parameters at once (variadic in JS).
        # Calling .bind() multiple times replaces previous bindings.
        stmt = self._db.prepare(sql).bind(*limited_tokens)

        result = await stmt.all()
        rows: list[KeywordRow] = []
        if result and result.results:
            js_results = result.results
            for i in range(js_results.length):
                r = js_results[i]
                rows.append(KeywordRow(
                    id=str(r.id),
                    content=str(r.content),
                    category=str(r.category) if r.category else None,
                    is_image=bool(r.is_image),
                    term_frequency=int(r.term_frequency),
                    doc_length=int(r.doc_length),
                    document_frequency=int(r.document_frequency),
                ))

        self._log.debug_log("d1.search.ok", rowCount=len(rows))
        return doc_stats, rows

    async def delete_document(self, doc_id: str) -> list[str]:
        """Delete a document and its chunks. Returns IDs for vector cleanup."""
        self._log.debug_log("d1.delete_document", docId=doc_id)
        chunks_result = await self._db.prepare(
            "SELECT id FROM documents WHERE id = ? OR parent_id = ?"
        ).bind(doc_id, doc_id).all()

        ids: list[str] = []
        if chunks_result and chunks_result.results:
            for i in range(chunks_result.results.length):
                ids.append(str(chunks_result.results[i].id))

        if ids:
            self._log.debug_log("d1.delete_document.found", chunkIds=ids)
            await self._db.prepare(
                "DELETE FROM documents WHERE id = ? OR parent_id = ?"
            ).bind(doc_id, doc_id).run()
            self._log.debug_log("d1.delete_document.ok")

        return ids

    async def get_doc_stats(self) -> DocStats | None:
        """Fetch corpus-level statistics."""
        self._log.debug_log("d1.get_doc_stats")
        row = await self._db.prepare(
            "SELECT total_documents, avg_doc_length FROM doc_stats WHERE id = 1"
        ).first()
        if not row:
            return None
        return DocStats(
            total_documents=int(row.total_documents),
            avg_doc_length=float(row.avg_doc_length),
        )

    async def document_exists(self, doc_id: str) -> bool:
        """Check if a document or chunk exists."""
        self._log.debug_log("d1.document_exists", docId=doc_id)
        row = await self._db.prepare(
            "SELECT id FROM documents WHERE id = ? OR parent_id = ?"
        ).bind(doc_id, doc_id).first()
        return row is not None


class CloudflareD1LicenseStore:
    """Implements LicenseStore protocol using env.DB (D1)."""

    def __init__(self, db_binding: JsProxy, logger: RequestLogger | None = None) -> None:
        self._db = db_binding
        self._log = logger or noop_logger()

    async def validate(self, license_key: str) -> License | None:
        """Validate a license key. Returns License if active, None otherwise."""
        self._log.debug_log("d1.license.validate", keyPrefix=license_key[:8])
        row = await self._db.prepare(
            "SELECT * FROM licenses WHERE license_key = ? AND is_active = 1"
        ).bind(license_key).first()

        if not row:
            return None

        return License(
            license_key=str(row.license_key),
            email=str(row.email) if row.email else None,
            plan=str(row.plan),
            max_documents=int(row.max_documents),
            max_queries_per_day=int(row.max_queries_per_day),
            created_at=str(row.created_at) if row.created_at else None,
            is_active=True,
        )

    async def create(
        self,
        email: str,
        plan: str = "standard",
        max_documents: int | None = None,
        max_queries_per_day: int | None = None,
    ) -> License:
        """Create a new license with a generated key."""
        license_key = f"lic_{uuid.uuid4().hex}"
        self._log.debug_log("d1.license.create", email=email, plan=plan)

        if max_documents is None:
            max_documents = {"enterprise": 100000, "pro": 50000}.get(plan, 10000)
        if max_queries_per_day is None:
            max_queries_per_day = {"enterprise": 10000, "pro": 5000}.get(plan, 1000)

        await self._db.prepare(
            "INSERT INTO licenses (license_key, email, plan, max_documents, max_queries_per_day) "
            "VALUES (?, ?, ?, ?, ?)"
        ).bind(license_key, email, plan, max_documents, max_queries_per_day).run()

        self._log.debug_log("d1.license.created", keyPrefix=license_key[:8])
        return License(
            license_key=license_key,
            email=email,
            plan=plan,
            max_documents=max_documents,
            max_queries_per_day=max_queries_per_day,
        )

    async def list_all(self, limit: int = 100) -> list[License]:
        """List all licenses ordered by creation date descending."""
        self._log.debug_log("d1.license.list_all", limit=limit)
        result = await self._db.prepare(
            "SELECT license_key, email, plan, max_documents, max_queries_per_day, "
            "created_at, is_active FROM licenses ORDER BY created_at DESC LIMIT ?"
        ).bind(limit).all()

        licenses: list[License] = []
        if result and result.results:
            for i in range(result.results.length):
                r = result.results[i]
                licenses.append(License(
                    license_key=str(r.license_key),
                    email=str(r.email) if r.email else None,
                    plan=str(r.plan),
                    max_documents=int(r.max_documents),
                    max_queries_per_day=int(r.max_queries_per_day),
                    created_at=str(r.created_at) if r.created_at else None,
                    is_active=bool(r.is_active),
                ))

        return licenses

    async def revoke(self, license_key: str) -> bool:
        """Revoke a license by setting is_active = 0."""
        self._log.debug_log("d1.license.revoke", keyPrefix=license_key[:8])
        await self._db.prepare(
            "UPDATE licenses SET is_active = 0 WHERE license_key = ?"
        ).bind(license_key).run()
        return True
