from __future__ import annotations

import json

import pytest

from decepticon.tools.verification import validate_workspace_finding


class _Sandbox:
    async def execute_tmux_async(self, *, command: str, **_kwargs: object) -> str:
        if command == "positive":
            return "proof-marker\n[Exit code: 0]"
        if command == "negative":
            return "ordinary response\n[Exit code: 0]"
        return "unexpected\n[Exit code: 1]"


@pytest.mark.asyncio
async def test_workspace_verifier_requires_and_records_negative_control(monkeypatch) -> None:
    monkeypatch.setattr("decepticon.tools.verification.get_sandbox", _Sandbox)
    raw = await validate_workspace_finding.ainvoke(
        {
            "finding_id": "FIND-001",
            "poc_command": "positive",
            "success_patterns": "proof-marker",
            "negative_command": "negative",
            "negative_patterns": "ordinary response",
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        }
    )

    result = json.loads(raw)
    assert result["validated"] is True
    assert result["success_signals"] == ["proof-marker"]
    assert result["negative_signals"] == ["ordinary response"]


@pytest.mark.asyncio
async def test_workspace_verifier_rejects_missing_control_before_execution(monkeypatch) -> None:
    monkeypatch.setattr(
        "decepticon.tools.verification.get_sandbox",
        lambda: (_ for _ in ()).throw(AssertionError("sandbox must not run")),
    )

    raw = await validate_workspace_finding.ainvoke(
        {
            "finding_id": "FIND-001",
            "poc_command": "positive",
            "success_patterns": "proof-marker",
            "negative_command": "",
            "negative_patterns": "ordinary response",
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        }
    )

    assert json.loads(raw)["error"] == "mandatory verification fields are missing"
