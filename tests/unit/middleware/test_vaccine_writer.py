"""Unit tests for VaccineWriter — stage-transition writes.

Uses an in-memory fake backend matching the deepagents backend protocol
shape: ``ls(dir)`` / ``read(path)`` / ``write(path, content)`` all return
result objects with optional ``error`` + ``file_data`` attributes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from decepticon.middleware.vaccine import VaccineMiddleware
from decepticon.middleware.vaccine_writer import VaccineWriter


@dataclass
class _FakeResult:
    error: str | None = None
    file_data: dict[str, Any] = field(default_factory=dict)


class _FakeBackend:
    """In-memory file backend matching the deepagents protocol shape."""

    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def ls(self, path: str) -> _FakeResult:
        prefix = path.rstrip("/") + "/"
        entries = [p[len(prefix):] for p in self._files if p.startswith(prefix)]
        return _FakeResult(file_data={"entries": entries})

    def read(self, path: str) -> _FakeResult:
        if path not in self._files:
            return _FakeResult(error="not found")
        return _FakeResult(file_data={"content": self._files[path]})

    def write(self, path: str, content: str) -> _FakeResult:
        self._files[path] = content
        return _FakeResult()


@pytest.fixture
def backend() -> _FakeBackend:
    return _FakeBackend()


@pytest.fixture
def writer(backend: _FakeBackend) -> VaccineWriter:
    return VaccineWriter(backend=backend, findings_dir="/workspace/findings")


def _load(backend: _FakeBackend, finding_id: str) -> dict:
    return json.loads(backend._files[f"/workspace/findings/{finding_id}.json"])


def test_create_then_progress(writer: VaccineWriter, backend: _FakeBackend) -> None:
    """End-to-end progression validated → patched → defended → shipped."""
    r = writer.create("FIND-001", title="SQLi in /login", bug_class="sqli")
    assert r.ok
    assert r.stage == "create"
    doc = _load(backend, "FIND-001")
    assert doc["validated"] is False
    assert doc["patched"] is False
    assert doc["title"] == "SQLi in /login"

    assert writer.mark_validated("FIND-001", evidence="/workspace/evidence/FIND-001.json").ok
    assert _load(backend, "FIND-001")["validated"] is True

    assert writer.mark_patched(
        "FIND-001",
        diff_path="/workspace/patches/FIND-001.diff",
        commit_sha="abc1234",
    ).ok
    doc = _load(backend, "FIND-001")
    assert doc["patched"] is True
    assert doc["commit_sha"] == "abc1234"

    assert writer.mark_defended(
        "FIND-001",
        rule_path="/workspace/rules/FIND-001.sigma.yml",
        rule_format="sigma",
    ).ok
    assert _load(backend, "FIND-001")["defended"] is True

    r = writer.mark_shipped(
        "FIND-001",
        patch_pr_url="https://github.com/PurpleAILAB/Decepticon/pull/999",
        detection_pr_url="https://github.com/SigmaHQ/sigma/pull/4242",
    )
    assert r.ok
    doc = _load(backend, "FIND-001")
    assert doc["shipped"] is True
    assert doc["patch_pr_url"].endswith("/pull/999")
    assert doc["detection_pr_url"].endswith("/pull/4242")


def test_create_is_idempotent(writer: VaccineWriter) -> None:
    assert writer.create("FIND-002").ok
    second = writer.create("FIND-002")
    assert not second.ok
    assert "exists" in (second.error or "")


def test_auto_create_on_first_transition(writer: VaccineWriter, backend: _FakeBackend) -> None:
    """If patcher fires before scanner created the finding, transition still works."""
    r = writer.mark_validated("FIND-003", source="auto")
    assert r.ok
    doc = _load(backend, "FIND-003")
    assert doc["validated"] is True
    assert doc["patched"] is False
    assert doc["source"] == "auto"


def test_idempotent_transition(writer: VaccineWriter, backend: _FakeBackend) -> None:
    """Re-flipping an already-set stage is a no-op merge, not an error."""
    writer.create("FIND-004")
    writer.mark_validated("FIND-004", first_pass="yes")
    first_at = _load(backend, "FIND-004")["validated_at"]
    r = writer.mark_validated("FIND-004", second_pass="yes")
    assert r.ok
    doc = _load(backend, "FIND-004")
    # Timestamp preserved from first flip (idempotent)
    assert doc["validated_at"] == first_at
    # New fields merged
    assert doc["second_pass"] == "yes"
    assert doc["first_pass"] == "yes"


def test_unknown_stage_rejected(writer: VaccineWriter) -> None:
    r = writer._transition("FIND-005", "exploited")
    assert not r.ok
    assert "unknown stage" in (r.error or "")


def test_filename_with_extension_accepted(writer: VaccineWriter, backend: _FakeBackend) -> None:
    writer.create("FIND-006.json")
    assert "/workspace/findings/FIND-006.json" in backend._files


def test_get_returns_none_on_missing(writer: VaccineWriter) -> None:
    assert writer.get("FIND-999") is None


def test_middleware_writer_property_shares_backend(backend: _FakeBackend) -> None:
    """VaccineMiddleware.writer must share its backend so the watcher sees writes."""
    mw = VaccineMiddleware(backend=backend, findings_dir="/workspace/findings")
    w = mw.writer
    assert w is mw.writer  # cached
    w.create("FIND-100")
    w.mark_validated("FIND-100")
    # Watcher sees the validated-but-not-patched finding
    files = mw._list_finding_files()
    assert "FIND-100.json" in files
    data = mw._read_finding("FIND-100.json")
    assert data is not None and data["validated"] is True
    assert mw._next_stage(data) == "patcher"
