"""Structured logging for Cloudflare Python Workers.

All output goes to stdout via print(), captured by ``wrangler tail --format=json``.
Each request gets a unique **trace ID** so you can follow a single request across
all log lines.

Toggle verbose debug logging with the ``DEBUG_LOGGING`` env var::

    # via wrangler secret (persistent)
    wrangler secret put DEBUG_LOGGING      # enter "true"

    # or via wrangler.toml [vars] (committed)
    [vars]
    DEBUG_LOGGING = "true"
"""

from __future__ import annotations

import json
import traceback
import uuid


class RequestLogger:
    """Request-scoped structured logger with trace ID.

    Every log entry is a JSON object printed to stdout, which ``wrangler tail
    --format=json`` captures alongside the Worker's console output.

    Usage::

        log = RequestLogger(debug=True)
        log.info("request started", endpoint="/search", method="POST")
        log.debug_log("Embedding generated", dimensions=384)
        log.error("D1 query failed", exc=some_exception, sql=query)
    """

    def __init__(self, debug: bool = False, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex[:12]
        self.debug = debug

    def _emit(self, level: str, message: str, **extra: object) -> None:
        """Emit a single structured JSON log line."""
        entry: dict[str, object] = {
            "level": level,
            "traceId": self.trace_id,
            "msg": message,
        }
        if extra:
            entry.update(extra)
        # default=str handles non-serialisable types (bytes, etc.)
        print(json.dumps(entry, default=str))

    # ── public API ────────────────────────────────────────────────────

    def info(self, message: str, **extra: object) -> None:
        """Always emitted. Key operational events."""
        self._emit("INFO", message, **extra)

    def warn(self, message: str, **extra: object) -> None:
        """Always emitted. Degraded-but-recoverable situations."""
        self._emit("WARN", message, **extra)

    def error(self, message: str, exc: BaseException | None = None, **extra: object) -> None:
        """Always emitted. Includes full traceback when *exc* is provided."""
        if exc is not None:
            extra["error"] = str(exc)
            extra["errorType"] = type(exc).__name__
            extra["traceback"] = "".join(traceback.format_exception(exc))
        self._emit("ERROR", message, **extra)

    def debug_log(self, message: str, **extra: object) -> None:
        """Only emitted when ``DEBUG_LOGGING`` is enabled."""
        if self.debug:
            self._emit("DEBUG", message, **extra)


# ── module-level helpers ──────────────────────────────────────────────

_NOOP: RequestLogger | None = None


def noop_logger() -> RequestLogger:
    """Return a shared silent logger (debug=False, fixed traceId='noop')."""
    global _NOOP  # noqa: PLW0603
    if _NOOP is None:
        _NOOP = RequestLogger(debug=False, trace_id="noop")
    return _NOOP
