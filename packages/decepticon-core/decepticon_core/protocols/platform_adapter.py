"""PlatformAdapter — one bug-bounty platform's worth of integration.

The bugclaw orchestrator interacts with bug-bounty platforms only
through this Protocol. Concrete implementations (HackerOneAdapter,
NaverAdapter, etc.) live in bug-bounty plugin packages (e.g.
``bugclaw.adapters.*``) and register via the
``decepticon.platform_adapters`` entry-point group (see
registry/platform_adapters.py).

Inheritance: extends ``ScopeProvider`` and ``IdentityProvider`` so a
single adapter object is the source of truth for scope rules, identity,
and submission.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from decepticon_core.protocols.identity_provider import IdentityProvider
from decepticon_core.protocols.scope_provider import ScopeProvider
from decepticon_core.types.bounty import (
    FindingSignature,
    Program,
    ReportDraft,
    ReportStatus,
    SubmittedReport,
)

__all__ = ["PlatformAdapter"]


@runtime_checkable
class PlatformAdapter(ScopeProvider, IdentityProvider, Protocol):
    """Full surface bugclaw orchestrator needs from a bounty platform."""

    platform_id: str
    """Registry key, e.g. ``"hackerone"``, ``"naver"``."""

    identity_handle: str
    """External account handle, e.g. ``"purpleailab"``."""

    report_template_id: str
    """Registry key of the default ReportTemplate to use, e.g.
    ``"hackerone-v1"``. Orchestrator may override per-finding."""

    # ─────────────── Discovery ───────────────

    async def list_programs(
        self,
        *,
        only_in_scope_for_handle: bool = True,
        min_payout_usd: int = 0,
    ) -> list[Program]:
        """Programs the current handle can hunt.

        Default filter: only programs whose policy allows
        ``identity_handle`` to participate (excludes private/invite-only
        we haven't been invited to).
        """
        ...

    # ─────────────── Dedupe ───────────────

    async def search_prior_reports(
        self,
        program: Program,
        signature: FindingSignature,
    ) -> list[dict]:
        """Search the platform for reports matching this signature.

        Includes our own historic reports and (where the platform
        exposes them) public hacktivity disclosures. Return shape is
        platform-specific; the orchestrator only checks emptiness.
        Empty list ⇒ no dupe ⇒ safe to draft.
        """
        ...

    # ─────────────── Submission ───────────────

    async def submit_report(
        self,
        program: Program,
        draft: ReportDraft,
        body_markdown: str,
        idempotency_key: str,
    ) -> SubmittedReport:
        """POST the report to the platform.

        ``idempotency_key`` is the orchestrator-supplied dedupe key the
        adapter MUST honor: a second call with the same key against a
        program where we've already submitted must return the original
        ``SubmittedReport`` (no double-submit). For platforms without
        native idempotency, the adapter maintains a local mapping.
        """
        ...

    # ─────────────── Status polling ───────────────

    async def fetch_report_status(
        self,
        report: SubmittedReport,
    ) -> ReportStatus:
        """Current state of a submitted report."""
        ...
