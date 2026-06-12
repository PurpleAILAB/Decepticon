"""Tests for ``decepticon-cli export-transcript``."""

from __future__ import annotations

from pathlib import Path

from decepticon.cli.__main__ import main as cli_main
from decepticon.cli.export_transcript import EXIT_NOT_FOUND, EXIT_OK
from decepticon.cli.export_transcript import main as export_main
from decepticon.runtime.event_log import EventLog, EventType


def _seed_engagement(workspace: Path, engagement_id: str = "eng-1") -> EventLog:
    log = EventLog(workspace_root=workspace, engagement_id=engagement_id)
    log.append(EventType.ENGAGEMENT_START, {"name": "demo-target"}, ts=1_700_000_000.0)
    log.append(
        EventType.AGENT_TURN,
        {"content": "Beginning reconnaissance of the target."},
        agent="recon",
        ts=1_700_000_001.0,
    )
    log.append(
        EventType.TOOL_CALL,
        {"tool": "nmap", "args": {"target": "10.0.0.1", "ports": "1-1024"}},
        agent="recon",
        ts=1_700_000_002.0,
    )
    log.append(
        EventType.TOOL_RESULT,
        {"tool": "nmap", "result": {"open_ports": [22, 80]}},
        agent="recon",
        ts=1_700_000_003.0,
    )
    log.append(EventType.ENGAGEMENT_END, {}, ts=1_700_000_004.0)
    return log


def test_export_to_stdout(tmp_path: Path, capsys) -> None:
    _seed_engagement(tmp_path)

    rc = export_main(["eng-1", "--workspace", str(tmp_path)])

    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert "# Engagement transcript: eng-1" in out
    assert "## Engagement started" in out
    assert "demo-target" in out
    assert "### recon" in out
    assert "Beginning reconnaissance of the target." in out
    assert "#### Tool call: `nmap`" in out
    assert '"target": "10.0.0.1"' in out
    assert "#### Tool result: `nmap`" in out
    assert '"open_ports"' in out
    assert "## Engagement ended" in out


def test_export_chronological_order(tmp_path: Path, capsys) -> None:
    _seed_engagement(tmp_path)

    export_main(["eng-1", "--workspace", str(tmp_path)])

    out = capsys.readouterr().out
    assert out.index("Engagement started") < out.index("recon")
    assert out.index("recon") < out.index("Tool call")
    assert out.index("Tool call") < out.index("Tool result")
    assert out.index("Tool result") < out.index("Engagement ended")


def test_export_to_output_file(tmp_path: Path) -> None:
    _seed_engagement(tmp_path)
    out_file = tmp_path / "reports" / "transcript.md"

    rc = export_main(["eng-1", "--workspace", str(tmp_path), "--output", str(out_file)])

    assert rc == EXIT_OK
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# Engagement transcript: eng-1" in text
    assert "nmap" in text


def test_workspace_defaults_to_env(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_engagement(tmp_path)
    monkeypatch.setenv("DECEPTICON_WORKSPACE", str(tmp_path))

    rc = export_main(["eng-1"])

    assert rc == EXIT_OK
    assert "# Engagement transcript: eng-1" in capsys.readouterr().out


def test_missing_engagement_returns_not_found(tmp_path: Path, capsys) -> None:
    rc = export_main(["ghost", "--workspace", str(tmp_path)])

    assert rc == EXIT_NOT_FOUND
    assert "event log not found" in capsys.readouterr().err


def test_generic_event_is_rendered(tmp_path: Path, capsys) -> None:
    log = EventLog(workspace_root=tmp_path, engagement_id="eng-2")
    log.append(EventType.FINDING_CREATED, {"id": "FIND-001"}, agent="exploit", ts=1_700_000_010.0)

    rc = export_main(["eng-2", "--workspace", str(tmp_path)])

    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert "finding.created (exploit)" in out
    assert "FIND-001" in out


def test_top_level_dispatcher_routes_export_transcript(tmp_path: Path, capsys) -> None:
    _seed_engagement(tmp_path)

    rc = cli_main(["export-transcript", "eng-1", "--workspace", str(tmp_path)])

    assert rc == EXIT_OK
    assert "# Engagement transcript: eng-1" in capsys.readouterr().out
