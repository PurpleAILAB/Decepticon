#!/usr/bin/env python3
"""Export the masked red-team reasoning corpus from PostHog as training JSONL.

The gateway ships identifier-masked ``trajectory.step`` events to PostHog (event
analytics). This pulls them back out and **reconstructs per-engagement
trajectories** — the ordered, role-labeled turn sequences an imitation/RL
training pipeline consumes. One JSON object per engagement:

    {"session_id": "...", "install_id": "...", "n_steps": 4, "steps": [
        {"step": 0, "role": "human", "agent": "decepticon", "text": "..."},
        {"step": 1, "role": "agent", "agent": "recon",      "text": "..."},
        {"step": 2, "role": "tool",  "agent": "recon", "tool": "bash",
         "args_text": "...", "observation": "..."},
        {"step": 3, "role": "agent", "agent": "exploit",    "text": "..."}
    ]}

All content is already masked (``<HOST_1>`` / ``<CRED_1>``) — no real target
ever reached PostHog, so the export is safe to share as a dataset.

Auth (no new account — reuse the deploy creds):
    set -a; . ~/.decepticon/telemetry-deploy.env; set +a
    python export_corpus.py --out corpus.jsonl            # all trajectories
    python export_corpus.py --since-hours 24 --out day.jsonl
    python export_corpus.py --self-test                   # offline logic check

Env: POSTHOG_CLI_API_KEY (personal), POSTHOG_CLI_PROJECT_ID, POSTHOG_HOST.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any

# Rows per page. HogQL caps a single query well below the corpus size, so the
# export pages rather than trusting one request.
_PAGE = 10_000

# Column order returned by the HogQL query below.
_COLS = [
    "session_id",
    "step",
    "role",
    "agent",
    "tool",
    "text",
    "args_text",
    "observation",
    "distinct_id",
]


def group_trajectories(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Group flat ``trajectory.step`` rows into ordered per-engagement trajectories.

    ``rows`` are ``[session_id, step, role, agent, tool, text, args_text,
    observation, distinct_id]``. Grouped by ``(distinct_id, session_id)`` — the
    install + engagement hash uniquely identify one engagement — and each group's
    steps are sorted by ``step``. Pure function (no I/O) so it is unit-testable.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        rec = dict(zip(_COLS, r, strict=False))
        key = (str(rec.get("distinct_id") or ""), str(rec.get("session_id") or ""))
        traj = groups.setdefault(
            key,
            {
                "session_id": rec.get("session_id"),
                "install_id": rec.get("distinct_id"),
                "steps": [],
            },
        )
        step: dict[str, Any] = {"step": _as_int(rec.get("step")), "role": rec.get("role")}
        for field in ("agent", "tool", "text", "args_text", "observation"):
            val = rec.get(field)
            if val not in (None, ""):
                step[field] = val
        traj["steps"].append(step)
    out: list[dict[str, Any]] = []
    for traj in groups.values():
        traj["steps"].sort(key=lambda s: s.get("step") if s.get("step") is not None else 0)
        traj["n_steps"] = len(traj["steps"])
        out.append(traj)
    out.sort(key=lambda t: str(t.get("session_id")))
    return out


def _as_int(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _query(host: str, project: str, api_key: str, since_hours: int | None) -> list[list[Any]]:
    # Exclude gateway/deploy verification traffic — a poisoned training corpus is
    # far more expensive than a skewed chart. Mirrors build_dashboard.NOT_TEST.
    where = (
        "event = 'trajectory.step' "
        "AND coalesce(toString(properties.decepticon_version),'') "
        "NOT IN ('deploy-verify', 'live-verify') "
        "AND distinct_id NOT IN ('00000000-0000-4000-8000-000000000001', "
        "'11111111-1111-4111-8111-111111111111', "
        "'ce9fffea-a87a-4375-a2dd-f6217f743959', "
        "'2e953b6e-bf01-4140-bc6d-26a6ec2c82f2', "
        "'6b49be5b-459c-4332-a2f6-30787d8bd479', "
        "'28bcd7df-a74e-4489-859d-ed6a8d912add')"
    )
    if since_hours:
        where += f" AND timestamp > now() - INTERVAL {int(since_hours)} HOUR"
    # Paginate. HogQL applies a default LIMIT of 100 when a query does not state
    # one, so this exported 100 of 119,774 rows and reported success — a
    # silently truncated corpus is worse than a failed export. OFFSET is
    # rejected for personal API keys, so this is keyset pagination on
    # `timestamp`, as PostHog directs. `timestamp` is selected last so the
    # `_COLS` zip is unaffected.
    rows: list[list[Any]] = []
    seen: set[tuple[Any, ...]] = set()
    cursor = "1970-01-01 00:00:00"
    while True:
        hogql = (
            "SELECT properties.session_id, properties.step, properties.role, properties.agent, "
            "properties.tool, properties.text, properties.args_text, properties.observation, "
            "distinct_id, timestamp "
            f"FROM events WHERE {where} AND timestamp >= toDateTime('{cursor}') "
            f"ORDER BY timestamp LIMIT {_PAGE}"
        )
        body = json.dumps({"query": {"kind": "HogQLQuery", "query": hogql}}).encode()
        req = urllib.request.Request(
            f"{host.rstrip('/')}/api/projects/{project}/query/",
            data=body,
            headers={"content-type": "application/json", "authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 — operator-configured
            page = json.loads(resp.read()).get("results", [])
        if not page:
            return rows
        # `>=` re-reads the boundary timestamp, so dedupe rather than risk the
        # strict-`>` variant skipping rows that share it.
        fresh = [r for r in page if (key := tuple(map(str, r))) not in seen and not seen.add(key)]
        rows.extend(fresh)
        if len(page) < _PAGE:
            return rows
        last = str(page[-1][-1])
        if not fresh:
            # A whole page at one timestamp: step past it or loop forever.
            cursor = _bump_ms(last)
        else:
            cursor = last
        print(f"  fetched {len(rows)} rows…", file=sys.stderr)


def _bump_ms(ts: str) -> str:
    """Advance an ISO timestamp by 1ms to break a same-timestamp page."""
    from datetime import datetime, timedelta

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return (datetime.strptime(ts, fmt) + timedelta(milliseconds=1)).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
        except ValueError:
            continue
    return ts


_SELF_TEST_ROWS = [
    ["s1", "1", "agent", "recon", "", "Recon <HOST_1>", "", "", "inst-a"],
    ["s1", "0", "human", "recon", "", "Objective: own <HOST_1>", "", "", "inst-a"],
    ["s1", "2", "tool", "recon", "bash", "", "nmap <HOST_1>", "445 open", "inst-a"],
    ["s2", "0", "agent", "exploit", "", "different engagement", "", "", "inst-a"],
]


def _self_test() -> int:
    trajs = group_trajectories(_SELF_TEST_ROWS)
    assert len(trajs) == 2, trajs  # two distinct (install, session) engagements
    t = next(t for t in trajs if t["session_id"] == "s1")
    assert [s["step"] for s in t["steps"]] == [0, 1, 2], "steps must be ordered"
    assert [s["role"] for s in t["steps"]] == ["human", "agent", "tool"]
    assert t["steps"][2]["observation"] == "445 open" and t["steps"][2]["tool"] == "bash"
    assert t["n_steps"] == 3 and t["install_id"] == "inst-a"
    print("self-test OK: trajectories reconstructed, ordered, role-labeled")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Export the masked reasoning corpus from PostHog as JSONL."
    )
    ap.add_argument("--out", default="-", help="output JSONL path (default: stdout)")
    ap.add_argument(
        "--since-hours", type=int, default=None, help="only trajectories newer than N hours"
    )
    ap.add_argument(
        "--self-test", action="store_true", help="run the offline grouping check and exit"
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    api_key = os.environ.get("POSTHOG_CLI_API_KEY")
    project = os.environ.get("POSTHOG_CLI_PROJECT_ID")
    host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com")
    if not api_key or not project:
        print(
            "error: set POSTHOG_CLI_API_KEY and POSTHOG_CLI_PROJECT_ID (see the deploy creds file).",
            file=sys.stderr,
        )
        return 2

    rows = _query(host, project, api_key, args.since_hours)
    trajectories = group_trajectories(rows)

    fh = sys.stdout if args.out == "-" else open(args.out, "w", encoding="utf-8")  # noqa: SIM115
    try:
        for traj in trajectories:
            fh.write(json.dumps(traj, ensure_ascii=False) + "\n")
    finally:
        if fh is not sys.stdout:
            fh.close()
    total_steps = sum(t["n_steps"] for t in trajectories)
    print(
        f"exported {len(trajectories)} trajectories / {total_steps} steps"
        + (f" -> {args.out}" if args.out != "-" else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
