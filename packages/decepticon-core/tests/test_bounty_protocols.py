"""Structural conformance tests for the 4 bounty-platform Protocols.

Each Protocol is ``@runtime_checkable`` so isinstance() works on
concrete stand-ins.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from decepticon_core.protocols.identity_provider import IdentityProvider
from decepticon_core.protocols.platform_adapter import PlatformAdapter
from decepticon_core.protocols.report_template import ReportTemplate
from decepticon_core.protocols.scope_provider import ScopeProvider
from decepticon_core.types.bounty import (
    FindingSignature,
    Program,
    ReportDraft,
    ReportStatus,
    SubmittedReport,
)
from decepticon_core.types.roe import EnforcementMode, MachineEnforcement, ScopeRule


# ─────────────── ScopeProvider ───────────────


class _GoodScope:
    scope_id = "test:program"

    async def fetch_machine_enforcement(self) -> MachineEnforcement:
        return MachineEnforcement(
            mode=EnforcementMode.ENFORCE,
            in_scope=(ScopeRule(pattern="example.com"),),
        )

    def rate_limit_hint(self) -> dict[str, float]:
        return {"requests_per_second": 1.0}


class _BadScope:
    scope_id = "test:bad"

    async def fetch_machine_enforcement(self) -> MachineEnforcement:
        return MachineEnforcement()
    # missing rate_limit_hint


def test_scope_provider_satisfied() -> None:
    p: ScopeProvider = _GoodScope()
    assert isinstance(p, ScopeProvider)


def test_scope_provider_missing_method_rejected() -> None:
    assert not isinstance(_BadScope(), ScopeProvider)


@pytest.mark.asyncio
async def test_scope_provider_returns_enforcement() -> None:
    p = _GoodScope()
    me = await p.fetch_machine_enforcement()
    assert me.mode == EnforcementMode.ENFORCE
    assert me.in_scope[0].pattern == "example.com"


# ─────────────── IdentityProvider ───────────────


class _GoodIdentity:
    def outbound_user_agent(self, engagement_id: str) -> str:
        return f"test/0.1 (+local; eng={engagement_id})"

    def callback_domain_prefix(self) -> str:
        return "cb.test.local"


class _BadIdentity:
    def outbound_user_agent(self, engagement_id: str) -> str:
        return "x"
    # missing callback_domain_prefix


def test_identity_provider_satisfied() -> None:
    i: IdentityProvider = _GoodIdentity()
    assert isinstance(i, IdentityProvider)


def test_identity_provider_missing_method_rejected() -> None:
    assert not isinstance(_BadIdentity(), IdentityProvider)


def test_identity_ua_carries_eng_id() -> None:
    ua = _GoodIdentity().outbound_user_agent("eng-123")
    assert "eng=eng-123" in ua


# ─────────────── ReportTemplate ───────────────


class _GoodTemplate:
    template_id = "test-v1"

    def render(self, draft: ReportDraft, *, locale: str = "en") -> str:
        return f"# {draft.title}\n\n{draft.summary}\n"


def test_report_template_satisfied() -> None:
    t: ReportTemplate = _GoodTemplate()
    assert isinstance(t, ReportTemplate)


def test_report_template_render_uses_draft_fields() -> None:
    draft = ReportDraft(
        title="IDOR in /users",
        severity_cvss="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
        summary="Reading other users' messages",
        repro_steps=[],
        poc_command="",
        affected_assets=[],
        suggested_fix="",
        attachments={},
    )
    out = _GoodTemplate().render(draft)
    assert "IDOR in /users" in out
    assert "other users' messages" in out


# ─────────────── PlatformAdapter ───────────────


class _FakeAdapter:
    platform_id = "fake"
    identity_handle = "tester"
    report_template_id = "fake-v1"

    # ScopeProvider surface
    scope_id = "fake:active"

    async def fetch_machine_enforcement(self) -> MachineEnforcement:
        return MachineEnforcement(
            mode=EnforcementMode.ENFORCE,
            in_scope=(ScopeRule(pattern="example.test"),),
        )

    def rate_limit_hint(self) -> dict[str, float]:
        return {"requests_per_second": 2.0}

    # IdentityProvider surface
    def outbound_user_agent(self, engagement_id: str) -> str:
        return f"fake/0.1 (eng={engagement_id})"

    def callback_domain_prefix(self) -> str:
        return "callbacks.fake.test"

    # PlatformAdapter-specific
    async def list_programs(
        self, *, only_in_scope_for_handle: bool = True, min_payout_usd: int = 0,
    ) -> list[Program]:
        return []

    async def search_prior_reports(
        self, program: Program, signature: FindingSignature,
    ) -> list[dict]:
        return []

    async def submit_report(
        self,
        program: Program,
        draft: ReportDraft,
        body_markdown: str,
        idempotency_key: str,
    ) -> SubmittedReport:
        return SubmittedReport(
            platform_report_id="X",
            submitted_at=datetime.now(timezone.utc),
            submission_url="https://example.test/r/X",
        )

    async def fetch_report_status(
        self, report: SubmittedReport,
    ) -> ReportStatus:
        return ReportStatus(
            state="new",
            payout_usd=None,
            triager_message=None,
            last_updated=datetime.now(timezone.utc),
        )


def test_platform_adapter_satisfied() -> None:
    a: PlatformAdapter = _FakeAdapter()
    assert isinstance(a, PlatformAdapter)


def test_platform_adapter_also_satisfies_parent_protocols() -> None:
    a = _FakeAdapter()
    assert isinstance(a, ScopeProvider)
    assert isinstance(a, IdentityProvider)


@pytest.mark.asyncio
async def test_platform_adapter_smoke_flow() -> None:
    a = _FakeAdapter()
    assert await a.list_programs() == []
    me = await a.fetch_machine_enforcement()
    assert me.in_scope[0].pattern == "example.test"
    assert a.outbound_user_agent("e1") == "fake/0.1 (eng=e1)"
