"""Client-side sanitization: on-disk event → Tier-A telemetry event.

This is the first line of the privacy boundary (the gateway's Tier-C scan is the
second). Two jobs:

1. :func:`event_to_tier_a` — map a redacted event-log record to the closed
   Tier-A allow-list, keeping only non-identifying fields and bucketing exact
   sizes so they cannot fingerprint a run.
2. :func:`scan_tier_c` — a fail-closed scanner mirroring the gateway's, so the
   client refuses to enqueue anything that still carries a raw IP / cred / host
   (e.g. if a future event payload regresses).

The contract mirrors ``telemetry-gateway/schema.json``; keep them in sync.
"""

from __future__ import annotations

import re
from typing import Any

# ── Tier-A contract ──────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"

# Event types we forward (mirror runtime.event_log.EventType values).
_KNOWN_TYPES = frozenset(
    {
        "engagement.start",
        "engagement.end",
        "engagement.checkpoint",
        "agent.turn",
        "tool.call",
        "tool.result",
        "llm.call",
        "llm.response",
        "finding.created",
        "opplan.update",
    }
)

_STATUS_MAP = {"success": "ok", "error": "error"}  # "command" → dropped

_MITRE_TACTIC = re.compile(r"^TA\d{4}$")
_MITRE_TECHNIQUE = re.compile(r"^T\d{4}(\.\d{3})?$")
_CWE = re.compile(r"^CWE-\d{1,5}$")
_CVE = re.compile(r"^CVE-\d{4}-\d{4,7}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)


def _output_bucket(n: int) -> str:
    if n < 128:
        return "0-128"
    if n < 1024:
        return "128-1k"
    if n < 10240:
        return "1k-10k"
    return "10k+"


def _msgs_bucket(n: int) -> str:
    if n < 5:
        return "1-5"
    if n < 10:
        return "5-10"
    if n < 50:
        return "10-50"
    return "50+"


def _slug(value: Any) -> str | None:
    s = str(value).replace("/", "-").lower()
    return s if _SLUG.match(s) and len(s) <= 64 else None


def _id_list(value: Any, pattern: re.Pattern[str], limit: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out = [str(v) for v in value if pattern.match(str(v))]
    return out[:limit]


def event_to_tier_a(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map one event-log record to a Tier-A event, or ``None`` if not forwardable.

    ``record`` is the on-disk shape ``{ts, type, agent?, payload}``. Only the
    fields named in the Tier-A schema survive; everything else is dropped.
    """
    etype = record.get("type")
    if etype not in _KNOWN_TYPES:
        return None
    ts = record.get("ts")
    if not isinstance(ts, (int, float)):
        return None

    ev: dict[str, Any] = {"type": etype, "ts": float(ts)}
    agent = _slug(record.get("agent")) if record.get("agent") else None
    if agent:
        ev["agent"] = agent

    p = record.get("payload") or {}
    if not isinstance(p, dict):
        p = {}

    if etype == "tool.call":
        tool = _slug(p.get("tool"))
        if tool:
            ev["tool"] = tool
    elif etype == "finding.created":
        # Ground-truth finding classification from the Finding model / KG.
        for key in ("tool", "severity", "phase", "confidence", "detected"):
            slug = _slug(p.get(key))
            if slug:
                ev[key] = slug
        # cwe / mitre_techniques come from the shared id-list block below.
    elif etype == "opplan.update":
        phase = _slug(p.get("phase"))
        if phase:
            ev["phase"] = phase
        # OPPLAN status uses a different vocabulary than tool-result `status`
        # (pending/blocked/… vs ok/error), so it maps to its own field.
        status_obj = _slug(p.get("status"))
        if status_obj:
            ev["status_objective"] = status_obj
    elif etype == "tool.result":
        tool = _slug(p.get("tool"))
        if tool:
            ev["tool"] = tool
        status = _STATUS_MAP.get(str(p.get("status", "")))
        if status:
            ev["status"] = status
        n = p.get("output_chars")
        if isinstance(n, int):
            ev["output_bucket"] = _output_bucket(n)
    elif etype == "llm.call":
        model = _slug(p.get("model"))
        if model:
            ev["model"] = model
        m = p.get("messages")
        if isinstance(m, int):
            ev["msgs_bucket"] = _msgs_bucket(m)
    elif etype == "llm.response":
        usage = p.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens") or usage.get("total")
            if isinstance(total, int):
                ev["tokens"] = total
    # MITRE / CWE / CVE pass-through — forwarded only when the source payload
    # already carries them.
    for key, pat, limit in (
        ("mitre_tactics", _MITRE_TACTIC, 16),
        ("mitre_techniques", _MITRE_TECHNIQUE, 32),
        ("cwe", _CWE, 16),
        ("cve", _CVE, 16),
    ):
        ids = _id_list(p.get(key), pat, limit)
        if ids:
            ev[key] = ids

    return ev


# ── Tier-C fail-closed scanner (mirrors telemetry-gateway/src/tierc.ts) ───────

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("url", re.compile(r"\bhttps?://[^\s/$.?#][^\s]*", re.IGNORECASE)),
    ("ipv4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    ("mac", re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")),
    ("user_pass", re.compile(r"\b[\w.-]+:[^\s:@/]{4,}@[\w.-]+")),
    ("opaque_blob", re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")),
    (
        "domain",
        re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE),
    ),
)

# Keys whose values are strict, dotted enums fixed by the schema (e.g. the event
# ``type``) — skip so the domain pattern does not false-positive on the dot.
_ENUM_KEYS = frozenset({"type"})


def scan_tier_c(value: Any, path: str = "$") -> tuple[str, str] | None:
    """Return ``(klass, path)`` for the first forbidden hit, else ``None``.

    The matched VALUE is never returned — surfacing it would itself leak.
    """
    if isinstance(value, str):
        for klass, pattern in _PATTERNS:
            if pattern.search(value):
                return klass, path
        return None
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            hit = scan_tier_c(item, f"{path}[{i}]")
            if hit:
                return hit
        return None
    if isinstance(value, dict):
        for key, val in value.items():
            if key in _ENUM_KEYS:
                continue
            hit = scan_tier_c(val, f"{path}.{key}")
            if hit:
                return hit
    return None
