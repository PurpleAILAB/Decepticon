"""OpenTelemetry span helpers — no-op fallback when OTel isn't installed.

The agent code calls :func:`span` as a context manager. If the
``opentelemetry-api`` package is present and a tracer provider is
configured, real spans flow to the registered exporter. Otherwise we
fall back to a zero-cost no-op so nothing needs to change.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    from opentelemetry import trace as _ot_trace  # type: ignore[import]

    _OTEL_AVAILABLE = True
    _TRACER = _ot_trace.get_tracer("decepticon")
except Exception:
    _OTEL_AVAILABLE = False
    _TRACER = None


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, kv: dict[str, Any]) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Enter an OTel span (real or no-op) with initial attributes."""
    if _OTEL_AVAILABLE and _TRACER is not None:
        with _TRACER.start_as_current_span(name) as s:
            for k, v in attributes.items():
                try:
                    s.set_attribute(k, v)
                except Exception:
                    pass  # tracing unavailable — continue without telemetry
            yield s
    else:
        noop = _NoopSpan()
        for k, v in attributes.items():
            _ = k, v  # silence unused
        yield noop
