"""OpenTelemetry instrumentation for Decepticon agents.

Lightweight wrapper around the opentelemetry-sdk + OTLP HTTP exporter.
Agents call ``setup_telemetry(service_name)`` once at startup to:
- Configure tracer + meter w/ Decepticon-standard resource attributes
- Auto-export to ``OTEL_EXPORTER_OTLP_ENDPOINT`` (default
  http://otel-collector:4318 inside the decepticon-net Docker network)

When the OTel stack isn't running (e.g. operator hasn't started the
observability compose), this module degrades silently — exporters fail
their first send and back off; agents continue to work normally.

The instrumentation focuses on three signals Decepticon engineers actually
need for performance + benchmark optimization:

1. **Per-agent latency span** — every sub-agent dispatch is a span,
   tagged with agent name, engagement slug, target, tool count.
2. **Per-tool-call counter** — counts tool invocations by tool name.
   Highlights which tools dominate engagement cost.
3. **Per-finding outcome counter** — counts findings by status (passed,
   blocked, false_positive). Drives validity-ratio metrics.

For Langfuse-specific LLM tracing (token cost, prompt evaluation), see
``decepticon/core/langfuse_setup.py`` — Langfuse runs alongside OTel as
a complement (Langfuse for LLM-specific; OTel for generic infra).
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

_DEFAULT_OTLP_ENDPOINT = "http://otel-collector:4318"
_SERVICE_NAME_PREFIX = "decepticon-"

# Lazily-initialized — only import opentelemetry when setup_telemetry() runs,
# so importing this module does NOT add deps for users w/o OTel installed.
_tracer: Any = None
_meter: Any = None
_initialized = False


def setup_telemetry(
    service_name: str,
    *,
    endpoint: str | None = None,
    engagement_slug: str | None = None,
) -> bool:
    """Initialize OTel tracer + meter for an agent.

    Idempotent — repeated calls are no-ops.

    Args:
        service_name: Agent identifier (e.g. "decepticon", "recon", "exploit").
            Prefixed with "decepticon-" if not already.
        endpoint: OTLP HTTP endpoint. Default reads from
            OTEL_EXPORTER_OTLP_ENDPOINT env or falls back to otel-collector:4318.
        engagement_slug: Active engagement identifier (e.g. "xben-058"
            or "acme-corp-q2"). Tagged as a resource attribute for
            per-engagement filtering in Grafana.

    Returns:
        True if telemetry was initialized; False if dependencies are
        missing (opentelemetry-sdk not installed) or initialization
        failed silently — caller should not assume metrics are flowing.
    """
    global _tracer, _meter, _initialized
    if _initialized:
        return True

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.info(
            "opentelemetry-sdk not installed; telemetry disabled. "
            "Install: pip install opentelemetry-sdk opentelemetry-exporter-otlp"
        )
        return False

    if not service_name.startswith(_SERVICE_NAME_PREFIX):
        service_name = _SERVICE_NAME_PREFIX + service_name

    endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_OTLP_ENDPOINT)
    resource_attrs = {
        "service.name": service_name,
        "deployment.environment": os.getenv("DEPLOYMENT_ENV", "engagement"),
    }
    if engagement_slug:
        resource_attrs["decepticon.engagement"] = engagement_slug

    resource = Resource.create(resource_attrs)

    # Traces
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(service_name)

    # Metrics
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
                export_interval_millis=10_000,
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(service_name)

    _initialized = True
    logger.info(f"telemetry initialized: service={service_name} endpoint={endpoint}")
    return True


@contextmanager
def span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Trace one operation. Use as a context manager.

    Example:
        with span("recon_dispatch", target="example.com", tool_count=12):
            run_recon(...)

    Falls back to a null context if telemetry isn't initialized.
    """
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name, attributes=attributes) as s:
        yield s


def counter(name: str, description: str = "", unit: str = "1") -> Any:
    """Create or return a Prometheus-style counter.

    Returns a no-op shim if telemetry isn't initialized.
    """
    if _meter is None:
        return _NoOpInstrument()
    return _meter.create_counter(name, unit=unit, description=description)


def histogram(name: str, description: str = "", unit: str = "ms") -> Any:
    """Create or return a histogram metric."""
    if _meter is None:
        return _NoOpInstrument()
    return _meter.create_histogram(name, unit=unit, description=description)


class _NoOpInstrument:
    """No-op replacement when telemetry isn't initialized."""

    def add(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def record(self, *_args: Any, **_kwargs: Any) -> None:
        pass


__all__ = ["counter", "histogram", "setup_telemetry", "span"]
