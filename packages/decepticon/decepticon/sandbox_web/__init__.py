"""Decepticon open-web acquisition engine — runs INSIDE the sandbox.

A site-agnostic, multi-phase fetch engine that escalates on detected blocking
signals (WAF/challenge) rather than giving up on the first non-200. It is the
sandbox-side worker behind the ``web_search`` / ``web_fetch`` agent tools: the
tool wrappers (management process) RoE-gate the request and then dispatch this
engine over the existing bash execution surface, so every byte of egress
happens inside ``sandbox-net`` behind the nftables/DNS allowlist.

Design is precisely derived from ``fivetaku/insane-search`` (MIT) — the Verdict
model, 4-layer validation, WAF-profile ranking, transform×TLS×referer grid, and
the No-Site-Name rule — but its governance is **inverted** for Decepticon:

  * anti-allowlist "try everything"  → every hop gated by ``evaluate_target``,
    fail-closed.
  * in-process browser/curl          → runs inside the sandbox only.
  * runtime ``pip install`` of deps  → deps baked into the sandbox image at
    build time (CODEOWNERS-gated); never installed at runtime.
  * raw output to the model          → wrapped by ``UntrustedOutput`` upstream.
  * stealth always on                → default-off, per-engagement opt-in.

See ``docs/adr/0010-open-web-acquisition.md`` for the decision record.
"""

from __future__ import annotations

from decepticon.sandbox_web.validators import (
    CHALLENGE_MARKERS,
    ValidationResult,
    Verdict,
    validate,
)

__all__ = [
    "CHALLENGE_MARKERS",
    "ValidationResult",
    "Verdict",
    "validate",
]
