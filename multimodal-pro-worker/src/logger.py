"""Structured logging for the multimodal-pro-worker.

Identical API to the main worker's logger -- JSON lines to stdout,
per-request trace IDs, debug toggle via DEBUG_LOGGING env var.
"""

from __future__ import annotations

import json
import traceback
import uuid


class RequestLogger:
    """Request-scoped structured logger with trace ID."""

    def __init__(self, debug: bool = False, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex[:12]
        self.debug = debug

    def _emit(self, level: str, message: str, **extra: object) -> None:
        entry: dict[str, object] = {
            "level": level,
            "traceId": self.trace_id,
            "msg": message,
        }
        if extra:
            entry.update(extra)
        print(json.dumps(entry, default=str))

    def info(self, message: str, **extra: object) -> None:
        self._emit("INFO", message, **extra)

    def warn(self, message: str, **extra: object) -> None:
        self._emit("WARN", message, **extra)

    def error(self, message: str, exc: BaseException | None = None, **extra: object) -> None:
        if exc is not None:
            extra["error"] = str(exc)
            extra["errorType"] = type(exc).__name__
            extra["traceback"] = "".join(traceback.format_exception(exc))
        self._emit("ERROR", message, **extra)

    def debug_log(self, message: str, **extra: object) -> None:
        if self.debug:
            self._emit("DEBUG", message, **extra)
