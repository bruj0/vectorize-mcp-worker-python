"""Benchmark result storage and regression detection.

Persists benchmark results to tests/e2e/benchmark_results.json across runs.
Compares current results against historical baselines to detect regressions.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_RESULTS_FILE = Path(__file__).parent / "benchmark_results.json"

# Flag a regression if current p50 is >20% slower than historical p50
REGRESSION_THRESHOLD = 0.20


@dataclass
class BenchmarkEntry:
    """A single benchmark measurement."""

    operation: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class BenchmarkReport:
    """Comparison of current run vs historical baselines."""

    operation: str
    current_p50_ms: float
    current_p95_ms: float
    current_mean_ms: float
    historical_p50_ms: float | None
    regression: bool = False
    regression_pct: float = 0.0


def load_history() -> dict[str, list[dict[str, Any]]]:
    """Load historical benchmark results from disk."""
    if not _RESULTS_FILE.exists():
        return {}
    try:
        return json.loads(_RESULTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_history(data: dict[str, list[dict[str, Any]]]) -> None:
    """Save benchmark results to disk."""
    _RESULTS_FILE.write_text(json.dumps(data, indent=2))


def record(entries: list[BenchmarkEntry]) -> list[BenchmarkReport]:
    """Record benchmark entries and compare against history.

    Returns a list of BenchmarkReport with regression flags.
    """
    history = load_history()
    reports: list[BenchmarkReport] = []

    # Group entries by operation
    by_op: dict[str, list[float]] = {}
    for e in entries:
        by_op.setdefault(e.operation, []).append(e.duration_ms)

    for op, durations in by_op.items():
        # Calculate current stats
        p50 = statistics.median(durations)
        p95 = (
            sorted(durations)[int(len(durations) * 0.95)]
            if len(durations) >= 2
            else durations[0]
        )
        mean = statistics.mean(durations)

        # Load historical p50
        hist_entries = history.get(op, [])
        hist_p50 = None
        regression = False
        regression_pct = 0.0

        if hist_entries:
            hist_durations = [e["duration_ms"] for e in hist_entries[-50:]]  # Last 50
            if hist_durations:
                hist_p50 = statistics.median(hist_durations)
                if hist_p50 > 0:
                    regression_pct = (p50 - hist_p50) / hist_p50
                    regression = regression_pct > REGRESSION_THRESHOLD

        reports.append(BenchmarkReport(
            operation=op,
            current_p50_ms=round(p50, 1),
            current_p95_ms=round(p95, 1),
            current_mean_ms=round(mean, 1),
            historical_p50_ms=round(hist_p50, 1) if hist_p50 else None,
            regression=regression,
            regression_pct=round(regression_pct * 100, 1),
        ))

        # Append current entries to history
        for d in durations:
            history.setdefault(op, []).append({
                "duration_ms": round(d, 1),
                "timestamp": time.time(),
            })

        # Keep only last 200 entries per operation
        if len(history.get(op, [])) > 200:
            history[op] = history[op][-200:]

    save_history(history)
    return reports


def print_report(reports: list[BenchmarkReport]) -> None:
    """Print a formatted benchmark report to stdout."""
    print("\n" + "=" * 70)
    print("BENCHMARK REPORT")
    print("=" * 70)
    for r in reports:
        status = "REGRESSION" if r.regression else "OK"
        hist = f"{r.historical_p50_ms}ms" if r.historical_p50_ms else "N/A"
        delta = f" ({r.regression_pct:+.1f}%)" if r.historical_p50_ms else ""
        print(
            f"  {r.operation:<25} "
            f"p50={r.current_p50_ms:>7.1f}ms  "
            f"p95={r.current_p95_ms:>7.1f}ms  "
            f"mean={r.current_mean_ms:>7.1f}ms  "
            f"hist={hist:>10}{delta}  [{status}]"
        )
    print("=" * 70 + "\n")

    regressions = [r for r in reports if r.regression]
    if regressions:
        print(f"WARNING: {len(regressions)} regression(s) detected!")
        for r in regressions:
            print(f"  - {r.operation}: {r.regression_pct:+.1f}% slower")
