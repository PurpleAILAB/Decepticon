"""``decepticon-cli telemetry`` — inspect and control usage telemetry.

Subcommands:

* ``status``          show the resolved consent mode, endpoint, and anonymous id
* ``preview``         print the EXACT payload that would be sent for a sample run
                      (transparency before any data leaves the machine)
* ``enable <mode>``   give explicit consent (``basic`` or ``research``); prints
                      the full disclosure and persists the choice
* ``off``             persistently opt out (honored by every run)
* ``on``              alias for ``enable basic``
"""

from __future__ import annotations

import json
import sys

from decepticon.telemetry.config import (
    TelemetryConfig,
    TelemetryMode,
    is_opted_out,
    resolve_config,
    set_persisted_mode,
)
from decepticon.telemetry.sink import TelemetrySink

# Plain-language disclosure shown on `enable` — the OSS consent contract.
_CONSENT_NOTICE = """\
Decepticon usage telemetry — what you are consenting to share:

  basic     Anonymous STRUCTURAL ground truth the engagement produces: event
            type, agent name, tool name (e.g. nmap), status, bucketed sizes,
            model id, OS, version, and the validated FINDING's own classification
            (severity, CWE/MITRE, phase, confidence, detected) + OPPLAN progress.
            No prompt text. No targets.

  research  basic, PLUS the red-team REASONING corpus: your objectives, the
            agent's chain-of-thought and tactic rationale, the commands it runs,
            and the observations — captured as-is so the attacker reasoning is
            preserved for training future autonomous red-team agents. Target
            IDENTIFIERS are MASKED (10.0.0.5 -> <HOST_1>, creds -> <CRED_1>) so
            the reasoning stays intact but no real target/credential is shared.

NEVER sent, at any tier: real target IPs/domains/hosts, credentials, client/org
names (masked in research), and your IP (dropped at the gateway). You can share
the agent's reasoning, which is yours — never a target's data.

Run `decepticon-cli telemetry preview` to see the exact payload before sending.
DO_NOT_TRACK=1 or `telemetry off` disables everything.
"""

# A representative slice of a real run, used by `preview` so the user sees the
# concrete field set that would be transmitted.
_SAMPLE_EVENTS = [
    {
        "type": "opplan.update",
        "ts": 1.0,
        "agent": "decepticon",
        "payload": {"phase": "recon", "status": "pending"},
    },
    {
        "type": "llm.call",
        "ts": 2.0,
        "agent": "recon",
        "payload": {"messages": 12, "model": "claude-opus-4-8"},
    },
    {
        "type": "tool.call",
        "ts": 3.0,
        "agent": "recon",
        "payload": {"tool": "bash", "args": {"command": "<str:23>"}},
    },
    {
        "type": "tool.result",
        "ts": 4.0,
        "agent": "recon",
        "payload": {"tool": "bash", "status": "success", "output_chars": 2048},
    },
    {
        "type": "finding.created",
        "ts": 5.0,
        "agent": "exploit",
        "payload": {
            "severity": "high",
            "phase": "initial-access",
            "confidence": "verified",
            "detected": "no",
            "cwe": ["CWE-89"],
            "mitre_techniques": ["T1190"],
        },
    },
]


def _status(cfg: TelemetryConfig) -> int:
    print("Decepticon telemetry")
    print(f"  mode:      {cfg.mode.value}")
    print(f"  enabled:   {cfg.enabled}  (needs mode != off AND an endpoint)")
    print(f"  endpoint:  {cfg.endpoint or '(unset)'}")
    print(f"  opted_out: {is_opted_out()}")
    if cfg.enabled:
        print(f"  install_id: {cfg.install_id}")
    print("\nRaw prompts, targets, and credentials are NEVER transmitted. See TELEMETRY.md.")
    return 0


def _preview(cfg: TelemetryConfig) -> int:
    # Force at least BASIC + a placeholder endpoint so the mapping runs even when
    # telemetry is currently off — preview shows what *would* be sent.
    mode = cfg.mode if cfg.mode is not TelemetryMode.OFF else TelemetryMode.BASIC
    preview_cfg = TelemetryConfig(
        mode=mode,
        endpoint=cfg.endpoint or "https://<your-endpoint>",
        install_id=cfg.install_id if cfg.enabled else "<anonymous-install-id>",
        version=cfg.version,
        os_name=cfg.os_name,
    )
    sink = TelemetrySink(preview_cfg, transport=lambda _u, _b: None)
    print(f"# Exact payload that would be sent (tier {mode.value}):", file=sys.stderr)
    print(json.dumps(sink.preview(_SAMPLE_EVENTS), indent=2))
    return 0


def _enable(arg: str | None) -> int:
    raw = (arg or "basic").strip().lower()
    try:
        mode = TelemetryMode(raw)
    except ValueError:
        print(f"unknown mode: {raw} (use basic|research)", file=sys.stderr)
        return 2
    if mode is TelemetryMode.OFF:
        return _off()
    print(_CONSENT_NOTICE, file=sys.stderr)
    set_persisted_mode(mode)
    print(
        f"Telemetry enabled at '{mode.value}'. Set DECEPTICON_TELEMETRY_ENDPOINT to start sending.",
        file=sys.stderr,
    )
    return 0


def _off() -> int:
    set_persisted_mode(TelemetryMode.OFF)
    print("Telemetry disabled (persistent opt-out written).", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    sub = args[0] if args else "status"

    if sub in {"-h", "--help"}:
        print(__doc__, file=sys.stderr)
        return 0
    if sub == "status":
        return _status(resolve_config())
    if sub == "preview":
        return _preview(resolve_config())
    if sub == "enable":
        return _enable(args[1] if len(args) > 1 else None)
    if sub == "on":
        return _enable("basic")
    if sub == "off":
        return _off()
    print(
        f"unknown telemetry subcommand: {sub} (use status|preview|enable|off|on)", file=sys.stderr
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
