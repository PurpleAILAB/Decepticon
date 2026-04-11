"""Unit tests for the patch generation + verification module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.research import _state as state
from decepticon.tools.research.graph import (
    EdgeKind,
    Node,
    NodeKind,
    Severity,
    load_graph,
    save_graph,
)
from decepticon.tools.research.patch import patch_propose, patch_verify


def _configure_kg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    kg_path = tmp_path / "kg.json"
    monkeypatch.setenv("DECEPTICON_KG_PATH", str(kg_path))
    state._invalidate_kg_cache()
    return kg_path


def _seed_verified_vuln(kg_path: Path) -> str:
    """Plant a validated vuln node in the graph and return its id."""
    graph = load_graph(kg_path)
    vuln = Node.make(
        NodeKind.VULNERABILITY,
        "SQLi in product search",
        key="app.py:search_products:sqli",
        severity=Severity.HIGH.value,
        file="/workspace/target/app.py",
        line=42,
        validated=True,
        cvss_score=7.5,
    )
    graph.upsert_node(vuln)
    save_graph(graph, kg_path)
    state._invalidate_kg_cache()
    return vuln.id


class TestPatchPropose:
    def test_records_patch_node_and_edge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kg_path = _configure_kg(monkeypatch, tmp_path)
        vuln_id = _seed_verified_vuln(kg_path)

        raw = patch_propose.invoke(
            {
                "vuln_id": vuln_id,
                "diff": "--- a/app.py\n+++ b/app.py\n- old\n+ new\n",
                "commit_message": "fix(api): parameterize product search",
            }
        )
        result = json.loads(raw)
        assert result["vuln_id"] == vuln_id
        assert result["status"] == "proposed"

        graph = load_graph(kg_path)
        patch = graph.nodes[result["id"]]
        assert patch.kind == NodeKind.PATCH
        assert patch.props["status"] == "proposed"
        assert patch.props["applied"] is False
        assert patch.props["commit_message"] == "fix(api): parameterize product search"

        # PATCHES edge was created
        edges = [
            e
            for e in graph.edges.values()
            if e.src == patch.id and e.dst == vuln_id and e.kind == EdgeKind.PATCHES
        ]
        assert len(edges) == 1

    def test_rejects_unknown_vuln(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_kg(monkeypatch, tmp_path)
        raw = patch_propose.invoke(
            {
                "vuln_id": "does-not-exist",
                "diff": "",
                "commit_message": "noop",
            }
        )
        assert "error" in json.loads(raw)

    def test_idempotent_on_same_diff(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kg_path = _configure_kg(monkeypatch, tmp_path)
        vuln_id = _seed_verified_vuln(kg_path)
        diff = "--- a/x\n+++ b/x\n- 1\n+ 2\n"

        a = json.loads(
            patch_propose.invoke(
                {"vuln_id": vuln_id, "diff": diff, "commit_message": "fix: x"}
            )
        )
        b = json.loads(
            patch_propose.invoke(
                {"vuln_id": vuln_id, "diff": diff, "commit_message": "fix: x"}
            )
        )
        assert a["id"] == b["id"], "same vuln + same diff should dedupe"


class FakeSandbox:
    """Minimal stand-in for DockerSandbox that records commands and returns
    scripted output. Matches the ``execute_tmux_async`` interface the
    ``sandbox_runner`` adapter expects."""

    def __init__(self, scripts: list[tuple[str, int]]) -> None:
        # Ordered list of (stdout_blob, exit_code) to return per call.
        self.scripts = scripts
        self.commands: list[str] = []

    async def execute_tmux_async(
        self, command: str, session: str, timeout: int, is_input: bool
    ) -> str:
        self.commands.append(command)
        if not self.scripts:
            return "[Exit code: 0]"
        out, code = self.scripts.pop(0)
        return f"{out}\n[Exit code: {code}]"


@pytest.mark.asyncio
class TestPatchVerify:
    async def test_verified_flips_severity_to_info(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kg_path = _configure_kg(monkeypatch, tmp_path)
        vuln_id = _seed_verified_vuln(kg_path)

        proposed = json.loads(
            patch_propose.invoke(
                {
                    "vuln_id": vuln_id,
                    "diff": "diff",
                    "commit_message": "fix: sqli",
                }
            )
        )
        patch_id = proposed["id"]

        # PoC returns clean output that does NOT match the success pattern.
        fake = FakeSandbox(scripts=[("all good, no sql error", 0)])
        import importlib

        bash_mod = importlib.import_module("decepticon.tools.bash.bash")
        monkeypatch.setattr(bash_mod, "_sandbox", fake)

        raw = await patch_verify.ainvoke(
            {
                "patch_id": patch_id,
                "poc_command": "curl 'http://t/search?q=x%27'",
                "success_patterns": "sql syntax error,sqlite_master",
            }
        )
        result = json.loads(raw)
        assert result["status"] == "verified"
        assert result["poc_still_fires"] is False
        assert result["signals"] == []

        graph = load_graph(kg_path)
        vuln = graph.nodes[vuln_id]
        assert vuln.props["severity"] == Severity.INFO.value
        assert vuln.props["severity_before_patch"] == Severity.HIGH.value
        assert vuln.props["patched"] is True
        assert vuln.props["patched_by"] == patch_id

    async def test_regressed_leaves_vuln_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kg_path = _configure_kg(monkeypatch, tmp_path)
        vuln_id = _seed_verified_vuln(kg_path)

        proposed = json.loads(
            patch_propose.invoke(
                {"vuln_id": vuln_id, "diff": "bad fix", "commit_message": "fix: x"}
            )
        )
        patch_id = proposed["id"]

        # PoC output STILL contains the sqli error → regression.
        fake = FakeSandbox(scripts=[("sql syntax error near quote", 1)])
        import importlib

        bash_mod = importlib.import_module("decepticon.tools.bash.bash")
        monkeypatch.setattr(bash_mod, "_sandbox", fake)

        raw = await patch_verify.ainvoke(
            {
                "patch_id": patch_id,
                "poc_command": "curl 'http://t/?q=x%27'",
                "success_patterns": "sql syntax error",
            }
        )
        result = json.loads(raw)
        assert result["status"] == "regressed"
        assert result["poc_still_fires"] is True

        graph = load_graph(kg_path)
        vuln = graph.nodes[vuln_id]
        # Severity preserved — patcher has to retry.
        assert vuln.props["severity"] == Severity.HIGH.value
        assert vuln.props.get("patched") is not True

    async def test_tests_failed_short_circuits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kg_path = _configure_kg(monkeypatch, tmp_path)
        vuln_id = _seed_verified_vuln(kg_path)

        proposed = json.loads(
            patch_propose.invoke(
                {"vuln_id": vuln_id, "diff": "x", "commit_message": "fix"}
            )
        )
        patch_id = proposed["id"]

        # First call = tests, returns non-zero → short-circuits.
        fake = FakeSandbox(scripts=[("FAILED 3 tests", 1), ("should not run", 0)])
        import importlib

        bash_mod = importlib.import_module("decepticon.tools.bash.bash")
        monkeypatch.setattr(bash_mod, "_sandbox", fake)

        raw = await patch_verify.ainvoke(
            {
                "patch_id": patch_id,
                "poc_command": "never_runs",
                "success_patterns": "x",
                "test_cmd": "pytest -q",
            }
        )
        result = json.loads(raw)
        assert result["status"] == "tests_failed"
        assert result["tests_passed"] is False
        # PoC was never executed
        assert len(fake.commands) == 1
        assert "pytest" in fake.commands[0]
