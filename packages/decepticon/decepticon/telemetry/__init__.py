"""Optional OpenTelemetry helpers for Decepticon.

Default off. When ``OTEL_ENABLED`` is set and the ``opentelemetry`` packages
are installed, helpers emit OTLP spans for engagement / agent / tool / LLM
activity. Otherwise every helper is a no-op so the library remains safe to
import in any process without the optional extra installed.
"""

from decepticon.telemetry.config import (
    TelemetryConfig,
    TelemetryMode,
    resolve_config,
    resolve_mode,
)
from decepticon.telemetry.otel import (
    init_otel,
    record_llm_cost,
    record_llm_token_usage,
    set_current_objective_id,
    start_agent_span,
    start_engagement_span,
    start_llm_span,
    start_tool_span,
)
from decepticon.telemetry.sink import TelemetrySink, get_sink

__all__ = [
    "TelemetryConfig",
    "TelemetryMode",
    "TelemetrySink",
    "get_sink",
    "init_otel",
    "record_llm_cost",
    "record_llm_token_usage",
    "resolve_config",
    "resolve_mode",
    "set_current_objective_id",
    "start_agent_span",
    "start_engagement_span",
    "start_llm_span",
    "start_tool_span",
]
