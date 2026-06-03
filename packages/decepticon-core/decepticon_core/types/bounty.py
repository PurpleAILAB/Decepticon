"""Bug-bounty data types — shared between platform adapters,
the bugclaw orchestrator, and the saas web HITL UI.

These are pure dataclasses (frozen, slots). No behavior — adapters
and the orchestrator construct and read these; protocols/* defines
the methods that operate on them.

Note on ScopeRule: scope enforcement uses the existing
``decepticon_core.types.roe.MachineEnforcement`` + ``ScopeRule``
schema (see decepticon.middleware.roe). Bug-bounty platform adapters
produce a ``MachineEnforcement`` instance that the existing RoE
middleware consumes — no new scope types are defined here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

__all__ = [
    "FindingSignature",
    "Program",
    "ReportDraft",
    "ReportState",
    "ReportStatus",
    "SubmittedReport",
]


@dataclass(frozen=True, slots=True)
class Program:
    """One bug-bounty program (e.g. HackerOne's 'snapchat')."""

    platform: str
    handle: str
    name: str
    payout_range: tuple[int, int]      # (min_usd, max_usd) typical P3
    avg_triage_days: float | None
    bounty_table_url: str | None
    scope_url: str
    submission_endpoint: str           # URL or "email:..."
    requires_managed_account: bool     # True for invitation-only programs


@dataclass(frozen=True, slots=True)
class FindingSignature:
    """Stable hash-like view of a finding for dedupe."""

    cwe: str
    endpoint_canonical: str
    poc_minimal_hash: str              # sha256 hex of normalized PoC
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ReportDraft:
    """Pre-render finding payload. ReportTemplate.render → markdown body."""

    title: str
    severity_cvss: str
    summary: str
    repro_steps: list[str]
    poc_command: str
    affected_assets: list[str]
    suggested_fix: str
    attachments: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubmittedReport:
    """Returned by PlatformAdapter.submit_report."""

    platform_report_id: str
    submitted_at: datetime
    submission_url: str


ReportState = Literal[
    "new",
    "triaged",
    "needs_more_info",
    "duplicate",
    "informative",
    "resolved",
    "paid",
    "rejected",
]


@dataclass(frozen=True, slots=True)
class ReportStatus:
    """Snapshot of a submitted report's current state."""

    state: ReportState
    payout_usd: int | None
    triager_message: str | None
    last_updated: datetime
