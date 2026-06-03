"""ScopeProvider — source of the active RoE MachineEnforcement.

Bug-bounty platform adapters, red-team RoE document loaders, and lab
manifest loaders all implement this Protocol so the orchestrator can
treat scope as a uniform input — the RoE middleware
(``decepticon.middleware.roe``) consumes the produced
``MachineEnforcement`` regardless of origin.

We deliberately reuse ``MachineEnforcement`` from
``decepticon_core.types.roe`` rather than introduce a new scope type.
Same enforcement primitive, same audit ledger, same forbidden-IMDS
defaults across pentest and bugbounty modes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from decepticon_core.types.roe import MachineEnforcement

__all__ = ["ScopeProvider"]


@runtime_checkable
class ScopeProvider(Protocol):
    """Source of RoE rules for the existing roe middleware."""

    scope_id: str
    """Stable identifier for audit logs (e.g. 'hackerone:snapchat')."""

    async def fetch_machine_enforcement(self) -> MachineEnforcement:
        """Return the RoE block to write into <workspace>/plan/roe.json.

        Empty in_scope or wide-open patterns are caught by the
        orchestrator's pre-flight (not by this method). Audit-mode is
        the default — providers should opt into ``enforce`` explicitly.
        """
        ...

    def rate_limit_hint(self) -> dict[str, float]:
        """Operational throttle hints (NOT enforced by RoE middleware).

        Keys (all optional, all float):
            ``requests_per_second`` — token-bucket fill rate
            ``reports_per_day`` — submission cap (bug-bounty only)
            ``status_poll_interval_seconds`` — polling cadence
            ``status_poll_jitter_seconds`` — uniform jitter to apply
        """
        ...
