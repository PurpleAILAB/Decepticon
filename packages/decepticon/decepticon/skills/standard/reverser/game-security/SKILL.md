---
name: game-security-research
description: "Authorized game-client, protocol, replay, and anti-tamper security research for local, self-hosted, or intentionally vulnerable training targets."
allowed-tools: Read Write Bash
metadata:
  subdomain: reverse-engineering
  when_to_use: "game security Unity Unreal IL2CPP replay savegame protocol server authority anti-tamper authorized training lab"
  upstream_ref: "OWASP Game Security Framework concepts, Unity/Unreal vendor debugging documentation, Pwn Adventure educational game-security lab"
  capability_contract:
    lane: game-security
    scope: isolated-lab
    environment: [self-hosted-game-server, disposable-client-vm, isolated-network]
    required_tools: [ghidra, frida, wireshark]
    evidence: [client-build-hash, packet-capture, replay-artifact, server-state-diff]
    verification: "replay the minimal input against a local or explicitly authorized self-hosted game service"
    negative_control: "run an equivalent valid client action and confirm the server state does not change"
    scorecard: [validated-rate, server-authority-coverage, remediation-verification-rate]
    benchmark: held-out-game-security
---

# Game Security Research

## Scope

Use only local, self-hosted, or intentionally vulnerable game targets with
written authorization. Do not create or deploy online-game cheats, anti-cheat
bypasses, ban evasion, aim assistance, overlays, memory manipulation, or
multiplayer disruption tooling.

## Research workflow

1. **Pin client and server builds.** Record executable hashes, engine version,
   platform, symbols, server commit, and local-lab topology before inspection.
2. **Map trust boundaries.** Identify which values are authoritative on the
   server: inventory, currency, movement, progression, matchmaking, replay, and
   entitlement state. Classify client-only checks as hypotheses until server
   state is measured.
3. **Analyze accepted artifacts.** Inspect local save files, replay formats,
   asset bundles, protocol schemas, and debug telemetry. Keep raw captures and
   parsed summaries separate.
4. **Validate safely.** Submit the minimum input to the self-hosted target and
   record the server-observed state transition. Run the corresponding ordinary
   player action as the negative control.
5. **Evaluate defenses.** Exercise anti-tamper and telemetry only as a defender:
   confirm expected alerts, integrity checks, and server-side rejection after a
   local test case. Never develop an evasion workflow.

## Promotion rule

A reportable finding must include the pinned build identity, minimal replay or
request, packet/trace evidence, server-side state delta, baseline result, and a
post-remediation replay. A client-only display change is not proof of impact.
