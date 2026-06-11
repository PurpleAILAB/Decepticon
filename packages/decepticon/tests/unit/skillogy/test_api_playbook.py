"""Compile-and-shape tests for the shipped ``api-security-audit`` playbook.

The shared playbook *pass* (parser + validation behaviour) is covered in
``test_playbooks.py``; this module pins the one playbook this branch
ships. It compiles the real ``PLAYBOOK.md`` from the in-tree corpus and
asserts the graph shape that downstream traversal depends on:

- exactly one ``:Playbook`` node keyed ``api-security-audit``;
- a ``TARGETS_PHASE`` edge to a seeded ``:Phase``;
- one ordered ``HAS_STEP`` edge per authored step, each pointing at a
  ``:Skill`` name that actually exists in the corpus (no dangling step).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import decepticon
from decepticon.skillogy.builder.playbooks import (
    PlaybookValidationError,
    emit_playbook_records,
)
from decepticon.skillogy.builder.seeds import load_phases
from decepticon.skillogy.builder.skills import emit_skill_records

_SKILLS_ROOT = Path(decepticon.__file__).resolve().parent / "skills"
_PLAYBOOK_DIR = _SKILLS_ROOT / "playbooks" / "api-security-audit"
_FROZEN = datetime(1970, 1, 1, tzinfo=timezone.utc)

_EXPECTED_STEPS = [
    "web-api-enumeration",
    "web-auth-mapping",
    "idor",
    "auth-bypass",
    "ssrf",
]


def _corpus_skill_names() -> set[str]:
    nodes, _ = emit_skill_records(_SKILLS_ROOT, built_at=_FROZEN)
    return {n.key for n in nodes if n.label == "Skill"}


def _compile_api_playbook():
    return emit_playbook_records(
        _PLAYBOOK_DIR,
        known_skills=_corpus_skill_names(),
        built_at=_FROZEN,
    )


def test_api_security_audit_emits_single_playbook_node() -> None:
    nodes, _ = _compile_api_playbook()
    playbooks = [n for n in nodes if n.label == "Playbook"]
    assert len(playbooks) == 1
    node = playbooks[0]
    assert node.key == "api-security-audit"
    assert node.properties["target_phase"] == "web-exploitation"
    assert node.properties["step_count"] == len(_EXPECTED_STEPS)
    assert node.properties["description"]
    assert node.properties["content_sha256"].startswith("sha256:")


def test_target_phase_edge_points_at_seeded_phase() -> None:
    _, edges = _compile_api_playbook()
    seeded = {p.name for p in load_phases()}
    targets = [e for e in edges if e.edge_type == "TARGETS_PHASE"]
    assert len(targets) == 1
    edge = targets[0]
    assert edge.from_key == "api-security-audit"
    assert edge.to_label == "Phase"
    assert edge.to_key in seeded


def test_has_step_edges_are_ordered_and_reference_real_skills() -> None:
    skill_names = _corpus_skill_names()
    _, edges = _compile_api_playbook()
    steps = sorted(
        (e for e in edges if e.edge_type == "HAS_STEP"),
        key=lambda e: e.properties["order"],
    )
    assert [e.to_key for e in steps] == _EXPECTED_STEPS
    # 1-based, contiguous ordering.
    assert [e.properties["order"] for e in steps] == list(range(1, len(_EXPECTED_STEPS) + 1))
    for edge in steps:
        assert edge.from_key == "api-security-audit"
        assert edge.to_label == "Skill"
        assert edge.to_key in skill_names, f"step references unknown skill {edge.to_key!r}"
        assert edge.properties["goal"].strip()


def test_compile_fails_loudly_when_a_step_skill_is_unknown() -> None:
    # Re-compiling against an empty skill set must reject the dangling
    # references rather than silently emitting orphan HAS_STEP edges.
    with pytest.raises(PlaybookValidationError):
        emit_playbook_records(
            _PLAYBOOK_DIR,
            known_skills=set(),
            built_at=_FROZEN,
        )
