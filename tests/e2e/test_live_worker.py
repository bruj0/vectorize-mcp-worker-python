"""E2E tests against a live deployed worker.

Requires:
    VECTORIZE_E2E_URL=https://your-worker.workers.dev
    VECTORIZE_E2E_API_KEY=your-api-key

Each test is self-contained and cleans up after itself.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.e2e
class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, e2e_client) -> None:
        result = await e2e_client.health()
        assert result["status"] == "healthy"
        assert "bindings" in result


@pytest.mark.e2e
class TestStats:
    @pytest.mark.asyncio
    async def test_stats_endpoint(self, e2e_client) -> None:
        result = await e2e_client.stats()
        assert "index" in result
        assert "documents" in result


@pytest.mark.e2e
class TestDocumentLifecycle:
    """Full document lifecycle: ingest -> search -> get -> delete."""

    @pytest.mark.asyncio
    async def test_ingest_search_delete(self, e2e_client) -> None:
        doc_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
        content = "E2E test document about quantum computing and machine learning integration."

        try:
            # Ingest
            ingest_result = await e2e_client.ingest(
                doc_id, content, category="e2e-test", title="E2E Test Doc"
            )
            assert ingest_result.get("success") is True
            assert ingest_result.get("chunksCreated", 0) >= 1

            # Search
            search_result = await e2e_client.search_documents(
                "quantum computing", top_k=5
            )
            assert "results" in search_result

            # Get document
            get_result = await e2e_client.get_document(f"{doc_id}-chunk-0")
            assert get_result is not None

            # List documents
            list_result = await e2e_client.list_documents(limit=10)
            assert "documents" in list_result

        finally:
            # Cleanup
            try:
                await e2e_client.delete(doc_id)
            except Exception:
                pass


@pytest.mark.e2e
class TestLicenseLifecycle:
    """Full license lifecycle: create -> validate -> list -> revoke -> delete."""

    @pytest.mark.asyncio
    async def test_license_crud(self, e2e_client) -> None:
        email = f"e2e-{uuid.uuid4().hex[:8]}@test.com"
        license_key = None

        try:
            # Create
            create_result = await e2e_client.license_create(email)
            assert create_result.get("success") is True
            license_key = create_result.get("license_key")
            assert license_key is not None

            # Validate
            validate_result = await e2e_client.license_validate(license_key)
            assert validate_result.get("valid") is True

            # List
            list_result = await e2e_client.license_list()
            assert "licenses" in list_result

            # Revoke
            revoke_result = await e2e_client.license_revoke(license_key)
            assert revoke_result.get("success") is True

        finally:
            # Cleanup
            if license_key:
                try:
                    await e2e_client.delete_license(license_key)
                except Exception:
                    pass


@pytest.mark.e2e
class TestSearchOperations:
    @pytest.mark.asyncio
    async def test_multimodal_search(self, e2e_client) -> None:
        result = await e2e_client.search_multimodal("test query", top_k=3)
        assert "results" in result
        assert "performance" in result

    @pytest.mark.asyncio
    async def test_documents_search(self, e2e_client) -> None:
        result = await e2e_client.search_documents("test query", top_k=3)
        assert "results" in result

    @pytest.mark.asyncio
    async def test_search_with_rerank_off(self, e2e_client) -> None:
        result = await e2e_client.search_documents(
            "test query", top_k=3, rerank=False
        )
        assert "results" in result


