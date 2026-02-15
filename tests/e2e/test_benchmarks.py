"""E2E benchmark tests -- measure response times and detect regressions.

Requires:
    VECTORIZE_E2E_URL=https://your-worker.workers.dev
    VECTORIZE_E2E_API_KEY=your-api-key

Run with:
    pytest tests/e2e/test_benchmarks.py -m benchmark -v
"""

from __future__ import annotations

import time
import uuid

import pytest

from tests.e2e.benchmark_store import BenchmarkEntry, print_report, record

# Number of iterations per operation for benchmarking
ITERATIONS = 3


def _measure(func):
    """Async decorator that measures execution time in ms."""

    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return result, elapsed_ms

    return wrapper


@pytest.mark.benchmark
@pytest.mark.e2e
class TestBenchmarks:
    """Benchmark each major operation and compare to historical baselines."""

    @pytest.mark.asyncio
    async def test_benchmark_health(self, e2e_client) -> None:
        entries = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            await e2e_client.health()
            elapsed = (time.perf_counter() - start) * 1000
            entries.append(BenchmarkEntry(operation="health", duration_ms=elapsed))

        reports = record(entries)
        print_report(reports)
        regressions = [r for r in reports if r.regression]
        assert not regressions, f"Regression in health: {regressions}"

    @pytest.mark.asyncio
    async def test_benchmark_stats(self, e2e_client) -> None:
        entries = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            await e2e_client.stats()
            elapsed = (time.perf_counter() - start) * 1000
            entries.append(BenchmarkEntry(operation="stats", duration_ms=elapsed))

        reports = record(entries)
        print_report(reports)
        regressions = [r for r in reports if r.regression]
        assert not regressions, f"Regression in stats: {regressions}"

    @pytest.mark.asyncio
    async def test_benchmark_search(self, e2e_client) -> None:
        entries = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            await e2e_client.search_documents("benchmark test query", top_k=5)
            elapsed = (time.perf_counter() - start) * 1000
            entries.append(BenchmarkEntry(operation="search_documents", duration_ms=elapsed))

        reports = record(entries)
        print_report(reports)
        regressions = [r for r in reports if r.regression]
        assert not regressions, f"Regression in search: {regressions}"

    @pytest.mark.asyncio
    async def test_benchmark_ingest_delete(self, e2e_client) -> None:
        """Benchmark document ingest and deletion."""
        ingest_entries = []
        delete_entries = []
        doc_ids = []

        for i in range(ITERATIONS):
            doc_id = f"bench-{uuid.uuid4().hex[:8]}"
            doc_ids.append(doc_id)

            # Benchmark ingest
            start = time.perf_counter()
            await e2e_client.ingest(
                doc_id,
                f"Benchmark document {i} about distributed systems and consensus algorithms.",
                category="benchmark",
            )
            elapsed = (time.perf_counter() - start) * 1000
            ingest_entries.append(BenchmarkEntry(operation="ingest", duration_ms=elapsed))

        # Benchmark delete
        for doc_id in doc_ids:
            start = time.perf_counter()
            try:
                await e2e_client.delete(doc_id)
            except Exception:
                pass
            elapsed = (time.perf_counter() - start) * 1000
            delete_entries.append(BenchmarkEntry(operation="delete", duration_ms=elapsed))

        all_entries = ingest_entries + delete_entries
        reports = record(all_entries)
        print_report(reports)
        regressions = [r for r in reports if r.regression]
        assert not regressions, f"Regressions: {regressions}"

    @pytest.mark.asyncio
    async def test_benchmark_list_documents(self, e2e_client) -> None:
        entries = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            await e2e_client.list_documents(limit=10)
            elapsed = (time.perf_counter() - start) * 1000
            entries.append(BenchmarkEntry(operation="list_documents", duration_ms=elapsed))

        reports = record(entries)
        print_report(reports)
        regressions = [r for r in reports if r.regression]
        assert not regressions, f"Regression in list: {regressions}"
