#!/usr/bin/env python3
"""Rebuild the PostHog dashboard into a purpose-aligned view:
   *How OSS users use the Decepticon red-team harness, and what tactics they run.*

Replaces the generic v1 dashboard with three sections:
  Usage  — adoption, kill-chain reach, engagement depth, attack surface
  Tactics— MITRE techniques, tools run, failure hotspots, finding/vuln classes
  Corpus — the masked reasoning-trajectory training corpus (the gold)

Engagement-level insights rely on `properties.session_id` now being stamped on
every event (not just trajectory steps) — see feat/telemetry-session-everywhere.

Auth: set -a; . ~/.decepticon/telemetry-deploy.env; set +a
"""

from __future__ import annotations

import json
import os
import urllib.request

HOST = os.environ.get("POSTHOG_HOST", "https://us.posthog.com").rstrip("/")
PROJECT = os.environ["POSTHOG_CLI_PROJECT_ID"]
KEY = os.environ["POSTHOG_CLI_API_KEY"]
# Set OLD_DASHBOARD_ID to retire a previous dashboard (+ its insights) first.
OLD_DASHBOARD_ID = os.environ.get("OLD_DASHBOARD_ID", "")


def api(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{HOST}/api/projects/{PROJECT}{path}",
        data=data,
        headers={"content-type": "application/json", "authorization": f"Bearer {KEY}"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        raw = r.read()
        return json.loads(raw) if raw else {}


def hogql(sql: str) -> dict:
    return {"kind": "DataVisualizationNode", "source": {"kind": "HogQLQuery", "query": sql}}


SID = "coalesce(toString(properties.session_id),'') != ''"

INSIGHTS: list[tuple[str, str, str]] = [
    # ── USAGE ────────────────────────────────────────────────────────────────
    (
        "Usage · Engagements & installs per day",
        "Daily distinct engagements (session_id) and installs — adoption & volume.",
        f"""SELECT toStartOfDay(timestamp) AS day,
       count(DISTINCT properties.session_id) AS engagements,
       count(DISTINCT distinct_id) AS installs
FROM events WHERE {SID}
GROUP BY day ORDER BY day""",
    ),
    (
        "Usage · Kill-chain reach (engagements per phase)",
        "How far engagements get — count of distinct engagements that reached each "
        "kill-chain phase. The drop-off recon→exfiltration is the usage funnel.",
        # Phase ordering lives in an outer query: ordering by multiIf() on the raw
        # property in the same scope as GROUP BY trips HogQL's not-an-aggregate check.
        """SELECT phase, engagements_reached FROM (
  SELECT properties.phase AS phase,
         count(DISTINCT properties.session_id) AS engagements_reached
  FROM events WHERE event = 'opplan.update' AND coalesce(toString(properties.phase),'') != ''
  GROUP BY phase
) ORDER BY multiIf(phase='recon',1, phase='initial-access',2, phase='post-exploit',3,
                   phase='c2',4, phase='exfiltration',5, 99)""",
    ),
    (
        "Usage · Engagement outcome — reached a finding",
        "Share of engagements that produced at least one validated finding "
        "(a proxy for end-to-end success).",
        f"""SELECT
  count(DISTINCT properties.session_id) AS engagements_total,
  count(DISTINCT if(event='finding.created', properties.session_id, NULL)) AS engagements_with_finding,
  round(100 * count(DISTINCT if(event='finding.created', properties.session_id, NULL))
        / nullIf(count(DISTINCT properties.session_id),0), 1) AS pct_with_finding
FROM events WHERE {SID}""",
    ),
    (
        "Usage · Engagement depth (events & tools each)",
        "Per-engagement activity — total events, distinct tools, max trajectory step. "
        "Separates quick scans from deep multi-tool engagements.",
        f"""SELECT properties.session_id AS engagement,
       count() AS events,
       count(DISTINCT if(event='tool.call', properties.tool, NULL)) AS distinct_tools,
       max(toInt(coalesce(toString(properties.step),'0'))) AS max_step
FROM events WHERE {SID}
GROUP BY engagement ORDER BY events DESC LIMIT 100""",
    ),
    (
        "Usage · Power users (engagements per install)",
        "Engagements per install — one-off trials vs. repeat operators.",
        f"""SELECT distinct_id AS install,
       count(DISTINCT properties.session_id) AS engagements,
       count() AS events
FROM events WHERE {SID}
GROUP BY install ORDER BY engagements DESC LIMIT 100""",
    ),
    (
        "Usage · Agent / attack-surface utilization",
        "Which of the 16 specialists run (recon/web/AD/cloud/exploit…) — a proxy for "
        "the attack surfaces users actually target.",
        """SELECT properties.agent AS agent,
       count() AS events,
       count(DISTINCT properties.session_id) AS engagements
FROM events WHERE coalesce(toString(properties.agent),'') != ''
GROUP BY agent ORDER BY events DESC""",
    ),
    (
        "Usage · Model / provider mix",
        "LLM models powering the agents.",
        """SELECT properties.model AS model, count() AS llm_calls
FROM events WHERE event='llm.call' AND coalesce(toString(properties.model),'') != ''
GROUP BY model ORDER BY llm_calls DESC""",
    ),
    (
        "Usage · Version & OS adoption",
        "Installed Decepticon version × OS — upgrade & platform-support signal.",
        """SELECT properties.decepticon_version AS version, properties.os AS os,
       count(DISTINCT distinct_id) AS installs
FROM events GROUP BY version, os ORDER BY installs DESC""",
    ),
    # ── TACTICS ──────────────────────────────────────────────────────────────
    (
        "Tactics · MITRE ATT&CK techniques",
        "Techniques attached to validated findings — what users actually achieve.",
        """SELECT replaceAll(arrayJoin(JSONExtractArrayRaw(
         coalesce(toString(properties.mitre_techniques),'[]'))),'"','') AS technique,
       count() AS findings
FROM events WHERE event='finding.created'
GROUP BY technique HAVING technique != '' ORDER BY findings DESC""",
    ),
    (
        "Tactics · Top tools executed (TTPs)",
        "Most-run tools — the concrete techniques operators reach for.",
        """SELECT properties.tool AS tool, count() AS calls,
       count(DISTINCT properties.session_id) AS engagements
FROM events WHERE event='tool.call' AND coalesce(toString(properties.tool),'') != ''
GROUP BY tool ORDER BY calls DESC LIMIT 30""",
    ),
    (
        "Tactics · Tool failure hotspots (error rate)",
        "Tools by error rate (≥3 results) — where the harness/tactics break, i.e. "
        "where users struggle and what to harden.",
        """SELECT properties.tool AS tool, count() AS results,
       countIf(properties.status='error') AS errors,
       round(100*countIf(properties.status='error')/nullIf(count(),0),1) AS error_pct
FROM events WHERE event='tool.result' AND coalesce(toString(properties.tool),'') != ''
GROUP BY tool HAVING results >= 3 ORDER BY error_pct DESC, results DESC LIMIT 30""",
    ),
    (
        "Tactics · Finding severity distribution",
        "Severity of validated findings.",
        """SELECT properties.severity AS severity, count() AS findings
FROM events WHERE event='finding.created' AND coalesce(toString(properties.severity),'') != ''
GROUP BY severity
ORDER BY multiIf(severity='critical',1,severity='high',2,severity='medium',3,
                 severity='low',4,severity='informational',5,99)""",
    ),
    (
        "Tactics · Vulnerability classes (CWE)",
        "CWE classes of validated findings — what vuln types users find.",
        """SELECT replaceAll(arrayJoin(JSONExtractArrayRaw(
         coalesce(toString(properties.cwe),'[]'))),'"','') AS cwe,
       count() AS findings
FROM events WHERE event='finding.created'
GROUP BY cwe HAVING cwe != '' ORDER BY findings DESC""",
    ),
    (
        "Tactics · Purple-team detection rate",
        "Were findings detected by defenses (purple-team flag)?",
        """SELECT properties.detected AS detected, count() AS findings
FROM events WHERE event='finding.created' AND coalesce(toString(properties.detected),'') != ''
GROUP BY detected""",
    ),
    # ── CORPUS (the reasoning gold) ──────────────────────────────────────────
    (
        "Corpus · Reasoning steps by role over time",
        "Masked trajectory steps/day split by role (human/agent/tool) — the training "
        "corpus accumulating.",
        """SELECT toStartOfDay(timestamp) AS day, properties.role AS role, count() AS steps
FROM events WHERE event='trajectory.step' AND coalesce(toString(properties.role),'') != ''
GROUP BY day, role ORDER BY day, role""",
    ),
    (
        "Corpus · Reasoning-chain depth per engagement",
        "Length of the captured reason→act→observe chain per engagement.",
        f"""SELECT properties.session_id AS engagement,
       max(toInt(coalesce(toString(properties.step),'0'))) + 1 AS chain_steps,
       count() AS captured_steps
FROM events WHERE event='trajectory.step' AND {SID}
GROUP BY engagement ORDER BY chain_steps DESC LIMIT 100""",
    ),
    (
        "Corpus · Reasoning volume by agent",
        "Which specialists generate the most reasoning/tool turns in the corpus.",
        """SELECT properties.agent AS agent, count() AS steps,
       countIf(properties.role='agent') AS reasoning_turns,
       countIf(properties.role='tool') AS tool_turns
FROM events WHERE event='trajectory.step' AND coalesce(toString(properties.agent),'') != ''
GROUP BY agent ORDER BY steps DESC""",
    ),
]


def main() -> int:
    # 1. Retire the generic v1 dashboard + its insights.
    if OLD_DASHBOARD_ID:
        try:
            old = api("GET", f"/dashboards/{OLD_DASHBOARD_ID}/")
            for tile in old.get("tiles", []):
                iid = (tile.get("insight") or {}).get("id")
                if iid:
                    api("PATCH", f"/insights/{iid}/", {"deleted": True})
            api("PATCH", f"/dashboards/{OLD_DASHBOARD_ID}/", {"deleted": True})
            print(
                f"retired old dashboard {OLD_DASHBOARD_ID} (+{len(old.get('tiles', []))} insights)"
            )
        except Exception as e:  # noqa: BLE001
            print(f"(skip old-dashboard cleanup: {e})")

    # 2. New dashboard.
    dash = api(
        "POST",
        "/dashboards/",
        {
            "name": "Decepticon — OSS Usage & Tactics",
            "description": "How OSS users use the red-team harness and what tactics they "
            "run. Sections: Usage / Tactics / Corpus. Populates as opted-in "
            "telemetry arrives from released clients.",
        },
    )
    did = dash["id"]

    # 3. Insights linked to it (creation order = tile order).
    for name, desc, sql in INSIGHTS:
        ins = api(
            "POST",
            "/insights/",
            {
                "name": name,
                "description": desc,
                "query": hogql(sql),
                "dashboards": [did],
            },
        )
        print(f"  + [{ins.get('id')}] {name}")

    # 4. Verify.
    got = api("GET", f"/dashboards/{did}/")
    tiles = got.get("tiles", [])
    print(f"\ndashboard: {got.get('name')}  (id={did})  tiles={len(tiles)}")
    print(f"URL: {HOST}/project/{PROJECT}/dashboard/{did}")
    assert len(tiles) == len(INSIGHTS), f"expected {len(INSIGHTS)} tiles, got {len(tiles)}"
    print("OK — all insights linked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
