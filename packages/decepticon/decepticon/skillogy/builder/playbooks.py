"""PLAYBOOK.md → :Playbook nodes + ordered :STEP edges.

A *playbook* is an authored, ordered chain of skills for a recurring
engagement scenario — "exposed AI service takeover", "external web
foothold", "AD domain dominance". It is the composition plane the
Skillogy v0.2 design reserved (``COMPOSES_WITH`` / ``get_skill_chain``):
instead of the agent re-deriving a multi-skill sequence every run, a
playbook records the curated ordering once, in the graph, auditable in
the PR diff.

Graph shape
-----------
- ``:Playbook {name, path, description, phase, step_count, …}`` — one
  PLAYBOOK.md file.
- ``(:Playbook)-[:STEP {order}]->(:Skill)`` — ordered membership,
  ``order`` 1-based. ``suggest_next`` is derived at query time by
  matching ``order = current.order + 1`` on the shared playbook, so no
  separate ``NEXT`` edge type is needed and a transition shared by two
  playbooks is not lost to edge dedup.
- ``(:Playbook)-[:IN_PHASE]->(:Phase)`` — when the playbook declares a
  ``metadata.phase`` so the middleware can advertise playbooks for the
  agent's current phase.

Build-time integrity
--------------------
Every ``steps`` entry MUST resolve to a real ``:Skill`` name and every
``phase`` to a seeded ``:Phase``. A dangling reference raises at build
time — the same fail-fast contract the skill pass trusts from the
Phase 0 validator — so a typo can never ship a playbook that routes the
agent to a nonexistent skill.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decepticon.skill_audit.frontmatter import (
    FrontmatterParseError,
    parse_frontmatter,
)
from decepticon.skillogy.builder.model import Edge, Node


def _canonical_playbook_path(playbook_md: Path, root: Path) -> str:
    """Return the ``/skills/<...>/PLAYBOOK.md`` form used for the node path."""
    rel = playbook_md.relative_to(root).as_posix()
    return "/skills/" + rel


def _coerce_steps(value: Any) -> list[str]:
    """Steps may be a YAML list or a comma-separated string."""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def emit_playbook_records(
    skills_root: Path,
    *,
    skill_names: Iterable[str],
    phase_names: Iterable[str] | None = None,
    commit_sha: str = "",
    built_at: datetime | None = None,
) -> tuple[list[Node], list[Edge]]:
    """Walk ``skills_root`` for PLAYBOOK.md files and emit (nodes, edges).

    ``skill_names`` is the set of canonical ``:Skill`` names already
    emitted by the skill pass; every step is validated against it.
    ``phase_names`` (when given) validates ``metadata.phase``. ``built_at``
    / ``commit_sha`` are stamped on each node, mirroring the skill pass,
    so the dump attributes playbooks to a build.
    """
    if not skills_root.exists():
        raise FileNotFoundError(f"skills root not found: {skills_root}")
    if built_at is None:
        built_at = datetime.now(timezone.utc)
    built_at_iso = built_at.isoformat()

    known_skills = set(skill_names)
    known_phases = set(phase_names) if phase_names is not None else None

    nodes: list[Node] = []
    edges: list[Edge] = []

    for playbook_md in sorted(skills_root.rglob("PLAYBOOK.md")):
        text = playbook_md.read_text(encoding="utf-8")
        try:
            meta, _body = parse_frontmatter(text)
        except FrontmatterParseError as exc:
            raise RuntimeError(f"{playbook_md}: frontmatter parse failed: {exc}") from exc

        name = str(meta.get("name") or "").strip()
        description = str(meta.get("description") or "").strip()
        if not name or not description:
            raise RuntimeError(f"{playbook_md}: playbook missing name or description")

        metadata_raw = meta.get("metadata")
        metadata: dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
        phase = str(metadata.get("phase") or "").strip()
        steps = _coerce_steps(metadata.get("steps"))

        if not steps:
            raise RuntimeError(f"{playbook_md}: playbook {name!r} has no steps")
        if len(set(steps)) != len(steps):
            raise RuntimeError(f"{playbook_md}: playbook {name!r} has duplicate steps: {steps}")
        unknown = [s for s in steps if s not in known_skills]
        if unknown:
            raise RuntimeError(
                f"{playbook_md}: playbook {name!r} references unknown skills {unknown} "
                f"(steps must match an existing :Skill name)"
            )
        if phase and known_phases is not None and phase not in known_phases:
            raise RuntimeError(f"{playbook_md}: playbook {name!r} declares unknown phase {phase!r}")

        path = _canonical_playbook_path(playbook_md, skills_root)
        nodes.append(
            Node(
                label="Playbook",
                key_field="name",
                properties={
                    "name": name,
                    "path": path,
                    "description": description,
                    "phase": phase,
                    "step_count": len(steps),
                    "commit_sha": commit_sha,
                    "built_at": built_at_iso,
                },
            )
        )

        for order, skill_name in enumerate(steps, start=1):
            edges.append(
                Edge(
                    edge_type="STEP",
                    from_label="Playbook",
                    from_key_field="name",
                    from_key=name,
                    to_label="Skill",
                    to_key_field="name",
                    to_key=skill_name,
                    properties={"order": order},
                )
            )

        if phase:
            edges.append(
                Edge(
                    edge_type="IN_PHASE",
                    from_label="Playbook",
                    from_key_field="name",
                    from_key=name,
                    to_label="Phase",
                    to_key_field="name",
                    to_key=phase,
                )
            )

    return nodes, edges
