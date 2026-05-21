"""Tests for the Strix-style findings export pack."""

from __future__ import annotations

import json
import sys

import pytest

from decepticon.tools.reporting.findings_export import (
    FindingPack,
    slugify,
    write_finding_pack,
    write_findings_index,
)

# ── slugify ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("SQL Injection in /admin/users", "sql-injection-in-admin-users"),
        ("XSS via cookie\n value", "xss-via-cookie-value"),
        ("___messy___", "messy"),
        ("", "unnamed-finding"),
        ("a" * 100, "a" * 60),
        ("Café — résumé !!", "caf-r-sum"),
    ],
    ids=["typical", "newline", "underscores", "empty", "long", "non-ascii"],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


# ── write_finding_pack ────────────────────────────────────────────


def _basic_finding() -> dict:
    return {
        "id": "F-001",
        "props": {
            "title": "Reflected XSS in /search",
            "severity": "high",
            "cvss_score": 7.4,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
            "target": "https://example.com/search",
            "mitre": "T1059.007",
            "summary": "User-controlled query reflects unescaped",
            "steps": [
                "GET /search?q=<script>alert(1)</script>",
                "Observe alert dialog in browser",
            ],
            "poc": "curl -s 'https://example.com/search?q=<script>alert(1)</script>'",
            "poc_language": "bash",
            "references": ["https://owasp.org/xss"],
            "tags": ["web", "xss"],
        },
    }


def test_pack_creates_canonical_directory_layout(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    assert pack.root.exists()
    assert pack.root.is_dir()
    assert pack.root.parent == tmp_path
    # Slug + 8-char digest suffix from URL/title hash
    assert pack.root.name.startswith("reflected-xss-in-search-")
    assert (pack.root / "README.md").exists()
    assert (pack.root / "repro.md").exists()
    assert (pack.root / "manifest.json").exists()
    assert (pack.root / "evidence").is_dir()
    assert (pack.root / "poc.sh").exists()


def test_pack_readme_has_metadata(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    readme = (pack.root / "README.md").read_text()
    assert "Reflected XSS in /search" in readme
    assert "**Severity:** HIGH" in readme
    assert "CVSS:** 7.4" in readme
    assert "T1059.007" in readme


def test_pack_repro_renders_steps(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    body = (pack.root / "repro.md").read_text()
    assert "1. GET /search?q=" in body
    assert "2. Observe alert" in body


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Windows does not honor the executable mode bit",
)
def test_pack_poc_is_executable(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    poc = pack.root / "poc.sh"
    assert poc.read_text().startswith("curl -s")
    assert poc.stat().st_mode & 0o111  # executable bit set on POSIX


def test_pack_manifest_is_valid_json(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    payload = json.loads((pack.root / "manifest.json").read_text())
    assert payload["finding_id"] == "F-001"
    assert payload["severity"] == "high"
    assert payload["cvss_score"] == 7.4
    assert payload["tags"] == ["web", "xss"]


def test_pack_writes_evidence_files(tmp_path):
    evidence = [
        ("request.http", b"GET /search?q=<script> HTTP/1.1\nHost: example.com\n"),
        ("screenshot.png", b"\x89PNG\r\n\x1a\n... fake png"),
        ("logs.txt", "200 OK\n"),
    ]
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path, evidence=evidence)
    assert pack.evidence_count == 3
    ev_dir = pack.root / "evidence"
    assert (ev_dir / "request.http").read_bytes().startswith(b"GET")
    assert (ev_dir / "screenshot.png").read_bytes().startswith(b"\x89PNG")
    assert (ev_dir / "logs.txt").read_text() == "200 OK\n"


def test_pack_handles_string_steps(tmp_path):
    finding = _basic_finding()
    finding["props"]["steps"] = "step one\nstep two\n  \nstep three"
    pack = write_finding_pack(finding, output_root=tmp_path)
    body = (pack.root / "repro.md").read_text()
    assert "1. step one" in body
    assert "2. step two" in body
    assert "3. step three" in body


def test_pack_default_poc_when_missing(tmp_path):
    finding = _basic_finding()
    finding["props"].pop("poc")
    finding["props"].pop("poc_language", None)
    pack = write_finding_pack(finding, output_root=tmp_path)
    poc = (pack.root / "poc.sh").read_text()
    assert "TODO" in poc


@pytest.mark.parametrize(
    "language, expected_filename",
    [
        ("python", "poc.py"),
        ("javascript", "poc.js"),
        ("typescript", "poc.ts"),
        ("ruby", "poc.rb"),
        ("http", "poc.http"),
        ("raw", "poc.txt"),
        (None, "poc.sh"),
        ("unknown-lang", "poc.txt"),
    ],
)
def test_pack_picks_poc_extension_by_language(tmp_path, language, expected_filename):
    finding = _basic_finding()
    finding["props"]["poc_language"] = language
    finding["props"]["poc"] = "print('test')"
    pack = write_finding_pack(finding, output_root=tmp_path)
    assert (pack.root / expected_filename).exists()


def test_pack_flat_dict_accepted(tmp_path):
    """A flat dict (no ``props`` nesting) works just like a Node dump."""
    flat = {
        "id": "F-002",
        "title": "IDOR on /api/users/{id}",
        "severity": "medium",
        "summary": "missing auth check",
        "steps": ["GET /api/users/1 as user 2"],
        "poc": "curl -H 'Cookie: session=abc' https://x/api/users/1",
        "poc_language": "bash",
    }
    pack = write_finding_pack(flat, output_root=tmp_path)
    assert (pack.root / "README.md").read_text().startswith("# IDOR on")


def test_pack_overwrite_replaces_directory(tmp_path):
    finding = _basic_finding()
    pack1 = write_finding_pack(finding, output_root=tmp_path)
    stale = pack1.root / "stale.txt"
    stale.write_text("old data")
    pack2 = write_finding_pack(finding, output_root=tmp_path, overwrite=True)
    assert pack1.root == pack2.root
    assert not stale.exists()


def test_pack_no_overwrite_preserves_other_files(tmp_path):
    finding = _basic_finding()
    pack1 = write_finding_pack(finding, output_root=tmp_path)
    keep = pack1.root / "evidence" / "kept.txt"
    keep.write_text("keep me")
    pack2 = write_finding_pack(finding, output_root=tmp_path, overwrite=False)
    assert keep.exists()
    assert pack1.root == pack2.root
    # README is overwritten in place
    assert (pack2.root / "README.md").exists()


def test_pack_isolates_findings_with_same_title_different_url(tmp_path):
    a = _basic_finding()
    b = _basic_finding()
    b["props"]["target"] = "https://example.com/search?ref=other"
    pack_a = write_finding_pack(a, output_root=tmp_path)
    pack_b = write_finding_pack(b, output_root=tmp_path)
    assert pack_a.root != pack_b.root


def test_pack_unnamed_finding_still_writes(tmp_path):
    pack = write_finding_pack({}, output_root=tmp_path)
    assert pack.root.name.startswith("unnamed-finding")
    assert (pack.root / "README.md").exists()
    payload = json.loads((pack.root / "manifest.json").read_text())
    assert payload["severity"] == "unknown"


def test_pack_rejects_non_dict():
    with pytest.raises(TypeError):
        write_finding_pack("not a dict", output_root="/tmp")  # type: ignore[arg-type]


# ── findings index ────────────────────────────────────────────────


def test_index_renders_table(tmp_path):
    a = write_finding_pack(_basic_finding(), output_root=tmp_path)
    other = _basic_finding()
    other["props"]["title"] = "SSRF in webhook"
    other["props"]["severity"] = "critical"
    other["props"]["target"] = "https://example.com/webhook"
    b = write_finding_pack(other, output_root=tmp_path)
    index_path = write_findings_index([a, b], output_root=tmp_path)
    body = index_path.read_text()
    assert "# Findings Index" in body
    assert "SSRF in webhook" in body
    assert "Reflected XSS" in body
    assert "CRITICAL" in body
    assert "HIGH" in body


def test_index_skips_packs_with_missing_manifest(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    (pack.root / "manifest.json").unlink()
    index_path = write_findings_index([pack], output_root=tmp_path)
    body = index_path.read_text()
    # Header + table head still present, but no rows.
    assert "Reflected XSS" not in body
    assert "# Findings Index" in body


def test_index_idempotent(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    p1 = write_findings_index([pack], output_root=tmp_path)
    body1 = p1.read_text()
    p2 = write_findings_index([pack], output_root=tmp_path)
    assert p2 == p1
    assert p2.read_text() == body1


# ── return value ──────────────────────────────────────────────────


def test_pack_returns_finding_pack_dataclass(tmp_path):
    pack = write_finding_pack(_basic_finding(), output_root=tmp_path)
    assert isinstance(pack, FindingPack)
    assert pack.root.exists()
    assert len(pack.files_written) >= 4  # README, repro, poc, manifest
    info = pack.to_dict()
    assert "root" in info and "files_written" in info and "evidence_count" in info
