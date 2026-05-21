# Observability — Langfuse + OpenTelemetry stack

## Overview

Decepticon ships an opt-in observability stack that gives operators
per-engagement visibility into agent latency, token cost, tool-call
frequency, and finding outcome rates. The stack is a separate
`docker-compose-observability.yml` overlay — start it alongside the
main `docker-compose.yml` when needed; skip it when running lightweight
or on constrained hosts.

## Why

Without observability, operators are blind to:
- **Which agent dominates engagement cost?** (Token + wall-clock)
- **Which tool calls fail most?** (Recon failures? AD auth retries?)
- **What's the per-engagement validity ratio?** (Findings/total)
- **Which sub-agent loop is killing the benchmark?**
- **Where does the engagement actually spend its time?**

These are the questions that drive XBEN optimization, cost reduction,
and customer-facing SLAs. Observability is the first step toward all of
them.

## Stack components

| Component | Purpose | Port |
|---|---|---|
| **Langfuse** | LLM-specific tracing (prompt, completion, cost, eval) | 3700 |
| **Postgres (langfuse-db)** | Langfuse metadata storage | internal |
| **ClickHouse** | Analytics column store for Langfuse v3+ | internal |
| **OTel Collector** | Receives + processes OTLP traces/metrics from agents | 4317/4318/8889 |
| **Prometheus** | Metrics store + alerting | 9090 |
| **Grafana** | Dashboards + visualization | 3701 |
| **Jaeger** | Distributed trace storage + UI | 3702 |

Idle footprint: ~2.5 GB RAM. Engagement load: ~5 GB RAM.

## Quick start

```bash
# 1. Set required env vars (or use defaults from docker-compose.observability.yml)
cat >> ~/.decepticon/.env <<'EOF'
LANGFUSE_DB_PASSWORD=$(openssl rand -hex 16)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_SALT=$(openssl rand -hex 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)
CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 16)
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
EOF

# 2. Start the observability stack
docker compose \
  -f docker-compose.yml \
  -f containers/observability/docker-compose.observability.yml \
  up -d

# Or via Makefile shortcut (if added):
make obs-up

# 3. Confirm health
docker compose ps | grep -E 'langfuse|otel-collector|grafana|prometheus|jaeger'
# All should show "healthy" or "running"

# 4. Open the dashboards
xdg-open http://localhost:3701  # Grafana (admin / $GRAFANA_ADMIN_PASSWORD)
xdg-open http://localhost:3700  # Langfuse (admin@decepticon.local / $LANGFUSE_INIT_USER_PASSWORD)
xdg-open http://localhost:3702  # Jaeger UI
xdg-open http://localhost:9090  # Prometheus (no auth)
```

## Agent instrumentation

Agents emit telemetry via `decepticon.core.telemetry`:

```python
from decepticon.core.telemetry import setup_telemetry, span, counter

# At agent startup
setup_telemetry("recon", engagement_slug=engagement.slug)

# Per tool call
TOOL_CALLS = counter("decepticon.tool.calls", description="Tool invocations by name")

with span("recon_sweep", target=target, wordlist=wordlist_name):
    result = run_recon(...)
    TOOL_CALLS.add(1, attributes={"tool": "nmap", "agent": "recon"})
```

The `setup_telemetry()` call is **idempotent + safe** when the OTel
stack isn't running — exporters silently fail their first send and
back off. Agents continue to work normally without the stack.

## Dashboards

Pre-provisioned Grafana dashboards (loaded from
`grafana-provisioning/dashboards/`):

| Dashboard | Shows |
|---|---|
| `decepticon-overview` | Per-engagement summary: cost, latency p50/p95/p99, finding count, success rate |
| `decepticon-agents` | Per-sub-agent breakdown: dispatches, latency, error rate |
| `decepticon-tools` | Tool-call frequency + duration heatmap |
| `decepticon-findings` | Findings by stage (Scanner → Detector → Verifier → Patcher → Defender), validity ratio |
| `decepticon-vaccine` | Vaccine pipeline funnel: validated → patched → defended → shipped |

Dashboards are JSON files in `containers/observability/grafana-provisioning/dashboards/`.

## Langfuse LLM tracing

Langfuse handles LLM-specific signals OTel doesn't natively model:
- Prompt + completion text (when not redacted)
- Token cost per model per call
- Eval scores (when running eval suites via promptfoo)
- Prompt-version tracking
- User feedback annotations on traces

Decepticon's `decepticon/llm/factory.py` initializes Langfuse via
LiteLLM's built-in Langfuse integration when `LANGFUSE_PUBLIC_KEY` +
`LANGFUSE_SECRET_KEY` are set in the env. Both keys are generated in
the Langfuse web UI (Project → Settings → API Keys) after first login.

```bash
# After Langfuse first boot — generate keys via UI, then:
echo "LANGFUSE_PUBLIC_KEY=pk-lf-..." >> ~/.decepticon/.env
echo "LANGFUSE_SECRET_KEY=sk-lf-..." >> ~/.decepticon/.env
echo "LANGFUSE_HOST=http://langfuse:3000" >> ~/.decepticon/.env  # internal container reach
docker compose restart litellm langgraph
```

## Constrained-host mode

If the host can't afford 5 GB observability overhead, comment out
clickhouse + jaeger in `docker-compose.observability.yml` and run
with just langfuse + prometheus + grafana. That drops idle to ~1 GB
but disables ClickHouse-backed Langfuse analytics features (still
get traces + cost-per-call, just no aggregate analytics).

## Wipe + reset

```bash
# Stop + remove
docker compose -f containers/observability/docker-compose.observability.yml down

# Wipe stored data (Langfuse DB, ClickHouse, Prometheus TSDB, Grafana settings)
docker volume rm $(docker volume ls -q | grep '^decepticon_obs-')
```

## Source attribution

- Langfuse: https://github.com/langfuse/langfuse (MIT)
- OTel Collector + SDK: https://opentelemetry.io (Apache-2.0)
- Prometheus: https://prometheus.io (Apache-2.0)
- Grafana: https://grafana.com (AGPL-3.0 for OSS, custom commercial license available)
- Jaeger: https://jaegertracing.io (Apache-2.0)

PentAGI (vxcontrol/pentagi) provided the integration-pattern reference for combining Langfuse + Grafana + Jaeger in a multi-agent stack. CAI by Alias Robotics provided the Phoenix-style LLM observability pattern. Both were studied in the 18-repo survey before designing this stack.
