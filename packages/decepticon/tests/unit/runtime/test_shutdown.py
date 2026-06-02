"""Tests for ``decepticon.runtime.shutdown`` — bounded graceful shutdown.

Signal-handling behavior MUST run in subprocesses, never in the pytest
worker process, because installing SIGINT/SIGTERM handlers there would
break test isolation and could exit the whole test session.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_WINDOWS = os.name == "nt"


def _write_driver(
    workspace: Path,
    *,
    signal_name: str,
    delay_seconds: float = 0.1,
    create_events_jsonl: bool = False,
    findings_payload: str = "[]",
    objectives_payload: str = "[]",
) -> Path:
    """Render a self-contained driver script that installs handlers and self-signals.

    The driver writes nothing except via the shutdown handler under test, so
    the parent can assert behaviour purely from on-disk side effects.
    """
    if create_events_jsonl:
        (workspace / "events.jsonl").write_text("", encoding="utf-8")
    script = workspace / "_driver.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os
            import signal
            import sys
            import time

            from decepticon.runtime.shutdown import install_shutdown_handlers


            def _state():
                return {{
                    "workspace_path": r"{workspace.as_posix()}",
                    "engagement_name": "unit-shutdown",
                    "objectives": {objectives_payload},
                    "objective_counter": 1,
                    "threat_profile": "lab",
                    "pending_findings": {findings_payload},
                }}


            install_shutdown_handlers(_state)
            time.sleep({delay_seconds})
            os.kill(os.getpid(), signal.{signal_name})
            time.sleep(10)
            sys.exit(99)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return script


def _run_driver(script: Path, *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.mark.skipif(_WINDOWS, reason="POSIX self-signal test; Windows uses console events")
def test_sigint_flushes_findings_opplan_partial_executive_and_exits_130(tmp_path: Path) -> None:
    findings = json.dumps(
        [
            {
                "title": "Open redirect on /login",
                "severity": "medium",
                "summary": "Reflected query param redirects to attacker host.",
                "evidence": {"url": "https://target/login?next=//evil"},
            }
        ]
    )
    objectives = json.dumps([{"id": "OBJ-001", "title": "Map external surface"}])
    script = _write_driver(
        tmp_path,
        signal_name="SIGINT",
        findings_payload=findings,
        objectives_payload=objectives,
    )

    proc = _run_driver(script)

    assert proc.returncode == 130, proc.stderr
    finding_path = tmp_path / "findings" / "FIND-001.md"
    opplan_path = tmp_path / "plan" / "opplan.json"
    executive_path = tmp_path / "report" / "report_partial_executive.md"
    assert finding_path.exists()
    body = finding_path.read_text(encoding="utf-8")
    assert "Open redirect on /login" in body
    assert "MEDIUM" in body
    assert opplan_path.exists()
    opplan = json.loads(opplan_path.read_text(encoding="utf-8"))
    assert opplan["objectives"][0]["id"] == "OBJ-001"
    assert opplan["engagement_name"] == "unit-shutdown"
    assert executive_path.exists()
    assert "unit-shutdown" in executive_path.read_text(encoding="utf-8")
    assert "[shutdown] SIGINT:" in proc.stdout


@pytest.mark.skipif(
    _WINDOWS or not hasattr(signal, "SIGTERM"),
    reason="POSIX SIGTERM test",
)
def test_sigterm_exits_143(tmp_path: Path) -> None:
    script = _write_driver(
        tmp_path,
        signal_name="SIGTERM",
        findings_payload="[]",
        objectives_payload="[]",
    )

    proc = _run_driver(script)

    assert proc.returncode == 143, proc.stderr


@pytest.mark.skipif(_WINDOWS, reason="POSIX self-signal test")
def test_existing_findings_get_next_id(tmp_path: Path) -> None:
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    (findings_dir / "FIND-001.md").write_text("# pre-existing\n", encoding="utf-8")
    (findings_dir / "FIND-007.md").write_text("# pre-existing 7\n", encoding="utf-8")

    findings = json.dumps([{"title": "New finding", "severity": "low"}])
    script = _write_driver(
        tmp_path, signal_name="SIGINT", findings_payload=findings, objectives_payload="[]"
    )

    proc = _run_driver(script)

    assert proc.returncode == 130, proc.stderr
    assert (findings_dir / "FIND-008.md").exists()
    assert (findings_dir / "FIND-001.md").read_text(encoding="utf-8").startswith("# pre-existing")


@pytest.mark.skipif(_WINDOWS, reason="POSIX self-signal test")
def test_events_jsonl_checkpoint_appended_when_file_present(tmp_path: Path) -> None:
    script = _write_driver(
        tmp_path,
        signal_name="SIGINT",
        create_events_jsonl=True,
        findings_payload="[]",
        objectives_payload="[]",
    )

    proc = _run_driver(script)

    assert proc.returncode == 130, proc.stderr
    events_path = tmp_path / "events.jsonl"
    lines = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    assert lines[0]["type"] == "engagement.checkpoint"
    assert lines[0]["reason"] == "signal"
    assert lines[0]["signal"] == "SIGINT"


@pytest.mark.skipif(_WINDOWS, reason="POSIX self-signal test")
def test_no_events_jsonl_means_no_event_file_created(tmp_path: Path) -> None:
    script = _write_driver(
        tmp_path,
        signal_name="SIGINT",
        create_events_jsonl=False,
        findings_payload="[]",
        objectives_payload="[]",
    )

    proc = _run_driver(script)

    assert proc.returncode == 130, proc.stderr
    assert not (tmp_path / "events.jsonl").exists()


@pytest.mark.skipif(_WINDOWS, reason="POSIX self-signal test")
def test_double_signal_within_window_forces_immediate_exit(tmp_path: Path) -> None:
    script = tmp_path / "_double.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os
            import signal
            import time

            from decepticon.runtime.shutdown import install_shutdown_handlers


            def _state():
                time.sleep(3)
                return {{"workspace_path": r"{tmp_path.as_posix()}"}}


            install_shutdown_handlers(_state)
            time.sleep(0.1)
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.3)
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(10)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    proc = _run_driver(script, timeout=15.0)

    assert proc.returncode == 130, proc.stderr


@pytest.mark.skipif(_WINDOWS, reason="POSIX self-signal test")
def test_missing_workspace_path_does_not_hang(tmp_path: Path) -> None:
    script = tmp_path / "_noworkspace.py"
    script.write_text(
        textwrap.dedent(
            """
            import os
            import signal
            import sys
            import time

            from decepticon.runtime.shutdown import install_shutdown_handlers


            def _state():
                return {}


            install_shutdown_handlers(_state)
            time.sleep(0.1)
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(10)
            sys.exit(99)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    proc = _run_driver(script, timeout=15.0)

    assert proc.returncode == 130, proc.stderr
    assert "no workspace" in proc.stdout


def test_install_shutdown_handlers_is_idempotent() -> None:
    """In-process API test: repeated install with same/new provider does not raise."""
    from decepticon.runtime.shutdown import install_shutdown_handlers

    def _state_a() -> dict:
        return {}

    def _state_b() -> dict:
        return {"workspace_path": "/tmp/example"}

    install_shutdown_handlers(_state_a)
    install_shutdown_handlers(_state_b)
    install_shutdown_handlers(_state_a)


def test_fallback_executive_used_when_no_graph(tmp_path: Path) -> None:
    """The handler must write a fallback executive markdown rather than skip."""
    if _WINDOWS:
        pytest.skip("POSIX self-signal test")
    script = _write_driver(
        tmp_path,
        signal_name="SIGINT",
        findings_payload="[]",
        objectives_payload="[]",
    )

    proc = _run_driver(script)

    assert proc.returncode == 130, proc.stderr
    executive_path = tmp_path / "report" / "report_partial_executive.md"
    assert executive_path.exists()
    body = executive_path.read_text(encoding="utf-8")
    assert "Partial Executive Summary" in body
    assert "no knowledge graph in state" in body


class TestFlushLogicInProcess:
    """Direct unit tests for the flush helpers — cross-platform; no real signals."""

    def test_run_flush_writes_finding_opplan_and_executive(self, tmp_path: Path) -> None:
        from decepticon.runtime import shutdown as mod

        state = {
            "workspace_path": str(tmp_path),
            "engagement_name": "in-proc-test",
            "objectives": [{"id": "OBJ-001", "title": "Map"}],
            "objective_counter": 1,
            "threat_profile": "lab",
            "pending_findings": [
                {
                    "title": "SSRF in /proxy",
                    "severity": "high",
                    "summary": "Server fetches arbitrary URLs.",
                    "evidence": {"url": "https://target/proxy?url=http://169.254.169.254/"},
                }
            ],
        }
        mod._state_provider = lambda: state

        result = mod._run_flush("SIGINT", deadline=time_monotonic_plus(5))

        assert result.workspace == tmp_path
        assert result.findings_written == 1
        assert result.opplan_written is True
        assert result.partial_executive_written is True
        assert (tmp_path / "findings" / "FIND-001.md").exists()
        assert (tmp_path / "plan" / "opplan.json").exists()
        assert (tmp_path / "report" / "report_partial_executive.md").exists()

    def test_run_flush_with_no_workspace_returns_empty_result(self, tmp_path: Path) -> None:
        from decepticon.runtime import shutdown as mod

        mod._state_provider = lambda: {}
        result = mod._run_flush("SIGINT", deadline=time_monotonic_plus(5))

        assert result.workspace is None
        assert result.findings_written == 0
        assert result.opplan_written is False
        assert result.partial_executive_written is False

    def test_run_flush_continues_after_one_write_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from decepticon.runtime import shutdown as mod

        state = {
            "workspace_path": str(tmp_path),
            "engagement_name": "err-test",
            "objectives": [{"id": "OBJ-001"}],
            "pending_findings": [{"title": "x", "severity": "low"}],
        }
        mod._state_provider = lambda: state

        def _broken(*_args: object, **_kwargs: object) -> int:
            raise RuntimeError("disk full")

        monkeypatch.setattr(mod, "_write_inflight_findings", _broken)

        result = mod._run_flush("SIGINT", deadline=time_monotonic_plus(5))

        assert result.workspace == tmp_path
        assert result.findings_written == 0
        assert result.opplan_written is True
        assert any("findings:" in e for e in result.errors)

    def test_existing_findings_offset_next_id(self, tmp_path: Path) -> None:
        from decepticon.runtime import shutdown as mod

        findings_dir = tmp_path / "findings"
        findings_dir.mkdir()
        (findings_dir / "FIND-001.md").write_text("# old", encoding="utf-8")
        (findings_dir / "FIND-003.md").write_text("# old", encoding="utf-8")
        (findings_dir / "FIND-notanumber.md").write_text("# old", encoding="utf-8")

        next_id = mod._next_finding_id(findings_dir)

        assert next_id == 4

    def test_finding_markdown_includes_severity_and_summary(self) -> None:
        from decepticon.runtime import shutdown as mod

        body = mod._finding_markdown(
            {
                "title": "Reflected XSS in search",
                "severity": "high",
                "summary": "Unencoded user input rendered as HTML.",
                "evidence": {"url": "https://target/search?q=<script>"},
            }
        )

        assert "# Reflected XSS in search" in body
        assert "HIGH" in body
        assert "Unencoded user input" in body
        assert "https://target/search" in body

    def test_events_jsonl_event_appended_when_file_exists(self, tmp_path: Path) -> None:
        from decepticon.runtime import shutdown as mod

        events = tmp_path / "events.jsonl"
        events.write_text("", encoding="utf-8")
        state = {"workspace_path": str(tmp_path)}
        result = mod._FlushResult(
            workspace=tmp_path,
            findings_written=2,
            opplan_written=True,
            partial_executive_written=True,
        )

        written = mod._write_checkpoint_event_if_available(state, tmp_path, result, "SIGINT")

        assert written is True
        lines = events.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["type"] == "engagement.checkpoint"
        assert entry["signal"] == "SIGINT"
        assert entry["findings_written"] == 2

    def test_events_jsonl_skipped_when_file_absent(self, tmp_path: Path) -> None:
        from decepticon.runtime import shutdown as mod

        result = mod._FlushResult(workspace=tmp_path)
        written = mod._write_checkpoint_event_if_available(
            {"workspace_path": str(tmp_path)}, tmp_path, result, "SIGINT"
        )

        assert written is False
        assert not (tmp_path / "events.jsonl").exists()

    def test_atomic_write_uses_tmp_then_replace(self, tmp_path: Path) -> None:
        from decepticon.runtime import shutdown as mod

        target = tmp_path / "out" / "file.md"
        mod._write_atomic(target, "hello\n")

        assert target.read_text(encoding="utf-8") == "hello\n"
        assert not (tmp_path / "out" / "file.md.tmp").exists()


def time_monotonic_plus(seconds: float) -> float:
    """Helper: monotonic-clock deadline ``seconds`` from now."""
    import time

    return time.monotonic() + seconds


class TestPerComponentTimeout:
    """Each ``_write_*`` step must be bounded so one hung writer cannot
    consume the whole flush deadline and starve the remaining steps."""

    def test_hung_component_is_bounded_and_others_still_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time as _time

        from decepticon.runtime import shutdown as mod

        monkeypatch.setattr(mod, "PER_COMPONENT_FLUSH_SECONDS", 0.2, raising=False)

        state = {
            "workspace_path": str(tmp_path),
            "engagement_name": "hang-test",
            "objectives": [{"id": "OBJ-001"}],
            "objective_counter": 1,
            "pending_findings": [{"title": "x", "severity": "low"}],
        }
        mod._state_provider = lambda: state

        def _hang(*_args: object, **_kwargs: object) -> int:
            _time.sleep(5.0)
            return 0

        monkeypatch.setattr(mod, "_write_inflight_findings", _hang)

        start = _time.monotonic()
        result = mod._run_flush("SIGINT", deadline=_time.monotonic() + 4.0)
        elapsed = _time.monotonic() - start

        # Hung step must be bounded — well under the total 4 s deadline.
        assert elapsed < 2.0, f"flush stalled for {elapsed:.2f}s"
        # Hung step is recorded as errored, with zero side effects.
        assert result.findings_written == 0
        assert any("findings" in e for e in result.errors), result.errors
        # Subsequent steps must still execute and persist their output.
        assert result.opplan_written is True
        assert result.partial_executive_written is True
        assert (tmp_path / "plan" / "opplan.json").exists()
        assert (tmp_path / "report" / "report_partial_executive.md").exists()
