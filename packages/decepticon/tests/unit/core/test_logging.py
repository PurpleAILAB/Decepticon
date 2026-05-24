"""Unit tests for decepticon_core.utils.logging."""

from __future__ import annotations

import io
import json
import logging

import pytest

# Import the canonical module directly (not the decepticon.core.logging
# shim): this test mutates + asserts module-level state (``_CONFIGURED``),
# and the PEP 562 shim delegates attribute reads but keeps its own module
# object, so shim-vs-canonical state would diverge.
from decepticon_core.utils import logging as dlog


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset the decepticon root logger between tests."""
    yield
    root = logging.getLogger("decepticon")
    for h in list(root.handlers):
        root.removeHandler(h)
    dlog._CONFIGURED = False  # type: ignore[attr-defined]


def _capture(level: str | int = "INFO", fmt: str = "text") -> io.StringIO:
    buf = io.StringIO()
    dlog.configure_logging(level=level, fmt=fmt)
    handler = logging.getLogger("decepticon").handlers[0]
    handler.stream = buf
    return buf


class TestGetLogger:
    def test_namespaces_under_decepticon(self) -> None:
        log = dlog.get_logger("auth.manager")
        assert log.name == "decepticon.auth.manager"

    def test_auto_configures_on_first_use(self) -> None:
        dlog._CONFIGURED = False  # type: ignore[attr-defined]
        log = dlog.get_logger("module")
        assert dlog._CONFIGURED is True  # type: ignore[attr-defined]
        assert logging.getLogger("decepticon").handlers, "handler should be installed"
        del log


class TestTextFormat:
    def test_text_output_contains_message(self) -> None:
        buf = _capture(fmt="text")
        log = dlog.get_logger("test")
        log.info("hello world")
        out = buf.getvalue()
        assert "hello world" in out
        assert "INFO" in out
        assert "decepticon.test" in out


class TestJsonFormat:
    def test_json_output_is_parseable(self) -> None:
        buf = _capture(fmt="json")
        log = dlog.get_logger("test")
        log.info("structured log")
        line = buf.getvalue().strip().splitlines()[-1]
        record = json.loads(line)
        assert record["msg"] == "structured log"
        assert record["level"] == "INFO"
        assert record["logger"] == "decepticon.test"
        assert "ts" in record

    def test_json_includes_extra_fields(self) -> None:
        buf = _capture(fmt="json")
        log = dlog.get_logger("test")
        log.info("with extras", extra={"user": "alice", "request_id": "abc-123"})
        line = buf.getvalue().strip().splitlines()[-1]
        record = json.loads(line)
        assert record["user"] == "alice"
        assert record["request_id"] == "abc-123"

    def test_json_renders_exception(self) -> None:
        buf = _capture(fmt="json")
        log = dlog.get_logger("test")
        try:
            raise ValueError("boom")
        except ValueError:
            log.exception("oops")
        line = buf.getvalue().strip().splitlines()[-1]
        record = json.loads(line)
        assert "exc_info" in record
        assert "ValueError" in record["exc_info"]
        assert "boom" in record["exc_info"]

    def test_json_falls_back_for_unserializable(self) -> None:
        buf = _capture(fmt="json")
        log = dlog.get_logger("test")

        class NotSerializable:
            def __repr__(self) -> str:
                return "<NotSerializable>"

        log.info("non-json extra", extra={"obj": NotSerializable()})
        line = buf.getvalue().strip().splitlines()[-1]
        record = json.loads(line)
        assert record["obj"] == "<NotSerializable>"


class TestConfigureLogging:
    def test_idempotent_replaces_handler(self) -> None:
        dlog.configure_logging(fmt="text")
        root = logging.getLogger("decepticon")
        assert len(root.handlers) == 1
        dlog.configure_logging(fmt="json")
        assert len(root.handlers) == 1  # replaced, not appended

    def test_respects_level(self) -> None:
        dlog.configure_logging(level="WARNING", fmt="text")
        root = logging.getLogger("decepticon")
        assert root.level == logging.WARNING

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_LOG_FORMAT", "json")
        monkeypatch.setenv("DECEPTICON_LOG_LEVEL", "DEBUG")
        dlog.configure_logging()
        root = logging.getLogger("decepticon")
        assert root.level == logging.DEBUG
        from decepticon_core.utils.logging import _JsonFormatter

        assert isinstance(root.handlers[0].formatter, _JsonFormatter)
