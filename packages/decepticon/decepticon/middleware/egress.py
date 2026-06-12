"""Layer-2 RoE egress guardrail — compile scope rules into a network boundary.

The parser-side :class:`~decepticon.middleware.roe.RoEGuardrailMiddleware`
is a *fast-fail UX* gate: it reads the literal command text and refuses
early when it can see an out-of-scope target. It cannot be the
authoritative boundary — a target can hide behind variable indirection,
command substitution, or out-of-band DNS resolution the parser never
sees (see ``docs/design/2026-06-12-roe-guardrail-middleware-redesign.md``).

This module is the authoritative half. ``compile_egress_policy`` turns
the **same** ``roe.json:machine_enforcement`` block the parser reads into
an :class:`EgressPolicy`, which the sandbox enforces at its network edge:

  * an **nftables** connect-allowlist (``render_nftables``) — outbound
    packets are dropped unless their destination IP/CIDR is in scope;
    cloud-metadata / out-of-scope ranges drop before the scope allow so
    denylist precedence holds.
  * a **DNS allowlist** (``render_dns_allowlist``) — the sandbox
    resolver answers only in-scope hostnames / wildcards.

One scope definition, two enforcement points. A packet to an
out-of-scope host cannot leave the sandbox even when the command parser
missed the target.

Layering
--------
The renderer + applier (``render_nftables``, ``render_dns_allowlist``,
``apply_egress``) live in ``decepticon.sandbox_kernel.egress`` because
they run *inside* the sandbox container — where ``nft`` exists, the
management subnet is locally discoverable, and the image ships no
``decepticon_core``. They are re-exported here for convenience. This
module owns only the core-dependent step: ``MachineEnforcement`` →
:class:`EgressPolicy`. The compiled policy is serialised over the
``/provision_egress`` endpoint; the sandbox applier folds in the
locally-discovered management plane and loads the ruleset.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from decepticon.sandbox_kernel.egress import (
    EgressPolicy,
    render_dns_allowlist,
    render_nftables,
)
from decepticon_core.types.roe import EnforcementMode, MachineEnforcement, ScopeRule


def _is_ip_or_cidr(token: str) -> bool:
    try:
        ipaddress.ip_network(token, strict=False)
        return True
    except ValueError:
        return False


def _classify(patterns: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split raw scope patterns into (ip/cidr literals, hostnames/globs)."""
    cidrs: list[str] = []
    hosts: list[str] = []
    for pat in patterns:
        (cidrs if _is_ip_or_cidr(pat) else hosts).append(pat)
    return tuple(cidrs), tuple(hosts)


def _rule_patterns(rules: Iterable[ScopeRule]) -> list[str]:
    return [r.pattern for r in rules]


def _norm(addrs: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({a for a in addrs if a}))


def compile_egress_policy(rules: MachineEnforcement) -> EgressPolicy:
    """Compile a ``MachineEnforcement`` block into an :class:`EgressPolicy`.

    ``enforce`` follows ENFORCE mode (audit / warn never touch the
    network). ``default_drop`` is set only when an in-scope allowlist
    exists — an enforce-mode RoE that lists only *denies* tightens those
    destinations without otherwise restricting egress, mirroring the
    parser's ``evaluate_target`` (which constrains to the allowlist only
    when ``in_scope`` is non-empty).
    """
    enforce = rules.mode == EnforcementMode.ENFORCE

    allowed_cidrs, allowed_hosts = _classify(_rule_patterns(rules.in_scope))
    denied_cidrs, denied_hosts = _classify(
        [*_rule_patterns(rules.out_of_scope), *rules.effective_forbidden_destinations()]
    )

    default_drop = enforce and bool(allowed_cidrs or allowed_hosts)

    return EgressPolicy(
        enforce=enforce,
        default_drop=default_drop,
        allowed_cidrs=_norm(allowed_cidrs),
        allowed_hosts=_norm(allowed_hosts),
        denied_cidrs=_norm(denied_cidrs),
        denied_hosts=_norm(denied_hosts),
    )


__all__ = [
    "EgressPolicy",
    "compile_egress_policy",
    "render_dns_allowlist",
    "render_nftables",
]
