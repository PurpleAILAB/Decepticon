"""Tests for ``decepticon-cli zip``."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

from decepticon.cli.__main__ import main as cli_main
from decepticon.cli.zip import (
    EXIT_CONFIG,
    EXIT_ERROR,
    EXIT_OK,
    export_engagement,
    import_engagement,
)
from decepticon.cli.zip import main as zip_main


def _seed_engagement(workspace: Path, engagement_id: str = "acme-2026") -> Path:
    """Create a realistic engagement directory tree under ``workspace``."""
    eng = workspace / "engagements" / engagement_id
    (eng / "kg").mkdir(parents=True)
    (eng / "audit").mkdir(parents=True)
    (eng / "events.jsonl").write_text('{"event": "start"}\n', encoding="utf-8")
    (eng / "kg" / "graph.json").write_text('{"nodes": []}', encoding="utf-8")
    (eng / "audit" / "roe-decisions.jsonl").write_text('{"decision": "allow"}\n', encoding="utf-8")
    return eng


def test_export_creates_archive_with_engagement_prefix(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _seed_engagement(ws)
    out = tmp_path / "out" / "acme.zip"

    count = export_engagement("acme-2026", ws, out)

    assert count == 3
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "acme-2026/events.jsonl" in names
    assert "acme-2026/kg/graph.json" in names
    assert "acme-2026/audit/roe-decisions.jsonl" in names


def test_export_missing_engagement_raises(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "engagements").mkdir(parents=True)
    try:
        export_engagement("nope", ws, tmp_path / "x.zip")
    except FileNotFoundError as exc:
        assert "engagement directory not found" in str(exc)
    else:  # pragma: no cover - guard
        raise AssertionError("expected FileNotFoundError")


def test_import_restores_files(tmp_path: Path) -> None:
    src_ws = tmp_path / "src"
    _seed_engagement(src_ws)
    archive = tmp_path / "acme.zip"
    export_engagement("acme-2026", src_ws, archive)

    dst_ws = tmp_path / "dst"
    engagement_id, restored = import_engagement(archive, dst_ws)

    assert engagement_id == "acme-2026"
    assert restored == 3
    eng = dst_ws / "engagements" / "acme-2026"
    assert (eng / "events.jsonl").read_text(encoding="utf-8") == '{"event": "start"}\n'
    assert (eng / "kg" / "graph.json").is_file()
    assert (eng / "audit" / "roe-decisions.jsonl").is_file()


def test_export_import_round_trip_via_cli(tmp_path: Path) -> None:
    src_ws = tmp_path / "src"
    _seed_engagement(src_ws)
    archive = tmp_path / "acme.zip"

    rc = zip_main(["export", "acme-2026", "--workspace", str(src_ws), "-o", str(archive)])
    assert rc == EXIT_OK
    assert archive.is_file()

    dst_ws = tmp_path / "dst"
    rc = zip_main(["import", str(archive), "--workspace", str(dst_ws)])
    assert rc == EXIT_OK
    assert (dst_ws / "engagements" / "acme-2026" / "events.jsonl").is_file()


def test_workspace_falls_back_to_env(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "ws"
    _seed_engagement(ws)
    archive = tmp_path / "acme.zip"
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(ws))

    rc = zip_main(["export", "acme-2026", "-o", str(archive)])

    assert rc == EXIT_OK
    assert archive.is_file()


def test_missing_workspace_is_config_error(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("DECEPTICON_ENGAGEMENT_WORKSPACE", raising=False)

    rc = zip_main(["export", "acme-2026", "-o", str(tmp_path / "x.zip")])

    assert rc == EXIT_CONFIG
    assert "workspace not set" in capsys.readouterr().err


def test_export_unknown_engagement_is_config_error(tmp_path: Path, capsys) -> None:
    ws = tmp_path / "ws"
    (ws / "engagements").mkdir(parents=True)

    rc = zip_main(["export", "ghost", "--workspace", str(ws), "-o", str(tmp_path / "x.zip")])

    assert rc == EXIT_CONFIG
    assert "engagement directory not found" in capsys.readouterr().err


def test_import_missing_archive_is_config_error(tmp_path: Path, capsys) -> None:
    rc = zip_main(["import", str(tmp_path / "absent.zip"), "--workspace", str(tmp_path / "ws")])

    assert rc == EXIT_CONFIG
    assert "archive not found" in capsys.readouterr().err


def test_import_non_zip_is_error(tmp_path: Path, capsys) -> None:
    bogus = tmp_path / "bogus.zip"
    bogus.write_text("not a zip", encoding="utf-8")

    rc = zip_main(["import", str(bogus), "--workspace", str(tmp_path / "ws")])

    assert rc == EXIT_ERROR
    assert "not a valid ZIP archive" in capsys.readouterr().err


def test_import_rejects_path_traversal(tmp_path: Path, capsys) -> None:
    malicious = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious, "w") as zf:
        zf.writestr("../escape.txt", "pwned")

    rc = zip_main(["import", str(malicious), "--workspace", str(tmp_path / "ws")])

    assert rc == EXIT_ERROR
    assert "unsafe path" in capsys.readouterr().err
    assert not (tmp_path / "escape.txt").exists()


def test_import_rejects_multiple_engagements(tmp_path: Path, capsys) -> None:
    multi = tmp_path / "multi.zip"
    with zipfile.ZipFile(multi, "w") as zf:
        zf.writestr("eng-a/events.jsonl", "{}\n")
        zf.writestr("eng-b/events.jsonl", "{}\n")

    rc = zip_main(["import", str(multi), "--workspace", str(tmp_path / "ws")])

    assert rc == EXIT_ERROR
    assert "exactly one engagement" in capsys.readouterr().err


def test_top_level_dispatcher_routes_zip(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _seed_engagement(ws)
    archive = tmp_path / "acme.zip"

    rc = cli_main(["zip", "export", "acme-2026", "--workspace", str(ws), "-o", str(archive)])

    assert rc == EXIT_OK
    assert archive.is_file()


def test_import_rejects_symlink_entry(tmp_path: Path, capsys) -> None:
    malicious = tmp_path / "link.zip"
    with zipfile.ZipFile(malicious, "w") as zf:
        info = zipfile.ZipInfo("acme-2026/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")

    rc = zip_main(["import", str(malicious), "--workspace", str(tmp_path / "ws")])

    assert rc == EXIT_ERROR
    assert "symlink entry not allowed" in capsys.readouterr().err
    assert not (tmp_path / "ws" / "engagements" / "acme-2026" / "link").exists()


def test_import_refuses_overwrite_without_force(tmp_path: Path, capsys) -> None:
    src_ws = tmp_path / "src"
    _seed_engagement(src_ws)
    archive = tmp_path / "acme.zip"
    export_engagement("acme-2026", src_ws, archive)

    dst_ws = tmp_path / "dst"
    import_engagement(archive, dst_ws)

    rc = zip_main(["import", str(archive), "--workspace", str(dst_ws)])

    assert rc == EXIT_ERROR
    assert "already exists" in capsys.readouterr().err


def test_import_force_replaces_stale_files(tmp_path: Path) -> None:
    src_ws = tmp_path / "src"
    _seed_engagement(src_ws)
    archive = tmp_path / "acme.zip"
    export_engagement("acme-2026", src_ws, archive)

    dst_ws = tmp_path / "dst"
    import_engagement(archive, dst_ws)
    stale = dst_ws / "engagements" / "acme-2026" / "stale.txt"
    stale.write_text("leftover", encoding="utf-8")

    engagement_id, restored = import_engagement(archive, dst_ws, force=True)

    assert engagement_id == "acme-2026"
    assert restored == 3
    assert not stale.exists()
    assert (dst_ws / "engagements" / "acme-2026" / "events.jsonl").is_file()
