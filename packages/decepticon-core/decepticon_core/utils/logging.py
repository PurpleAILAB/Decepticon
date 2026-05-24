"""Decepticon logging — stdlib wrapper with optional structured JSON output.

Use plain text logs for local dev, JSON for production / containers / CI.
Toggle via env vars (read once at import / first ``configure_logging`` call):

    DECEPTICON_LOG_LEVEL    DEBUG | INFO (default) | WARNING | ERROR
    DECEPTICON_LOG_FORMAT   text (default) | json

JSON output is single-line per record so it can be ingested by Loki, Datadog,
ELK, etc. without further processing.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """Minimal structured JSON log formatter.

    Includes standard LogRecord fields plus any ``extra={...}`` keys passed
    by the caller. Exception info is rendered into the ``exc_info`` field.
    """

    _RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        # Pull caller-supplied extra fields
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    level: str | int | None = None,
    fmt: str | None = None,
) -> None:
    """Configure the root ``decepticon`` logger.

    Idempotent: calling twice replaces the prior handler so tests can
    reconfigure freely. Honors env vars when args are omitted.
    """
    global _CONFIGURED
    level = level or os.getenv("DECEPTICON_LOG_LEVEL", "INFO")
    fmt = (fmt or os.getenv("DECEPTICON_LOG_FORMAT", "text")).lower()

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    root = logging.getLogger("decepticon")
    # Replace any prior handlers we installed
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger for the given module.

    Auto-configures the root logger on first use.

    Usage::

        from decepticon_core.utils.logging import get_logger
        log = get_logger("auth.manager")
        log.info("something happened", extra={"user": "alice"})
    """
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(f"decepticon.{name}")
