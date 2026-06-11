"""Tests for the PLAYBOOK.md → :Playbook composition-plane builder pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.skillogy.builder.playbooks import emit_playbook_records
from decepticon.skillogy.builder.seeds import load_phases
from decepticon.skillogy.builder.skills import emit_skill_records

_SKILLS_ROOT = Path("packages/decepticon/decepticon/skills")


def _write_playbook(root: Path, name: str, steps: list[str], phase: str | None = None) -> None:
    d = root / "playbooks" / name
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}", 'description: "a test playbook"', "metadata:"]
    if phase is not None:
        lines.append(f"  phase: {phase}")
    lines.append("  steps:")
    lines.extend(f"    - {s}" for s in steps)
    lines += ["---", "", "# Body", ""]
    (d / "PLAYBOOK.md").write_text("\n".join(lines), encoding="utf-8")


class TestEmitPlaybookRecords:
    def test_emits_node_and_ordered_steps(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "demo", ["alpha", "beta", "gamma"], phase="reconnaissance")
        nodes, edges = emit_playbook_records(
            tmp_path,
            skill_names={"alpha", "beta", "gamma"},
            phase_names={"reconnaissance"},
        )
        pb = [n for n in nodes if n.label == "Playbook"]
        assert len(pb) == 1
        assert pb[0].properties["name"] == "demo"
        assert pb[0].properties["path"] == "/skills/playbooks/demo/PLAYBOOK.md"
        assert pb[0].properties["step_count"] == 3

        steps = sorted(
            (e for e in edges if e.edge_type == "STEP"),
            key=lambda e: e.properties["order"],
        )
        assert [e.to_key for e in steps] == ["alpha", "beta", "gamma"]
        assert [e.properties["order"] for e in steps] == [1, 2, 3]

        in_phase = [e for e in edges if e.edge_type == "IN_PHASE"]
        assert len(in_phase) == 1
        assert in_phase[0].to_key == "reconnaissance"

    def test_no_phase_omits_in_phase_edge(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "demo", ["alpha"])
        _nodes, edges = emit_playbook_records(tmp_path, skill_names={"alpha"})
        assert [e for e in edges if e.edge_type == "IN_PHASE"] == []

    def test_unknown_skill_reference_raises(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "demo", ["alpha", "ghost"])
        with pytest.raises(RuntimeError, match="unknown skills"):
            emit_playbook_records(tmp_path, skill_names={"alpha"})

    def test_unknown_phase_raises(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "demo", ["alpha"], phase="not-a-phase")
        with pytest.raises(RuntimeError, match="unknown phase"):
            emit_playbook_records(tmp_path, skill_names={"alpha"}, phase_names={"reconnaissance"})

    def test_duplicate_steps_raise(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "demo", ["alpha", "alpha"])
        with pytest.raises(RuntimeError, match="duplicate steps"):
            emit_playbook_records(tmp_path, skill_names={"alpha"})

    def test_empty_steps_raise(self, tmp_path: Path) -> None:
        _write_playbook(tmp_path, "demo", [])
        with pytest.raises(RuntimeError, match="no steps"):
            emit_playbook_records(tmp_path, skill_names={"alpha"})


class TestRealCorpus:
    """The shipped playbooks must reference only real skills + phases."""

    def test_corpus_playbooks_resolve(self) -> None:
        if not _SKILLS_ROOT.exists():
            pytest.skip("skills corpus not on disk")
        skill_nodes, _ = emit_skill_records(_SKILLS_ROOT)
        skill_names = {n.properties["name"] for n in skill_nodes if n.label == "Skill"}
        phase_names = {p.name for p in load_phases()}

        # Must not raise — every STEP and phase resolves.
        nodes, edges = emit_playbook_records(
            _SKILLS_ROOT, skill_names=skill_names, phase_names=phase_names
        )
        names = {n.properties["name"] for n in nodes if n.label == "Playbook"}
        assert {
            "exposed-ai-service-takeover",
            "external-web-foothold",
            "ad-domain-dominance",
        } <= names
        # The AI playbook chains the two new skills first.
        ai_steps = sorted(
            (
                e
                for e in edges
                if e.edge_type == "STEP" and e.from_key == "exposed-ai-service-takeover"
            ),
            key=lambda e: e.properties["order"],
        )
        assert ai_steps[0].to_key == "ai-surface-mapping"
        assert ai_steps[1].to_key == "llm-api-abuse"
