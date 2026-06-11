"""Skillogy PLAYBOOK.md builder pass tests.

Covers the shared ``emit_playbook_records`` pass (parsing, graph emission,
and every validation error) plus an end-to-end compile of the in-tree
``cloud-metadata-exfiltration`` playbook through the real graph builder.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import decepticon
from decepticon.skillogy.builder.cli import build_graph
from decepticon.skillogy.builder.playbooks import (
    PlaybookValidationError,
    emit_playbook_records,
)
from decepticon.skillogy.builder.seeds import load_phases

_CORPUS_ROOT = Path(decepticon.__file__).resolve().parent / "skills"
_FROZEN = datetime(1970, 1, 1, tzinfo=timezone.utc)

_VALID_PLAYBOOK = """\
---
name: demo-chain
description: A demo playbook for testing the builder pass.
metadata:
  phase: credential-access
  tags: [demo, test]
  steps:
    - skill: skill-a
      goal: Do the first thing.
      phase: web-exploitation
    - skill: skill-b
      goal: Do the second thing.
---
# Demo

Body text.
"""


def _write_playbook(root: Path, name: str, text: str) -> Path:
    pb_dir = root / "playbooks" / name
    pb_dir.mkdir(parents=True, exist_ok=True)
    path = pb_dir / "PLAYBOOK.md"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Happy path: node + edge emission
# --------------------------------------------------------------------------


def test_emits_playbook_node_with_expected_props(tmp_path: Path) -> None:
    _write_playbook(tmp_path, "demo-chain", _VALID_PLAYBOOK)
    nodes, _ = emit_playbook_records(
        tmp_path,
        known_skills={"skill-a", "skill-b"},
        commit_sha="abc123",
        built_at=_FROZEN,
    )
    playbooks = [n for n in nodes if n.label == "Playbook"]
    assert len(playbooks) == 1
    props = playbooks[0].properties
    assert props["name"] == "demo-chain"
    assert props["target_phase"] == "credential-access"
    assert props["tags_raw"] == ["demo", "test"]
    assert props["step_count"] == 2
    assert props["commit_sha"] == "abc123"
    assert props["built_at"] == _FROZEN.isoformat()
    assert props["content_sha256"].startswith("sha256:")
    assert props["path"] == "/skills/playbooks/demo-chain/PLAYBOOK.md"


def test_emits_target_phase_and_ordered_step_edges(tmp_path: Path) -> None:
    _write_playbook(tmp_path, "demo-chain", _VALID_PLAYBOOK)
    _, edges = emit_playbook_records(
        tmp_path, known_skills={"skill-a", "skill-b"}, built_at=_FROZEN
    )

    targets = [e for e in edges if e.edge_type == "TARGETS_PHASE"]
    assert len(targets) == 1
    assert targets[0].from_key == "demo-chain"
    assert targets[0].to_label == "Phase"
    assert targets[0].to_key == "credential-access"

    steps = [e for e in edges if e.edge_type == "HAS_STEP"]
    assert [(e.to_key, e.properties["order"]) for e in steps] == [
        ("skill-a", 1),
        ("skill-b", 2),
    ]
    assert steps[0].properties["goal"] == "Do the first thing."
    assert steps[0].properties["phase"] == "web-exploitation"
    # Step 2 omits an explicit phase, so the edge carries no phase prop.
    assert "phase" not in steps[1].properties


def test_known_skills_none_skips_skill_existence_check(tmp_path: Path) -> None:
    _write_playbook(tmp_path, "demo-chain", _VALID_PLAYBOOK)
    # No known_skills -> parser must not raise on unknown skill names.
    nodes, _ = emit_playbook_records(tmp_path, known_skills=None, built_at=_FROZEN)
    assert any(n.label == "Playbook" for n in nodes)


def test_empty_root_emits_nothing(tmp_path: Path) -> None:
    (tmp_path / "playbooks").mkdir()
    nodes, edges = emit_playbook_records(tmp_path, built_at=_FROZEN)
    assert nodes == []
    assert edges == []


# --------------------------------------------------------------------------
# Validation errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        (
            """---
description: no name here.
metadata:
  phase: credential-access
  steps:
    - {skill: skill-a, goal: go}
---
x
""",
            "missing 'name'",
        ),
        (
            """---
name: no-desc
metadata:
  phase: credential-access
  steps:
    - {skill: skill-a, goal: go}
---
x
""",
            "missing 'description'",
        ),
        (
            """---
name: no-phase
description: d
metadata:
  steps:
    - {skill: skill-a, goal: go}
---
x
""",
            "missing 'metadata.phase'",
        ),
        (
            """---
name: bad-phase
description: d
metadata:
  phase: not-a-real-phase
  steps:
    - {skill: skill-a, goal: go}
---
x
""",
            "unknown target phase",
        ),
        (
            """---
name: no-steps
description: d
metadata:
  phase: credential-access
  steps: []
---
x
""",
            "non-empty list",
        ),
        (
            """---
name: step-no-skill
description: d
metadata:
  phase: credential-access
  steps:
    - {goal: go}
---
x
""",
            "missing 'skill'",
        ),
        (
            """---
name: step-no-goal
description: d
metadata:
  phase: credential-access
  steps:
    - {skill: skill-a}
---
x
""",
            "missing 'goal'",
        ),
        (
            """---
name: bad-step-phase
description: d
metadata:
  phase: credential-access
  steps:
    - {skill: skill-a, goal: go, phase: not-a-phase}
---
x
""",
            "unknown phase",
        ),
    ],
)
def test_validation_errors(tmp_path: Path, body: str, needle: str) -> None:
    _write_playbook(tmp_path, "bad", body)
    with pytest.raises(PlaybookValidationError) as exc:
        emit_playbook_records(tmp_path, known_skills={"skill-a"}, built_at=_FROZEN)
    assert needle in str(exc.value)


def test_unknown_skill_reference_is_rejected(tmp_path: Path) -> None:
    _write_playbook(tmp_path, "demo-chain", _VALID_PLAYBOOK)
    with pytest.raises(PlaybookValidationError) as exc:
        # skill-b is not in the known set.
        emit_playbook_records(tmp_path, known_skills={"skill-a"}, built_at=_FROZEN)
    assert "unknown skill 'skill-b'" in str(exc.value)


def test_duplicate_playbook_name_is_rejected(tmp_path: Path) -> None:
    _write_playbook(tmp_path, "one", _VALID_PLAYBOOK)
    _write_playbook(tmp_path, "two", _VALID_PLAYBOOK)
    with pytest.raises(PlaybookValidationError) as exc:
        emit_playbook_records(tmp_path, known_skills={"skill-a", "skill-b"}, built_at=_FROZEN)
    assert "duplicate playbook name" in str(exc.value)


# --------------------------------------------------------------------------
# In-tree corpus: the real cloud-metadata-exfiltration playbook compiles
# --------------------------------------------------------------------------


def test_cloud_metadata_playbook_present_on_disk() -> None:
    path = (
        _CORPUS_ROOT
        / "playbooks"
        / "cloud-metadata-exfiltration"
        / "PLAYBOOK.md"
    )
    assert path.is_file()


def test_full_build_graph_compiles_cloud_playbook_without_errors() -> None:
    """build_graph (skills-only) must compile every PLAYBOOK.md in the
    real corpus with no validation error and wire the cloud playbook to
    its target phase + the four skills it composes."""
    nodes, edges = build_graph(
        skills_root=_CORPUS_ROOT,
        stix_bundle=None,
        commit_sha="",
        built_at=_FROZEN,
    )

    playbook = next(
        (
            n
            for n in nodes
            if n.label == "Playbook" and n.key == "cloud-metadata-exfiltration"
        ),
        None,
    )
    assert playbook is not None, "cloud-metadata-exfiltration not compiled"
    assert playbook.properties["target_phase"] == "credential-access"

    skill_names = {n.key for n in nodes if n.label == "Skill"}
    step_targets = {
        e.to_key
        for e in edges
        if e.edge_type == "HAS_STEP" and e.from_key == "cloud-metadata-exfiltration"
    }
    expected = {"exploit-ssrf", "imds-pivot", "aws-iam-enum", "aws-iam-passrole-chain"}
    assert step_targets == expected
    # Every referenced skill must be a real compiled :Skill node.
    assert expected <= skill_names

    target_edges = {
        e.to_key
        for e in edges
        if e.edge_type == "TARGETS_PHASE"
        and e.from_key == "cloud-metadata-exfiltration"
    }
    assert target_edges == {"credential-access"}
    # Target phase must be a seeded :Phase.
    assert "credential-access" in {p.name for p in load_phases()}
