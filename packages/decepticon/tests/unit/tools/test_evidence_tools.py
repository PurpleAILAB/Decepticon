from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.evidence import tools as evtools
from decepticon.tools.evidence.tools import (
    export_session_asciicast,
    list_session_recordings,
    seal_evidence,
    verify_evidence,
)


def _seed_evidence(workspace: Path) -> Path:
    evidence = workspace / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "a.txt").write_text("alpha", encoding="utf-8")
    sub = evidence / "captures"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"\x00\x01\x02beta")
    return evidence


def test_workspace_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECEPTICON_ENGAGEMENT_WORKSPACE", raising=False)
    assert evtools._workspace() == Path("/workspace")


def test_workspace_returns_path_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    assert evtools._workspace() == tmp_path


def test_evidence_dir_is_workspace_subpath(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    assert evtools._evidence_dir() == tmp_path / "evidence" / "recordings"


def test_json_helper_round_trips_dict() -> None:
    result = evtools._json({"k": 1})
    assert json.loads(result) == {"k": 1}


def test_export_session_asciicast_explicit_log_path_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    log_file = tmp_path / "cmd.log"
    log_file.write_text(
        "first\nDECEPTICON_PROMPT_END_xx\nsecond\nDECEPTICON_PROMPT_END_xx\n",
        encoding="utf-8",
    )
    result = json.loads(
        export_session_asciicast.invoke(
            {
                "session_name": "sess",
                "pipe_pane_log_path": str(log_file),
                "title": "My Title",
            }
        )
    )
    assert result["status"] == "exported"
    assert result["session_name"] == "sess"
    assert result["segments"] == 2
    cast_path = Path(result["asciicast_path"])
    assert cast_path == tmp_path / "evidence" / "recordings" / "sess.cast"
    assert cast_path.exists()
    sidecar = cast_path.with_suffix(cast_path.suffix + ".manifest.json")
    assert sidecar.exists()


def test_export_session_asciicast_fallback_tmux_log_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    tmux_logs_dir = tmp_path / ".tmux-logs"
    tmux_logs_dir.mkdir()
    log_file = tmux_logs_dir / "fb.log"
    log_file.write_text(
        "output\nDECEPTICON_PROMPT_END_xx\nmore\nDECEPTICON_PROMPT_END_xx\n",
        encoding="utf-8",
    )
    result = json.loads(export_session_asciicast.invoke({"session_name": "fb"}))
    assert result["status"] == "exported"
    assert (
        result["source_log"].endswith(".tmux-logs/fb.log")
        or result["source_log"] == str(log_file).replace("\\", "/")
        or Path(result["source_log"]) == log_file
    )


def test_export_session_asciicast_error_when_log_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    result = json.loads(export_session_asciicast.invoke({"session_name": "missing"}))
    assert "error" in result
    assert "status" not in result
    assert "pipe-pane log not found" in result["error"]


def test_list_session_recordings_empty_when_evidence_dir_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    result = json.loads(list_session_recordings.invoke({}))
    assert result == {"count": 0, "recordings": []}


def test_list_session_recordings_returns_manifests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    recordings_dir = tmp_path / "evidence" / "recordings"
    recordings_dir.mkdir(parents=True)
    (recordings_dir / "a.cast.manifest.json").write_text(
        json.dumps({"session_name": "a"}), encoding="utf-8"
    )
    (recordings_dir / "b.cast.manifest.json").write_text(
        json.dumps({"session_name": "b"}), encoding="utf-8"
    )
    result = json.loads(list_session_recordings.invoke({}))
    assert result["count"] == 2
    assert sorted(r["session_name"] for r in result["recordings"]) == ["a", "b"]


def test_seal_evidence_error_when_dir_missing(tmp_path: Path) -> None:
    result = json.loads(seal_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert "error" in result
    assert "status" not in result


def test_seal_evidence_writes_manifest_for_each_file(tmp_path: Path) -> None:
    _seed_evidence(tmp_path)
    result = json.loads(seal_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert result["status"] == "sealed"
    assert result["sealed"] == 2
    assert sorted(result["files"]) == ["a.txt", "captures/b.bin"]
    manifest = tmp_path / "evidence" / "chain-of-custody.jsonl"
    assert manifest.exists()
    records = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
    assert len(records) == 2
    assert records[0]["prev_hash"] == "0" * 64
    assert records[1]["prev_hash"] == records[0]["hash"]
    for rec in records:
        assert len(rec["sha256"]) == 64
        assert rec["size"] >= 0


def test_verify_evidence_ok_after_seal(tmp_path: Path) -> None:
    _seed_evidence(tmp_path)
    seal_evidence.invoke({"workspace_path": str(tmp_path)})
    result = json.loads(verify_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert result["ok"] is True
    assert result["records_checked"] == 2
    assert result["drift"] == []
    assert result["missing"] == []
    assert result["chain_errors"] == []


def test_verify_evidence_flags_drift_when_file_tampered(tmp_path: Path) -> None:
    evidence = _seed_evidence(tmp_path)
    seal_evidence.invoke({"workspace_path": str(tmp_path)})
    (evidence / "a.txt").write_text("TAMPERED", encoding="utf-8")
    result = json.loads(verify_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert result["ok"] is False
    drift_paths = [d["path"] for d in result["drift"]]
    assert "a.txt" in drift_paths


def test_verify_evidence_flags_missing_file(tmp_path: Path) -> None:
    evidence = _seed_evidence(tmp_path)
    seal_evidence.invoke({"workspace_path": str(tmp_path)})
    (evidence / "a.txt").unlink()
    result = json.loads(verify_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert result["ok"] is False
    assert "a.txt" in result["missing"]


def test_verify_evidence_error_when_manifest_absent(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    result = json.loads(verify_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert "error" in result


def test_verify_evidence_flags_hmac_chain_break(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECEPTICON_AUDIT_HMAC_KEY", "secret-key")
    _seed_evidence(tmp_path)
    seal_evidence.invoke({"workspace_path": str(tmp_path)})
    manifest = tmp_path / "evidence" / "chain-of-custody.jsonl"
    lines = manifest.read_text().splitlines()
    first = json.loads(lines[0])
    first["sha256"] = "0" * 64
    lines[0] = json.dumps(first)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = json.loads(verify_evidence.invoke({"workspace_path": str(tmp_path)}))
    assert result["ok"] is False
    assert result["chain_errors"]
