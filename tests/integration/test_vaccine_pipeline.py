"""Integration test scaffold for the Offensive Vaccine pipeline.

Smoke-tests the MentorMiddleware + VaccineMiddleware integration into
the decepticon orchestrator middleware stack. Uses a fake backend that
simulates per-finding JSON state transitions:

  validated=true       → expect VaccineMiddleware advisory "dispatch patcher"
  patched=true          → expect "dispatch defender"
  defended=true         → expect "dispatch ship"
  shipped=true          → expect None (terminal)

Repeated identical tool-calls → expect MentorMiddleware loop advisory.

These tests run the middleware hooks DIRECTLY without booting a full
LangGraph agent — fast (sub-second), no model calls, no docker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.messages import AIMessage


# ── Fakes ──────────────────────────────────────────────────────────


@dataclass
class FakeBackendResult:
    """Match the shape of DockerSandbox.ls/.read results."""

    error: str | None = None
    file_data: dict | None = None
    entries: list[str] = field(default_factory=list)


class FakeFindingsBackend:
    """In-memory backend simulating /workspace/findings/ contents."""

    def __init__(self, findings: dict[str, dict]) -> None:
        self._findings = findings

    def ls(self, path: str) -> FakeBackendResult:
        if path.rstrip("/") == "/workspace/findings":
            return FakeBackendResult(entries=list(self._findings.keys()))
        return FakeBackendResult(error=f"unknown path: {path}")

    def read(self, path: str) -> FakeBackendResult:
        name = path.rsplit("/", 1)[-1]
        if name in self._findings:
            return FakeBackendResult(
                file_data={"content": json.dumps(self._findings[name])}
            )
        return FakeBackendResult(error=f"not found: {path}")


def _ai_tool_call(tool: str, args: dict) -> AIMessage:
    """Build an AIMessage with one tool_call entry."""
    return AIMessage(
        content="",
        tool_calls=[{"name": tool, "args": args, "id": f"call_{tool}"}],
    )


# ── VaccineMiddleware integration tests ──────────────────────────


class TestVaccineMiddleware:
    """Direct middleware-level tests — no full LangGraph orchestrator."""

    def test_validated_findings_dispatch_patcher(self) -> None:
        from decepticon.middleware.vaccine import VaccineMiddleware
        backend = FakeFindingsBackend(
            {
                "FIND-001.json": {
                    "vuln_id": "FIND-001",
                    "validated": True,
                    "patched": False,
                }
            }
        )
        m = VaccineMiddleware(backend=backend)
        result = m.before_model({}, runtime=None)
        assert result is not None, "expected dispatch advisory"
        text = result["messages"][0].content
        assert "patcher" in text.lower()
        assert "FIND-001" in text

    def test_patched_findings_dispatch_defender(self) -> None:
        from decepticon.middleware.vaccine import VaccineMiddleware
        backend = FakeFindingsBackend(
            {
                "FIND-002.json": {
                    "vuln_id": "FIND-002",
                    "validated": True,
                    "patched": True,
                    "defended": False,
                }
            }
        )
        m = VaccineMiddleware(backend=backend)
        result = m.before_model({}, runtime=None)
        assert result is not None
        text = result["messages"][0].content
        assert "defender" in text.lower()
        assert "FIND-002" in text

    def test_defended_findings_dispatch_ship(self) -> None:
        from decepticon.middleware.vaccine import VaccineMiddleware
        backend = FakeFindingsBackend(
            {
                "FIND-003.json": {
                    "vuln_id": "FIND-003",
                    "validated": True,
                    "patched": True,
                    "defended": True,
                    "shipped": False,
                }
            }
        )
        m = VaccineMiddleware(backend=backend)
        result = m.before_model({}, runtime=None)
        assert result is not None
        text = result["messages"][0].content
        assert "ship" in text.lower() or "pr_from_patcher" in text.lower()
        assert "FIND-003" in text

    def test_terminal_finding_no_advisory(self) -> None:
        from decepticon.middleware.vaccine import VaccineMiddleware
        backend = FakeFindingsBackend(
            {
                "FIND-004.json": {
                    "vuln_id": "FIND-004",
                    "validated": True,
                    "patched": True,
                    "defended": True,
                    "shipped": True,
                }
            }
        )
        m = VaccineMiddleware(backend=backend)
        assert m.before_model({}, runtime=None) is None

    def test_unvalidated_finding_no_advisory(self) -> None:
        from decepticon.middleware.vaccine import VaccineMiddleware
        backend = FakeFindingsBackend(
            {
                "FIND-005.json": {
                    "vuln_id": "FIND-005",
                    "validated": False,
                }
            }
        )
        m = VaccineMiddleware(backend=backend)
        assert m.before_model({}, runtime=None) is None

    def test_cooldown_suppresses_repeat(self) -> None:
        from decepticon.middleware.vaccine import VaccineMiddleware
        backend = FakeFindingsBackend(
            {
                "FIND-006.json": {
                    "vuln_id": "FIND-006",
                    "validated": True,
                    "patched": False,
                }
            }
        )
        m = VaccineMiddleware(backend=backend, cooldown_turns=3)
        r1 = m.before_model({}, runtime=None)
        assert r1 is not None
        # Within cooldown — suppress
        for _ in range(2):
            assert m.before_model({}, runtime=None) is None
        # After cooldown
        r4 = m.before_model({}, runtime=None)
        assert r4 is not None


# ── MentorMiddleware integration tests ────────────────────────────


class TestMentorMiddlewareIntegration:
    """Sanity that Mentor + Vaccine can coexist in the same stack."""

    def test_mentor_fires_independently_of_vaccine(self) -> None:
        from decepticon.middleware.mentor import MentorMiddleware
        from decepticon.middleware.vaccine import VaccineMiddleware

        backend = FakeFindingsBackend({})  # no findings → Vaccine silent
        vaccine = VaccineMiddleware(backend=backend)
        mentor = MentorMiddleware(min_repeat_count=3)

        msgs = [_ai_tool_call("bash", {"cmd": "ls /tmp"}) for _ in range(3)]
        state = {"messages": msgs}

        v_out = vaccine.before_model(state, runtime=None)
        m_out = mentor.before_model(state, runtime=None)

        # Vaccine: no findings yet, silent
        assert v_out is None
        # Mentor: loop detected, advisory emitted
        assert m_out is not None
        assert "MENTOR" in m_out["messages"][0].content


# ── full-stack smoke (skipped by default — needs docker) ──────────


@pytest.mark.skip(reason="full-stack smoke requires docker-compose up + valid creds")
class TestVaccineEndToEnd:
    """E2E smoke against a real Decepticon engagement.

    Enable when running benchmark suites or release acceptance — runs
    the full Scanner -> Verifier -> Patcher -> Defender -> github_pr_*
    pipeline against a known-vulnerable benchmark target (e.g.
    XBEN-058 fixed-source mode).

    Asserts:
      1. At least one FINDING reaches validated=True
      2. VaccineMiddleware advisory observed in orchestrator log
      3. Defender promotes finding to defended=True with a
         verified rule
      4. github_pr_from_patcher + github_pr_from_defender are called
         on at least one finding (mocked to NOT actually push)
    """

    def test_full_pipeline_simulated(self) -> None:
        # Implementation deferred — needs benchmark target wiring.
        # When implemented, run: pytest -m e2e tests/integration/
        pass
