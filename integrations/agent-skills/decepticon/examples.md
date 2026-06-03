# Decepticon MCP — worked examples

Concrete tool-call sequences for common requests, with how to narrate to the
user. Tool calls are shown as `tool(args) -> {key fields}`. Adapt the prose;
keep updates short.

---

## 1. Bug-bounty engagement, watched from a phone

**User:** "Hunt bugs on `https://app.example.com` and `*.example.com`. Out of
scope: the billing host `pay.example.com`. Use Decepticon."

```
decepticon_start_engagement(
  targets=["https://app.example.com", "*.example.com"],
  instruction="In scope: app.example.com and all *.example.com subdomains. "
              "Out of scope: pay.example.com (production billing). Bug-bounty "
              "rules: no DoS, no data exfiltration, rate-limit requests.",
  scan_mode="standard",
) -> { thread_id: "th_1", engagement_name: "mcp-20260603-2140", status: "pending" }
```

Reply: *"Engagement `mcp-20260603-2140` started against app.example.com (+
subdomains), billing host excluded. I'll watch and report progress."*

Then poll (every ~20s), advancing the cursor:

```
decepticon_transcript(thread_id="th_1", after_index=0) -> { next_index: 6, run_status: "running",
  messages: [ ... assistant: "Building OPPLAN…", tool_calls: ["task(recon)"], tool(name=task): "Found 4 subdomains, 3 web apps…" ] }
```

Reply: *"Recon done — 4 subdomains, 3 web apps. Now enumerating endpoints."*
Next poll uses `after_index=6`, and so on. When:

```
decepticon_engagement_status(thread_id="th_1", engagement_name="mcp-20260603-2140")
  -> { status: "running", findings_available: true }
decepticon_engagement_findings(engagement_name="mcp-20260603-2140", include_sarif=true)
  -> { available: true, result_count: 3, level_counts: {error: 1, warning: 2}, sarif: {...} }
```

Reply with the findings: 1 high + 2 medium, each with affected URL + repro from
`sarif.runs[0].results[]`. Offer to keep the run going for deeper coverage.

## 2. Recon only

**User:** "Just do recon on `10.10.0.0/24`, don't exploit anything."

```
decepticon_start_engagement(targets=["10.10.0.0/24"],
  instruction="Recon and enumeration ONLY. In scope: 10.10.0.0/24. Do not exploit.",
  assistant="recon", scan_mode="quick")
```

Use the `recon` graph + an explicit no-exploit instruction. Watch via
`transcript`; report hosts/services/attack surface from
`decepticon_engagement_state(thread_id)` (`values` holds the recon map).

## 3. Steering a live engagement

**User (mid-run):** "Ignore the marketing site, focus on the API at `/api/v2`."

```
decepticon_send_message(thread_id="th_1",
  message="Deprioritize the marketing site. Focus on the REST API under /api/v2 — "
          "test authz/IDOR and injection there.") -> { run_id: "rn_9", status: "pending" }
```

Reply: *"Refocusing the engagement on `/api/v2` (authz/IDOR + injection)."* Keep
polling the transcript to confirm the orchestrator picked it up.

**Switch models mid-run** (e.g. for a hard target):

```
decepticon_send_message(thread_id="th_1", message="/model anthropic/claude-opus-4-8")
```

## 4. Check status / resume later

**User (next day):** "What's happening with the example.com engagement?"

```
decepticon_list_engagements(limit=20) -> [{ thread_id: "th_1", engagement_name: "mcp-20260603-2140", status: "idle" }, …]
decepticon_transcript(thread_id="th_1", after_index=0, limit=10)   # recent narrative
decepticon_engagement_findings(engagement_name="mcp-20260603-2140")  # what was found
```

Summarise where it stands + findings. To continue, `decepticon_send_message` or
`decepticon_start_engagement` a fresh pass.

## 5. A live burst (when the user wants detail "right now")

```
decepticon_watch(thread_id="th_1", max_seconds=15, max_events=30)
  -> { run_status: "running", events: [{event:"custom", data:"{\"type\":\"recon_step\",…}"}, …], truncated: true }
```

Summarise the live sub-agent activity (e.g. "recon agent is fuzzing
directories, exploit agent queued"). Then return to the normal transcript loop.

## 6. Handling failure

```
decepticon_engagement_status(thread_id="th_1", engagement_name="…") -> { status: "error" }
decepticon_transcript(thread_id="th_1", after_index=<n>, limit=10)  # read the cause
```

Tell the user what failed (from the last messages) and offer to
`decepticon_send_message` a correction or start a fresh engagement. If a tool
errors with a connection problem, the Decepticon server is down — ask the user
to start it rather than retrying.

---

## Narration principles

- One or two sentences per update; lead with what changed.
- Name the phase/specialist ("recon", "exploit", "post-ex") so the user follows
  the kill chain.
- Surface findings with **severity + affected target + one-line repro**.
- Never paste raw transcript/SARIF dumps into chat — summarise; offer detail on
  request.
