"""``decepticon-cli telemetry`` — inspect and control usage telemetry.

Subcommands:

* ``status``   show the resolved consent mode, endpoint, and anonymous id
* ``preview``  print the EXACT payload that would be sent for a sample run
               (transparency before any data leaves the machine)
* ``off``      persistently opt out (writes a marker honored by every run)
* ``on``       remove the opt-out marker (telemetry still needs the env opt-in)
"""

from __future__ import annotations

import json
import sys

from decepticon.telemetry.config import (
    TelemetryConfig,
    TelemetryMode,
    is_opted_out,
    resolve_config,
    set_opted_out,
)
from decepticon.telemetry.sink import TelemetrySink

# A representative slice of a real run, used by `preview` so the user sees the
# concrete field set that would be transmitted.
_SAMPLE_EVENTS = [
    {
        "type": "llm.call",
        "ts": 1.0,
        "agent": "recon",
        "payload": {"messages": 12, "model": "claude-opus-4-8"},
    },
    {
        "type": "tool.call",
        "ts": 2.0,
        "agent": "recon",
        "payload": {"tool": "bash", "args": {"command": "<str:23>"}},
    },
    {
        "type": "tool.result",
        "ts": 3.0,
        "agent": "recon",
        "payload": {"tool": "bash", "status": "success", "output_chars": 2048},
    },
    {
        "type": "finding.created",
        "ts": 4.0,
        "agent": "exploit",
        "payload": {"tool": "validate_finding", "cwe": ["CWE-89"], "mitre_techniques": ["T1190"]},
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
    print("# Exact payload that would be sent (sample run):", file=sys.stderr)
    print(json.dumps(sink.preview(_SAMPLE_EVENTS), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    sub = args[0] if args else "status"
    cfg = resolve_config()

    if sub in {"-h", "--help"}:
        print(__doc__, file=sys.stderr)
        return 0
    if sub == "status":
        return _status(cfg)
    if sub == "preview":
        return _preview(cfg)
    if sub == "off":
        set_opted_out(True)
        print("Telemetry disabled (persistent opt-out written).", file=sys.stderr)
        return 0
    if sub == "on":
        set_opted_out(False)
        print(
            "Opt-out removed. Telemetry still requires DECEPTICON_TELEMETRY=basic|extended "
            "and an endpoint to actually send.",
            file=sys.stderr,
        )
        return 0
    print(f"unknown telemetry subcommand: {sub} (use status|preview|off|on)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
