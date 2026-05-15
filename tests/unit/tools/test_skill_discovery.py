"""Tests for ``list_skills`` and ``find_skill`` runtime discovery tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from decepticon.tools.skills import build_find_skill_tool, build_list_skills_tool


@dataclass
class _Result:
    error: str | None = None
    file_data: Any = None
    entries: list[str] | None = None


SKILL_FILES = {
    "/skills/recon/active.md": (
        "---\n"
        "name: active-recon\n"
        "description: nmap port scanning + service version detection\n"
        "when_to_use: nmap, port scan, service enumeration\n"
        "mitre: T1046\n"
        "---\n"
        "# active recon body\n"
    ),
    "/skills/recon/passive.md": (
        "---\n"
        "name: passive-recon\n"
        "description: subfinder, amass, OSINT discovery\n"
        "when_to_use: subdomain, OSINT, passive\n"
        "mitre: T1596\n"
        "---\n"
    ),
    "/skills/exploit/web/sqli.md": (
        "---\n"
        "name: sqli-exploit\n"
        "description: SQL injection identification + exploitation\n"
        "when_to_use: sqli, injection, sqlmap\n"
        "mitre: T1190\n"
        "---\n"
    ),
}


class _FakeBackend:
    """In-memory backend that mimics the deepagents BackendProtocol surface
    used by the discovery tools (``read``, ``ls``)."""

    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    def read(self, path: str) -> _Result:
        if path not in self._files:
            return _Result(error=f"missing: {path}", file_data=None)
        return _Result(error=None, file_data={"content": self._files[path]})

    def ls(self, dir_path: str) -> _Result:
        # Return entries that are either subdirectory names or .md files.
        prefix = dir_path.rstrip("/") + "/"
        children: set[str] = set()
        for path in self._files:
            if not path.startswith(prefix):
                continue
            tail = path[len(prefix) :]
            head = tail.split("/", 1)[0]
            children.add(head)
        return _Result(entries=sorted(children))


def _invoke(tool, **kwargs) -> str:
    payload = {
        "name": tool.name,
        "type": "tool_call",
        "id": "tc-1",
        "args": kwargs,
    }
    result = tool.invoke(payload)
    # The tool envelope returns a ToolMessage when invoked via tool_call;
    # plain (non-tool) tools return their string directly.
    return getattr(result, "content", result)


# ── list_skills ────────────────────────────────────────────────────


def test_list_skills_returns_all_under_source():
    backend = _FakeBackend(SKILL_FILES)
    list_skills = build_list_skills_tool(backend, ["/skills/"])
    out = _invoke(list_skills)
    assert "/skills/recon/active.md" in out
    assert "/skills/recon/passive.md" in out
    assert "/skills/exploit/web/sqli.md" in out
    assert "Skills available (3)" in out


def test_list_skills_filters_by_category():
    backend = _FakeBackend(SKILL_FILES)
    list_skills = build_list_skills_tool(backend, ["/skills/"])
    out = _invoke(list_skills, category="recon")
    assert "/skills/recon/active.md" in out
    assert "/skills/recon/passive.md" in out
    assert "/skills/exploit/web/sqli.md" not in out


def test_list_skills_empty_source_returns_message():
    backend = _FakeBackend({})
    list_skills = build_list_skills_tool(backend, ["/skills/"])
    out = _invoke(list_skills)
    assert "No skills found" in out


def test_list_skills_renders_descriptions():
    backend = _FakeBackend(SKILL_FILES)
    list_skills = build_list_skills_tool(backend, ["/skills/"])
    out = _invoke(list_skills)
    assert "nmap port scanning" in out
    assert "SQL injection" in out


# ── find_skill ─────────────────────────────────────────────────────


def test_find_skill_keyword_match():
    backend = _FakeBackend(SKILL_FILES)
    find_skill = build_find_skill_tool(backend, ["/skills/"])
    out = _invoke(find_skill, query="sqli")
    assert "/skills/exploit/web/sqli.md" in out
    assert "/skills/recon/active.md" not in out


def test_find_skill_ranks_by_match_count():
    backend = _FakeBackend(SKILL_FILES)
    find_skill = build_find_skill_tool(backend, ["/skills/"])
    out = _invoke(find_skill, query="sql injection")
    # SQLi skill mentions SQL twice + injection — should rank above all else
    lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert lines[0].startswith("- ") and "/skills/exploit/web/sqli.md" in lines[0]


def test_find_skill_includes_mitre_in_output():
    backend = _FakeBackend(SKILL_FILES)
    find_skill = build_find_skill_tool(backend, ["/skills/"])
    out = _invoke(find_skill, query="sqli")
    assert "T1190" in out


def test_find_skill_empty_query_rejected():
    backend = _FakeBackend(SKILL_FILES)
    find_skill = build_find_skill_tool(backend, ["/skills/"])
    out = _invoke(find_skill, query="   ")
    assert "query is required" in out


def test_find_skill_no_matches_message():
    backend = _FakeBackend(SKILL_FILES)
    find_skill = build_find_skill_tool(backend, ["/skills/"])
    out = _invoke(find_skill, query="zzz-nonexistent")
    assert "No matches" in out


def test_find_skill_max_results_caps_output():
    backend = _FakeBackend(SKILL_FILES)
    find_skill = build_find_skill_tool(backend, ["/skills/"])
    out = _invoke(find_skill, query="recon", max_results=1)
    bullets = [line for line in out.splitlines() if line.startswith("- (")]
    assert len(bullets) == 1


# ── allowlist enforcement ──────────────────────────────────────────


def test_list_skills_respects_source_allowlist():
    backend = _FakeBackend(SKILL_FILES)
    list_skills = build_list_skills_tool(backend, ["/skills/recon/"])
    out = _invoke(list_skills)
    assert "/skills/recon/active.md" in out
    assert "/skills/exploit/web/sqli.md" not in out


@pytest.mark.parametrize("tool_factory", [build_list_skills_tool, build_find_skill_tool])
def test_discovery_tools_degrade_on_backend_error(tool_factory):
    """A backend that raises every read still returns a printable message."""

    class _BrokenBackend:
        def read(self, _p: str) -> _Result:
            raise RuntimeError("boom")

        def ls(self, _p: str) -> _Result:
            raise RuntimeError("boom")

    tool = tool_factory(_BrokenBackend(), ["/skills/"])
    if tool.name == "list_skills":
        assert "No skills found" in _invoke(tool)
    else:
        assert "No matches" in _invoke(tool, query="anything")
