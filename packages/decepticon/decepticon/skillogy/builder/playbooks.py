"""PLAYBOOK.md → :Playbook nodes + ordered step edges.

A *playbook* is an authored, ordered chain of existing :Skill nodes that
solves one concrete offensive objective end-to-end (e.g. SSRF → IMDS →
IAM credential exfiltration). Unlike a :Skill — which is a single
self-contained capability — a :Playbook is composition: it references
skills by name and gives them an execution order plus a per-step goal.

Discovery mirrors ``skills.py``: every ``PLAYBOOK.md`` under the corpus
root is compiled. Authors drop a directory at
``skills/playbooks/<name>/PLAYBOOK.md`` and the graph picks it up with no
seed edit required.

Frontmatter schema
------------------
::

    ---
    name: <kebab-name>          # required, unique; the :Playbook key
    description: <one line>     # required
    metadata:
      phase: <phase-name>       # required; target :Phase (TARGETS_PHASE)
      tags: [..]                # optional, free-form
      steps:                    # required, non-empty, in execution order
        - skill: <skill-name>   # required; must match an existing :Skill name
          goal: <text>          # required; what this step accomplishes
          phase: <phase-name>   # optional; the kill-chain phase of the step
    ---
    # markdown body

Edge emission policy
--------------------
- ``TARGETS_PHASE`` : every Playbook → its target :Phase.
- ``HAS_STEP``      : Playbook → each referenced :Skill, carrying the
                      1-based ``order`` and the step ``goal`` (and the
                      step ``phase`` when the author declares one).

Validation
----------
The pass fails loudly (``PlaybookValidationError``) on a missing name /
description / target phase, an empty step list, a step that omits
``skill`` or ``goal``, an unknown ``phase`` (target or per-step), or a
step whose ``skill`` is not a known :Skill name. ``known_skills`` is the
set of compiled :Skill names; when ``None`` the skill-existence check is
skipped (useful for isolated unit tests of the parser itself).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decepticon.skill_audit.frontmatter import (
    FrontmatterParseError,
    parse_frontmatter,
)
from decepticon.skillogy.builder.model import Edge, Node
from decepticon.skillogy.builder.seeds import load_phases


class PlaybookValidationError(ValueError):
    """Raised when a PLAYBOOK.md violates the playbook schema."""


def _canonical_playbook_path(playbook_md: Path, root: Path) -> str:
    """Return the ``/skills/<...>/PLAYBOOK.md`` form used for the path prop."""
    rel = playbook_md.relative_to(root).as_posix()
    return "/skills/" + rel


def _coerce_str_list(value: Any) -> list[str]:
    """Tags may be authored as a YAML list or a CSV string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def emit_playbook_records(
    playbooks_root: Path,
    *,
    known_skills: set[str] | None = None,
    known_phases: set[str] | None = None,
    commit_sha: str = "",
    built_at: datetime | None = None,
) -> tuple[list[Node], list[Edge]]:
    """Walk ``playbooks_root`` and emit (nodes, edges) for every PLAYBOOK.md.

    ``commit_sha`` and ``built_at`` are stamped onto every :Playbook node
    for build attribution, mirroring :func:`emit_skill_records`. Tests
    pass them explicitly for byte-identical determinism.
    """
    if not playbooks_root.exists():
        raise FileNotFoundError(f"playbooks root not found: {playbooks_root}")
    if built_at is None:
        built_at = datetime.now(timezone.utc)
    built_at_iso = built_at.isoformat()

    if known_phases is None:
        known_phases = {p.name for p in load_phases()}

    nodes: list[Node] = []
    edges: list[Edge] = []
    seen_names: set[str] = set()

    for playbook_md in sorted(playbooks_root.rglob("PLAYBOOK.md")):
        text = playbook_md.read_text(encoding="utf-8")
        try:
            meta, body = parse_frontmatter(text)
        except FrontmatterParseError as exc:
            raise PlaybookValidationError(f"{playbook_md}: {exc}") from exc

        name = str(meta.get("name") or "").strip()
        description = str(meta.get("description") or "").strip()
        if not name:
            raise PlaybookValidationError(f"{playbook_md}: missing 'name'")
        if not description:
            raise PlaybookValidationError(f"{playbook_md}: missing 'description'")
        if name in seen_names:
            raise PlaybookValidationError(
                f"{playbook_md}: duplicate playbook name '{name}'"
            )
        seen_names.add(name)

        metadata_raw = meta.get("metadata")
        metadata: dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}

        target_phase = str(metadata.get("phase") or "").strip()
        if not target_phase:
            raise PlaybookValidationError(
                f"{playbook_md}: missing 'metadata.phase' (target phase)"
            )
        if target_phase not in known_phases:
            raise PlaybookValidationError(
                f"{playbook_md}: unknown target phase '{target_phase}'"
            )

        steps_raw = metadata.get("steps")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise PlaybookValidationError(
                f"{playbook_md}: 'metadata.steps' must be a non-empty list"
            )

        tags_raw = _coerce_str_list(metadata.get("tags"))
        path = _canonical_playbook_path(playbook_md, playbooks_root)
        body_bytes = body.encode("utf-8")
        body_sha = "sha256:" + hashlib.sha256(body_bytes).hexdigest()

        # Validate every step before emitting any edge so a bad step
        # never produces a half-built playbook.
        step_edges: list[Edge] = []
        for index, step in enumerate(steps_raw, start=1):
            if not isinstance(step, dict):
                raise PlaybookValidationError(
                    f"{playbook_md}: step {index} must be a mapping"
                )
            step_skill = str(step.get("skill") or "").strip()
            step_goal = str(step.get("goal") or "").strip()
            step_phase = str(step.get("phase") or "").strip()
            if not step_skill:
                raise PlaybookValidationError(
                    f"{playbook_md}: step {index} missing 'skill'"
                )
            if not step_goal:
                raise PlaybookValidationError(
                    f"{playbook_md}: step {index} missing 'goal'"
                )
            if known_skills is not None and step_skill not in known_skills:
                raise PlaybookValidationError(
                    f"{playbook_md}: step {index} references unknown skill "
                    f"'{step_skill}'"
                )
            if step_phase and step_phase not in known_phases:
                raise PlaybookValidationError(
                    f"{playbook_md}: step {index} has unknown phase '{step_phase}'"
                )
            step_props: dict[str, Any] = {"order": index, "goal": step_goal}
            if step_phase:
                step_props["phase"] = step_phase
            step_edges.append(
                Edge(
                    edge_type="HAS_STEP",
                    from_label="Playbook",
                    from_key_field="name",
                    from_key=name,
                    to_label="Skill",
                    to_key_field="name",
                    to_key=step_skill,
                    properties=step_props,
                )
            )

        props: dict[str, Any] = {
            "name": name,
            "path": path,
            "description": description,
            "body": body,
            "content_sha256": body_sha,
            "size_bytes": len(body_bytes),
            "target_phase": target_phase,
            "tags_raw": tags_raw,
            "step_count": len(steps_raw),
            "commit_sha": commit_sha,
            "built_at": built_at_iso,
        }
        nodes.append(Node(label="Playbook", key_field="name", properties=props))

        edges.append(
            Edge(
                edge_type="TARGETS_PHASE",
                from_label="Playbook",
                from_key_field="name",
                from_key=name,
                to_label="Phase",
                to_key_field="name",
                to_key=target_phase,
            )
        )
        edges.extend(step_edges)

    return nodes, edges
