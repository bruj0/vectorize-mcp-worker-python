"""Tests for the structured logger."""

from __future__ import annotations

import json

import pytest

from src.logger import RequestLogger, noop_logger


class TestRequestLogger:
    def test_trace_id_auto_generated(self) -> None:
        log = RequestLogger()
        assert len(log.trace_id) == 12

    def test_trace_id_custom(self) -> None:
        log = RequestLogger(trace_id="custom-123")
        assert log.trace_id == "custom-123"

    def test_info_emits(self, capsys: pytest.CaptureFixture) -> None:
        log = RequestLogger(trace_id="t1")
        log.info("test.event", key="val")
        captured = capsys.readouterr()
        entry = json.loads(captured.out)
        assert entry["level"] == "INFO"
        assert entry["msg"] == "test.event"
        assert entry["traceId"] == "t1"
        assert entry["key"] == "val"

    def test_warn_emits(self, capsys: pytest.CaptureFixture) -> None:
        log = RequestLogger(trace_id="t2")
        log.warn("bad.thing")
        captured = capsys.readouterr()
        entry = json.loads(captured.out)
        assert entry["level"] == "WARN"

    def test_error_with_exception(self, capsys: pytest.CaptureFixture) -> None:
        log = RequestLogger(trace_id="t3")
        try:
            raise ValueError("boom")
        except ValueError as exc:
            log.error("err.event", exc=exc)
        captured = capsys.readouterr()
        entry = json.loads(captured.out)
        assert entry["level"] == "ERROR"
        assert entry["error"] == "boom"
        assert entry["errorType"] == "ValueError"
        assert "traceback" in entry

    def test_debug_suppressed_by_default(self, capsys: pytest.CaptureFixture) -> None:
        log = RequestLogger(debug=False)
        log.debug_log("should.not.appear")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_debug_enabled(self, capsys: pytest.CaptureFixture) -> None:
        log = RequestLogger(debug=True, trace_id="t4")
        log.debug_log("visible.debug")
        captured = capsys.readouterr()
        entry = json.loads(captured.out)
        assert entry["level"] == "DEBUG"


class TestNoopLogger:
    def test_singleton(self) -> None:
        a = noop_logger()
        b = noop_logger()
        assert a is b

    def test_no_output(self, capsys: pytest.CaptureFixture) -> None:
        log = noop_logger()
        log.info("should.emit")
        # noop_logger has debug=False, but info always emits
        captured = capsys.readouterr()
        assert captured.out != ""  # info still emits

    def test_debug_suppressed(self, capsys: pytest.CaptureFixture) -> None:
        log = noop_logger()
        log.debug_log("suppressed")
        captured = capsys.readouterr()
        assert captured.out == ""
