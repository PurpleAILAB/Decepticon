---
name: dfir-overview
description: >
  Use to close the Offensive Vaccine loop on the defender side. The Detector
  agent produces Sigma / YARA rules from offensive operations; this catalog
  validates those rules against real memory dumps, event logs, and forensic
  artifacts using Volatility 3, plaso, and sigma-cli. Without this catalog,
  detection rules are theoretical.
metadata:
  subdomain: dfir
  when_to_use: "dfir validation sigma yara volatility plaso memory dump event log forensic artifact detection rule blue team"
  tags: dfir, memory, volatility, plaso, sigma, validation, blue-team
  upstream_ref: "Sigma rules + YARA + Volatility 3 + plaso — detection-rule validation harness for the Offensive Vaccine loop"
---

# Forensicator / DFIR Skill Catalog

Decepticon emits attacks AND detection rules. This catalog feeds the
detection rules back through real forensic artifacts to confirm they fire
— closing the Offensive Vaccine loop on the operations side.

## Playbooks

| Skill | Use for |
|---|---|
| `/skills/standard/dfir/volatility-windows/SKILL.md` | Volatility 3 Windows plugins: pslist, malfind, cmdline, netscan, dlllist, handles |
| `/skills/standard/dfir/volatility-linux/SKILL.md` | Volatility 3 Linux: linux.pslist, linux.bash, linux.malfind |
| `/skills/standard/dfir/plaso-timeline/SKILL.md` | psort + log2timeline; super-timeline construction; Sigma matchers on the timeline |
| `/skills/standard/dfir/sigma-cli-validation/SKILL.md` | sigma-cli convert + match against captured event logs |
| `/skills/standard/dfir/yara-scan/SKILL.md` | yara-x scan against memory dumps and disk images |
| `/skills/standard/dfir/event-log-mining/SKILL.md` | Windows Event Log (.evtx) extraction + key event ID reference |
| `/skills/standard/dfir/etw-trace/SKILL.md` | ETW provider triage; .etl file extraction |
| `/skills/standard/dfir/edr-validation/SKILL.md` | Replay an attack against a target with Velociraptor / OSQuery active; capture artifacts |

## Loop closure workflow

1. **Run an offensive technique** (e.g., `dcsync` from the ad-operator agent).
2. **Detector agent emits Sigma rule** describing the expected detection
   pattern (event 4662 with right `ControlAccessRights`, etc.).
3. **Defender pushes the Sigma to the customer SIEM** via
   `sigma_to_splunk_savedsearch` / `sigma_to_sentinel_analyticrule` /
   `sigma_to_elastic_detection_rule`.
4. **Forensicator validates** by:
   - Collecting the event log from the DC at attack time.
   - Running `sigma-cli convert --target sqlite` and matching against
     the log file.
   - If the match count is 0 → detection rule has a bug. Iterate with
     Detector.
   - If match count is N → detection works. Record the validation
     evidence in the engagement knowledge graph.
5. **Patcher proposes the fix**; Forensicator validates the patch
   doesn't break the detection (verify the rule still fires on attempted
   exploitation of the patched build).

## Tools sandbox

- Volatility 3 (`vol`, `volshell`) — already in operator's AGENTS.md tooling.
- plaso (`log2timeline`, `psort`).
- sigma-cli (`sigma convert`, `sigma check`).
- yara-x (`yr`) — operator already has it installed at `C:\Tools\yara-x\yr.exe`.
- Velociraptor + OSQuery (for live-system validation paths).

## Why this is differentiating

Strix doesn't have this. XBOW doesn't have this. The "Offensive Vaccine"
promise (every attack becomes a defense improvement) is only deliverable
when someone validates the detection. Without Forensicator, the loop
stops at "rule written". With it, the loop completes at "rule verified to
fire on this attack class against this client's stack".
