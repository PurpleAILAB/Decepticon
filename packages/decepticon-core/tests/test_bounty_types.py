"""Dataclass shape + immutability tests for bug-bounty types."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from decepticon_core.types.bounty import (
    FindingSignature,
    Program,
    ReportDraft,
    ReportState,
    ReportStatus,
    SubmittedReport,
)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


class TestProgram:
    def test_required_fields(self) -> None:
        p = Program(
            platform="hackerone",
            handle="snapchat",
            name="Snap",
            payout_range=(100, 5000),
            avg_triage_days=7.0,
            bounty_table_url=None,
            scope_url="https://hackerone.com/snapchat",
            submission_endpoint="https://api.hackerone.com/v1/hackers/reports",
            requires_managed_account=False,
        )
        assert p.platform == "hackerone"
        assert p.payout_range == (100, 5000)

    def test_frozen(self) -> None:
        p = Program(
            platform="hackerone",
            handle="snapchat",
            name="Snap",
            payout_range=(100, 5000),
            avg_triage_days=None,
            bounty_table_url=None,
            scope_url="https://hackerone.com/snapchat",
            submission_endpoint="email:security@example.com",
            requires_managed_account=False,
        )
        with pytest.raises((AttributeError, TypeError)):
            p.handle = "evil"  # type: ignore[misc]


class TestFindingSignature:
    def test_basic(self) -> None:
        sig = FindingSignature(
            cwe="CWE-918",
            endpoint_canonical="GET https://api.snap.com/v1/users/{id}",
            poc_minimal_hash="a" * 64,
        )
        assert sig.cwe == "CWE-918"


class TestReportDraft:
    def test_attachments_default_empty(self) -> None:
        d = ReportDraft(
            title="t",
            severity_cvss="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
            summary="s",
            repro_steps=["one", "two"],
            poc_command="curl ...",
            affected_assets=["api.snap.com"],
            suggested_fix="patch",
            attachments={},
        )
        assert d.attachments == {}


class TestSubmittedReport:
    def test_basic(self) -> None:
        s = SubmittedReport(
            platform_report_id="1234",
            submitted_at=_utc(2026, 6, 3),
            submission_url="https://hackerone.com/reports/1234",
        )
        assert s.platform_report_id == "1234"


class TestReportStatus:
    def test_states_enum_literal(self) -> None:
        valid: set[ReportState] = {
            "new", "triaged", "needs_more_info", "duplicate",
            "informative", "resolved", "paid", "rejected",
        }
        for s in valid:
            rs = ReportStatus(
                state=s,
                payout_usd=None,
                triager_message=None,
                last_updated=_utc(2026, 6, 3),
            )
            assert rs.state == s
