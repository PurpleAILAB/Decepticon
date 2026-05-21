# Decepticon Grafana Dashboards

Auto-provisioned via `dashboards.yaml`. All dashboards read from the
Prometheus datasource (UID: `prometheus`) populated by the OTel Collector.

| File | Title | Purpose |
|---|---|---|
| `01-engagement-overview.json` | Engagement Overview | Top-level KPIs: tool calls, dispatches, validity ratio, LLM spend |
| `02-tool-call-detail.json` | Tool-Call Forensics | Per-tool rate, p95 latency, error rate, top-10 piechart |
| `03-llm-cost.json` | LLM Cost Ledger | Cost per finding, per model, per agent. Critical for benchmark optimization |
| `04-vaccine-pipeline.json` | Vaccine Pipeline Flow | Funnel: validated → patched → defended → shipped + dwell time |
| `05-agent-handoffs.json` | Agent Handoff Topology | Per-edge dispatch counts, per-agent latency p50/p95 |

## Variables

All dashboards expose an `${engagement}` template variable populated from
`label_values(decepticon_tool_calls_total, engagement)`. Default `All`.
Dashboards `02` adds `${agent}` (multi-select).

## Metric Names

Canonical metric names + labels are defined in
[`decepticon/core/metrics.py`](../../../../decepticon/core/metrics.py).
Do NOT edit dashboard PromQL without updating `metrics.py` to match.

## Adding a new dashboard

1. Drop a `NN-name.json` file in this directory
2. Use `prometheus` as the datasource UID
3. Reference metrics from `decepticon/core/metrics.py` — don't invent names
4. Include `${engagement}` template variable for filterability
5. Set `schemaVersion: 38` (Grafana 10+)
6. Commit + restart grafana service: `docker compose -f containers/observability/docker-compose.observability.yml restart grafana`
