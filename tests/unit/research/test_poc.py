"""Unit tests for PoC validation + CVSS computation."""

from __future__ import annotations

import pytest

from decepticon.tools.research.graph import (
    KnowledgeGraph,
    Node,
    NodeKind,
)
from decepticon.tools.research.poc import (
    AC,
    AV,
    PR,
    UI,
    CVSSVector,
    Impact,
    Scope,
    Severity,
    _match_signals,
    validate_poc,
)


class TestCVSSv31:
    def test_canonical_critical_rce(self) -> None:
        # AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H
        v = CVSSVector()
        assert v.base_score() == 9.8
        assert v.to_severity() == Severity.CRITICAL

    def test_scope_change_boosts_score(self) -> None:
        v = CVSSVector(scope=Scope.CHANGED)
        assert v.base_score() == 10.0

    def test_auth_required_medium(self) -> None:
        v = CVSSVector(pr=PR.LOW, c=Impact.LOW, i=Impact.NONE, a=Impact.NONE)
        # Authenticated low-impact
        assert 3.0 <= v.base_score() <= 5.0

    def test_no_impact_is_zero(self) -> None:
        v = CVSSVector(c=Impact.NONE, i=Impact.NONE, a=Impact.NONE)
        assert v.base_score() == 0.0
        assert v.to_severity() == Severity.INFO

    def test_vector_string_round_trip(self) -> None:
        v = CVSSVector(
            av=AV.NETWORK,
            ac=AC.LOW,
            pr=PR.NONE,
            ui=UI.NONE,
            scope=Scope.CHANGED,
            c=Impact.HIGH,
            i=Impact.HIGH,
            a=Impact.HIGH,
        )
        assert v.to_vector_string() == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"

    def test_severity_buckets(self) -> None:
        low = CVSSVector(c=Impact.LOW, i=Impact.NONE, a=Impact.NONE, pr=PR.HIGH)
        assert low.to_severity() in (Severity.LOW, Severity.MEDIUM)


class TestSignalMatching:
    def test_plain_string_match(self) -> None:
        assert _match_signals("uid=0(root)", ["uid=0", "root"]) == ["uid=0", "root"]

    def test_case_insensitive(self) -> None:
        assert _match_signals("ROOT", ["root"]) == ["root"]

    def test_regex_match(self) -> None:
        assert _match_signals("AccessKey: ABCDEFG", [r"AccessKey:\s+\w+"]) == [r"AccessKey:\s+\w+"]

    def test_no_match_returns_empty(self) -> None:
        assert _match_signals("nothing to see", ["pwned"]) == []

    def test_invalid_regex_falls_back_to_substring(self) -> None:
        # "[unclosed" is invalid regex — should still match as substring
        assert _match_signals("foo [unclosed bar", ["[unclosed"]) == ["[unclosed"]


class TestValidatePoc:
    @pytest.mark.asyncio
    async def test_happy_path_validates(self) -> None:
        async def runner(cmd: str) -> tuple[str, str, int]:
            return ("uid=0(root) gid=0(root)", "", 0)

        result = await validate_poc(
            vuln_id="vuln1",
            poc_command="id",
            success_patterns=["uid=0"],
            runner=runner,
        )
        assert result.validated is True
        assert "uid=0" in result.success_signals

    @pytest.mark.asyncio
    async def test_no_signal_fails(self) -> None:
        async def runner(cmd: str) -> tuple[str, str, int]:
            return ("nothing", "", 0)

        result = await validate_poc(
            vuln_id="vuln1",
            poc_command="id",
            success_patterns=["uid=0"],
            runner=runner,
        )
        assert result.validated is False

    @pytest.mark.asyncio
    async def test_negative_control_demotes(self) -> None:
        """If the baseline also matches the success pattern, we demote."""

        async def runner(cmd: str) -> tuple[str, str, int]:
            # BOTH payload and baseline return the same marker
            return ("marker found", "", 0)

        result = await validate_poc(
            vuln_id="vuln1",
            poc_command="curl /exploit",
            success_patterns=["marker"],
            runner=runner,
            negative_command="curl /baseline",
            negative_patterns=["marker"],
        )
        # Negative patterns matched → validated must be False
        assert result.validated is False

    @pytest.mark.asyncio
    async def test_cvss_attached_on_success(self) -> None:
        async def runner(cmd: str) -> tuple[str, str, int]:
            return ("pwned", "", 0)

        cvss = CVSSVector()
        result = await validate_poc(
            vuln_id="vuln1",
            poc_command="curl",
            success_patterns=["pwned"],
            runner=runner,
            cvss=cvss,
        )
        assert result.cvss is not None
        assert result.cvss_score == 9.8
        assert result.severity == "critical"

    @pytest.mark.asyncio
    async def test_persists_to_graph(self) -> None:
        g = KnowledgeGraph()
        vuln = g.upsert_node(Node.make(NodeKind.VULNERABILITY, "SSRF", severity="medium"))

        async def runner(cmd: str) -> tuple[str, str, int]:
            return ("root creds leaked AccessKeyId: ABCD", "", 0)

        cvss = CVSSVector(scope=Scope.CHANGED)
        result = await validate_poc(
            vuln_id=vuln.id,
            poc_command="curl /exploit",
            success_patterns=[r"AccessKeyId"],
            runner=runner,
            cvss=cvss,
            graph=g,
        )
        assert result.validated is True
        # Graph updated — validated flag set, severity upgraded
        updated = g.nodes[vuln.id]
        assert updated.props["validated"] is True
        assert updated.props["severity"] == "critical"
        assert updated.props["cvss_score"] == 10.0
        # Finding node created
        findings = g.by_kind(NodeKind.FINDING)
        assert len(findings) == 1
        assert findings[0].props["validated"] is True
