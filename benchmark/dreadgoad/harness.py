"""Single-run execution: provision lab -> invoke LangGraph agent -> capture
artifacts -> teardown.

For ``lab_mode="isolated"`` the provision/teardown pair is invoked as a
try/finally so a mid-invocation exception (network glitch, LangGraph
crash) cannot leave cloud resources running.

For ``lab_mode="shared"`` the lab is provisioned once at the grid level
by the runner; ``run_one`` is called with that ``shared_provision`` and
must NOT teardown — the runner does it after the whole grid.

``pull_measurement_record`` is a module-level function so tests can
patch it without monkey-patching internals.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from benchmark.dreadgoad.providers.base import BaseBenchmarkProvider
from benchmark.dreadgoad.schemas import (
    BenchmarkConfig,
    ProvisionResult,
    RunResult,
    Scenario,
)

log = logging.getLogger(__name__)

# Sandbox container name — overridable for tests / non-docker setups.
# Defaults to the OSS Decepticon compose name; override via
# ``DECEPTICON_SANDBOX_CONTAINER`` when running outside the standard stack.
_SANDBOX_CONTAINER = os.environ.get("DECEPTICON_SANDBOX_CONTAINER", "decepticon-sandbox")
_SANDBOX_READ_TIMEOUT_S = 10

# LiteLLM proxy admin endpoints for offline cost attribution. The harness
# runs on the controller host where compose maps litellm to localhost on
# ``LITELLM_PORT``; override via ``DECEPTICON_LITELLM_URL`` +
# ``LITELLM_MASTER_KEY`` for non-docker test runs. When the env vars are
# unset, ``_compute_window_cost`` returns ``("time_window_unavailable", 0,
# {})`` and the run still completes — cost reporting is best-effort.
_LITELLM_URL = os.environ.get(
    "DECEPTICON_LITELLM_URL",
    # 4000 matches docker-compose.yml's host mapping (127.0.0.1:${LITELLM_PORT:-4000})
    f"http://127.0.0.1:{os.environ.get('LITELLM_PORT', '4000')}",
)
_LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

# Per-1M-token pricing for the model aliases configured by the OSS
# LiteLLM proxy (``config/litellm.yaml``). Extend with the provider/model
# combinations your config wires up. Unknown models contribute 0 to the
# total — the breakdown still reports them so the operator notices.
_MODEL_PRICES = {
    "anthropic/claude-opus-4-7": (15.0, 75.0),
    "anthropic/claude-sonnet-4-6": (3.0, 15.0),
    "anthropic/claude-haiku-4-5": (1.0, 5.0),
}


def _langsmith_trace_url(run_id: str) -> str:
    """Return a navigable LangSmith UI link for a given run/trace id.

    Tenant-scoped URL requires the workspace slug, which we don't know
    statically — fall back to the public deep-link form that LangSmith
    resolves to the authenticated user's workspace.
    """
    if not run_id:
        return ""
    project = os.environ.get("LANGSMITH_PROJECT", "decepticon-benchmark")
    return f"https://smith.langchain.com/public/{run_id}/r?project={urllib.parse.quote(project)}"


def _compute_window_cost(started_at: str, ended_at: str) -> tuple[float, dict, str]:
    """Aggregate litellm spend logs over a time window and price them.

    Returns ``(total_usd, by_model_breakdown, method_label)``.
    ``method_label`` is ``"time_window"`` so the metadata.json downstream
    knows this is an approximation across all engagements active during
    the same window. Returns ``"time_window_unavailable"`` if the proxy
    is unreachable or no master key is configured.
    """
    if not started_at or not ended_at or not _LITELLM_KEY:
        return 0.0, {}, "time_window_unavailable"
    all_logs: list[dict] = []
    offset = 0
    try:
        while True:
            params = urllib.parse.urlencode(
                {
                    "limit": 100,
                    "offset": offset,
                    "start_date": started_at,
                    "end_date": ended_at,
                }
            )
            req = urllib.request.Request(
                f"{_LITELLM_URL}/spend/logs?{params}",
                headers={"Authorization": f"Bearer {_LITELLM_KEY}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                page = json.loads(resp.read())
            if not page:
                break
            all_logs.extend(page)
            offset += len(page)
            if len(page) < 100 or offset > 20000:
                break
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        log.warning("_compute_window_cost: spend_logs fetch failed: %s", exc)
        return 0.0, {}, "time_window_unavailable"

    by_model: dict[str, dict[str, float | int]] = {}
    for entry in all_logs:
        model = entry.get("model")
        if not model:
            continue
        bucket = by_model.setdefault(
            model, {"calls": 0, "input_tok": 0, "output_tok": 0, "usd": 0.0}
        )
        bucket["calls"] += 1
        bucket["input_tok"] += entry.get("prompt_tokens", 0) or 0
        bucket["output_tok"] += entry.get("completion_tokens", 0) or 0

    total = 0.0
    for model, b in by_model.items():
        in_rate, out_rate = _MODEL_PRICES.get(model, (0.0, 0.0))
        cost = (b["input_tok"] / 1e6) * in_rate + (b["output_tok"] / 1e6) * out_rate
        b["usd"] = round(cost, 4)
        total += cost
    return round(total, 4), by_model, "time_window"


def _iso_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def render_operator_message(
    *,
    template: str,
    scenario: Scenario,
    provision: ProvisionResult,
) -> str:
    """Substitute placeholders in the operator message template.

    Supported placeholders: ``{agent}``, ``{agent_id}``, ``{domain}``,
    ``{entry_url}``, ``{seed_username}``, ``{seed_password}``. Missing
    placeholders are tolerated — they render as empty strings instead of
    raising KeyError.
    """
    creds = provision.seed_credentials or {}
    fields = {
        "agent": scenario.agent_id,
        "agent_id": scenario.agent_id,
        "domain": provision.domain,
        "entry_url": provision.dc_url,
        "seed_username": creds.get("username", ""),
        "seed_password": creds.get("password", ""),
    }
    try:
        return template.format_map({**{k: "" for k in fields}, **fields})
    except (KeyError, IndexError):
        return template


def _measurement_path(scenario_name: str, run_id: str) -> str:
    return f"/workspace/{scenario_name}/measurements/{run_id}.json"


def _provision_workspace(scenario_name: str) -> None:
    """Materialize ``/workspace/<slug>/`` in the sandbox before the agent runs.

    Without this, the agent's first ``ls('/workspace/<slug>')`` hits
    ``path_not_found`` because the engagement directory is created lazily
    on the first write. The OSS Go launcher
    (``clients/launcher/cmd/start.go``) materializes the host workspace
    dir before ``docker compose up`` so the bind-mount lands on a real
    directory; the benchmark harness is the analogous engagement-create
    caller for benchmark mode and owns the same responsibility.

    Mirrors the launcher's per-engagement layout — also seeds ``plan/``
    and ``findings/evidence/`` so the agent's first ``ls`` finds the
    canonical skeleton.

    Idempotent. Non-fatal: failures are logged at warning and the run
    continues.
    """
    workspace = f"/workspace/{scenario_name}"
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                _SANDBOX_CONTAINER,
                "mkdir",
                "-p",
                workspace,
                f"{workspace}/plan",
                f"{workspace}/findings/evidence",
            ],
            capture_output=True,
            timeout=_SANDBOX_READ_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("_provision_workspace(%s): %s", scenario_name, exc)
        return
    if result.returncode != 0:
        log.warning(
            "_provision_workspace(%s) rc=%d stderr=%s",
            scenario_name,
            result.returncode,
            result.stderr[:200],
        )


def pull_measurement_bytes(scenario_name: str, run_id: str | None) -> bytes | None:
    """Read the raw measurement-callback record from the sandbox.

    Returns the file's bytes (suitable for verbatim artifact storage) or
    ``None`` if anything goes wrong. ``docker exec <sandbox> cat
    /workspace/<scenario>/measurements/<run_id>.json`` — coupled to the
    docker-based deploy on purpose; non-docker deployments override via
    ``DECEPTICON_SANDBOX_CONTAINER`` env var.

    A run that died before any tool fired writes a near-empty record; a
    run that never reached on_chain_end / on_chain_error writes none at
    all and we return ``None``.
    """
    if not run_id:
        return None
    path = _measurement_path(scenario_name, run_id)
    try:
        out = subprocess.run(
            ["docker", "exec", _SANDBOX_CONTAINER, "cat", path],
            capture_output=True,
            timeout=_SANDBOX_READ_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("pull_measurement_bytes(%s, %s): %s", scenario_name, run_id, exc)
        return None
    if out.returncode != 0:
        # File-missing is the common case for runs that errored too early
        # for the callback to fire — log at debug to avoid noise.
        log.debug(
            "pull_measurement_bytes(%s): rc=%d stderr=%s",
            path,
            out.returncode,
            out.stderr[:200],
        )
        return None
    return out.stdout


def pull_measurement_record(client: Any, scenario_name: str, run_id: str | None) -> dict:
    """Read the measurement-callback JSON record from the sandbox.

    Wraps ``pull_measurement_bytes`` + JSON-parses. Returns an empty
    dict on any error so a missing/crashed record doesn't abort the
    grid. Tests patch this function directly to inject canned records.
    """
    raw = pull_measurement_bytes(scenario_name, run_id)
    if not raw:
        return {}
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning(
            "pull_measurement_record JSON parse failed for %s: %s",
            scenario_name,
            exc,
        )
        return {}
    return record if isinstance(record, dict) else {}


def _build_result(
    *,
    scenario: Scenario,
    provision: ProvisionResult,
    run_id: str | None,
    started_at: str,
    ended_at: str,
    status: str,
    record: dict,
    thread_id: str = "",
    assistant_id: str = "",
    error_message: str | None = None,
) -> RunResult:
    # Duration in seconds. Started_at / ended_at are ISO-8601 with TZ
    # from _iso_now(); falling back to 0 keeps schema stable when timing
    # is unavailable (e.g. provisioning failure before the run started).
    duration_sec = 0.0
    if started_at and ended_at:
        try:
            duration_sec = (
                _dt.datetime.fromisoformat(ended_at) - _dt.datetime.fromisoformat(started_at)
            ).total_seconds()
        except (TypeError, ValueError):
            pass

    total_usd, by_model, cost_method = _compute_window_cost(started_at, ended_at)

    return RunResult(
        scenario=scenario,
        provision=provision,
        run_id=run_id or "",
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        langsmith_project=os.environ.get("LANGSMITH_PROJECT", "decepticon-benchmark"),
        thread_id=thread_id,
        assistant_id=assistant_id,
        trace_url=_langsmith_trace_url(run_id or ""),
        duration_sec=duration_sec,
        cost_method=cost_method,
        cost_total_usd=total_usd,
        cost_by_model=by_model,
        hosts_compromised=list(record.get("hosts_compromised", [])),
        tool_calls=list(record.get("tool_calls", [])),
        error_message=error_message,
    )


async def run_one(
    scenario: Scenario,
    provider: BaseBenchmarkProvider,
    client: Any,
    config: BenchmarkConfig,
    *,
    shared_provision: ProvisionResult | None = None,
) -> RunResult:
    """Provision -> invoke LangGraph agent -> pull record -> teardown (always).

    When ``shared_provision`` is supplied (shared lab_mode), this run
    does NOT provision or teardown — the runner owns the lab's lifecycle
    for the whole grid. ``shared_provision is None`` keeps the
    isolated-mode behavior (per-scenario provision/teardown).

    Failure modes are caught and surfaced as RunResult with a
    non-completed ``status`` so the runner can continue to the next
    scenario without crashing.
    """
    started_at = _iso_now()
    own_lab = shared_provision is None
    provision = provider.provision(scenario) if own_lab else shared_provision
    # Engagement workspace provisioning is caller responsibility (mirrors
    # the Go launcher's pre-compose mkdir). Doing it here, before the
    # LangGraph graph is invoked, removes the agent's reliance on lazy
    # directory materialization via the first filesystem write.
    _provision_workspace(scenario.name)
    try:
        operator_message = render_operator_message(
            template=config.operator_message_template,
            scenario=scenario,
            provision=provision,
        )
        thread = await client.threads.create()
        thread_id = thread["thread_id"]
        # ``assistant_id`` here is the public graph slug that
        # langgraph_sdk turns into the internal assistant UUID on
        # ``runs.stream``. Recording the slug rather than the UUID keeps
        # the metadata.json link readable across deploys (the UUID
        # changes when the graph is re-registered).
        assistant_id = scenario.agent_id
        final_run_id: str | None = None

        def _capture_run_id(meta: Any) -> None:
            nonlocal final_run_id
            # langgraph_sdk hands us a RunCreateMetadata TypedDict (==
            # dict at runtime) with the run_id of the run it just
            # created. This is the only authoritative place to grab the
            # ID — stream chunks under stream_mode="values" are state
            # objects, not run-metadata events, so reading run_id off
            # them is a no-op.
            if isinstance(meta, dict):
                rid = meta.get("run_id")
            else:
                rid = getattr(meta, "run_id", None)
            if rid:
                final_run_id = rid

        try:
            async for _chunk in client.runs.stream(
                thread_id,
                assistant_id=assistant_id,
                input={"messages": [{"role": "user", "content": operator_message}]},
                config={
                    "configurable": {
                        "engagement_name": scenario.name,
                        "engagement_id": scenario.name,
                        "org_id": "benchmark",
                        "workspace_path": f"/workspace/{scenario.name}",
                        "target_url": provision.dc_url,
                        "target_domain": provision.domain,
                        "target_creds": provision.seed_credentials,
                    }
                },
                stream_mode="values",
                on_run_created=_capture_run_id,
            ):
                pass
        except asyncio.TimeoutError:
            # ★ CRITICAL: cancel the LangGraph-side run BEFORE returning.
            # asyncio.TimeoutError closes only the harness-local stream
            # coroutine. The langgraph-api server keeps the graph running
            # for hours after that — burning model-provider tokens
            # against a thread no one is reading. Issuing an explicit
            # cancel here stops the background work the moment the
            # harness gives up.
            #
            # Best-effort: if ``final_run_id`` was never captured (the
            # langgraph_sdk on_run_created callback can fire late) or the
            # cancel call itself fails, we log and move on — the
            # measurement record we pull below still gives us whatever
            # progress was made.
            if final_run_id:
                try:
                    await client.runs.cancel(thread_id, final_run_id)
                except Exception as cancel_exc:  # noqa: BLE001
                    log.warning(
                        "harness timeout cancel failed for thread=%s run=%s: %s",
                        thread_id,
                        final_run_id,
                        cancel_exc,
                    )
            ended_at = _iso_now()
            return _build_result(
                scenario=scenario,
                provision=provision,
                run_id=final_run_id,
                started_at=started_at,
                ended_at=ended_at,
                status="timeout",
                record=pull_measurement_record(client, scenario.name, final_run_id),
                thread_id=thread_id,
                assistant_id=assistant_id,
            )
        ended_at = _iso_now()
        record = pull_measurement_record(client, scenario.name, final_run_id)
        return _build_result(
            scenario=scenario,
            provision=provision,
            run_id=final_run_id,
            started_at=started_at,
            ended_at=ended_at,
            status="completed",
            record=record,
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _build_result(
            scenario=scenario,
            provision=provision,
            run_id=None,
            started_at=started_at,
            ended_at=_iso_now(),
            status="failed",
            record={},
            error_message=str(exc),
            thread_id=locals().get("thread_id", ""),
            assistant_id=locals().get("assistant_id", scenario.agent_id),
        )
    finally:
        if own_lab and provision is not None:
            provider.teardown(provision)
