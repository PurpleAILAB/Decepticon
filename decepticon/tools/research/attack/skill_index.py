"""Discover skills and seed them as graph nodes linked to ATT&CK techniques.

A skill becomes a ``Skill`` node with a ``TEACHES`` edge to every technique
its ``metadata.mitre_attack`` frontmatter declares. This is what joins the
skill library to the attack graph.

Seeding source of truth: the ``skills/`` tree is baked into the *sandbox*
container, but seeding runs in the *langgraph* container which does not host
``/skills/``. So production seeds from a build-time JSON
(``data/skill_techniques.json``); a ``DECEPTICON_SKILLS_DIR`` env override
re-discovers from a live tree for development.
"""

from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from decepticon.tools.research.attack.catalog import is_technique_id, parse_ids
from decepticon.tools.research.attack.seed import technique_node_id
from decepticon.tools.research.graph import Edge, EdgeKind, Node, NodeKind

_SKILL_INDEX_FILE = "data/skill_techniques.json"
_SKILLS_DIR_ENV = "DECEPTICON_SKILLS_DIR"


class SkillRecord(BaseModel):
    """A skill, indexed for the knowledge graph."""

    name: str
    path: str = Field(description="Canonical /skills/... path, also the node key")
    description: str = ""
    subdomain: str = "general"
    mitre: list[str] = Field(default_factory=list, description="Normalized ATT&CK IDs")
    tags: list[str] = Field(default_factory=list)


# ── Frontmatter parsing ──────────────────────────────────────────────────


def _extract_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter block of a SKILL.md as a dict."""
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return {}
    block = normalized[4:end]
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_skill_md(text: str, path: str) -> SkillRecord | None:
    """Parse a SKILL.md body into a :class:`SkillRecord`.

    Returns ``None`` when the frontmatter has no ``name`` — such a file is
    not a usable skill.
    """
    fm = _extract_frontmatter(text)
    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    metadata = fm.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    tags_raw = metadata.get("tags", "")
    if isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = [t.strip() for t in str(tags_raw).replace(",", " ").split() if t.strip()]
    return SkillRecord(
        name=name.strip(),
        path=path,
        description=str(fm.get("description", "")).strip(),
        subdomain=str(metadata.get("subdomain", "general")).strip() or "general",
        mitre=parse_ids(metadata.get("mitre_attack")),
        tags=tags,
    )


def discover_skills(skills_root: Path) -> list[SkillRecord]:
    """Walk ``skills_root`` for SKILL.md files and parse each into a record.

    Canonical paths are ``/skills/<relpath>`` — the form ``load_skill`` and
    the graph node key both use.
    """
    root = Path(skills_root)
    records: list[SkillRecord] = []
    for md_path in sorted(root.rglob("SKILL.md")):
        rel = md_path.relative_to(root).as_posix()
        canonical = "/skills/" + rel
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        rec = parse_skill_md(text, canonical)
        if rec is not None:
            records.append(rec)
    return records


# ── Graph construction ───────────────────────────────────────────────────


def skill_node_id(path: str) -> str:
    """Deterministic graph node ID for a skill, keyed on its canonical path."""
    return Node.make(NodeKind.SKILL, path, key=path).id


def skill_graph_elements(records: list[SkillRecord]) -> tuple[list[Node], list[Edge]]:
    """Build (nodes, edges) for the skill layer.

    Each skill is a ``Skill`` node; each declared technique ID becomes a
    ``TEACHES`` edge. Tactic-level tags are kept in node props but do not
    produce edges — ``TEACHES`` targets techniques only.
    """
    nodes: list[Node] = []
    edges: list[Edge] = []
    for rec in records:
        nodes.append(
            Node.make(
                NodeKind.SKILL,
                rec.name,
                key=rec.path,
                description=rec.description,
                subdomain=rec.subdomain,
                mitre=list(rec.mitre),
                tags=list(rec.tags),
            )
        )
        src = skill_node_id(rec.path)
        for mitre_id in rec.mitre:
            if is_technique_id(mitre_id):
                edges.append(Edge.make(src, technique_node_id(mitre_id), EdgeKind.TEACHES))
    return nodes, edges


# ── Loading / seeding ────────────────────────────────────────────────────


def load_skill_index() -> list[SkillRecord]:
    """Load skill records — from a live tree if ``DECEPTICON_SKILLS_DIR`` is
    set, otherwise from the build-time bundled JSON.

    Returns ``[]`` (rather than raising) when no source is available, so
    seeding degrades gracefully before the dataset is built.
    """
    override = os.environ.get(_SKILLS_DIR_ENV, "").strip()
    if override:
        return discover_skills(Path(override))
    try:
        raw = resources.files("decepticon.tools.research.attack").joinpath(_SKILL_INDEX_FILE)
        data = json.loads(raw.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    return [SkillRecord.model_validate(item) for item in data]


def seed_skills(store, records: list[SkillRecord] | None = None) -> dict[str, int]:
    """Seed the skill layer into ``store``. Idempotent. Returns counts."""
    records = load_skill_index() if records is None else records
    nodes, edges = skill_graph_elements(records)
    store.batch_upsert_nodes(nodes)
    store.batch_upsert_edges(edges)
    return {"skills": len(records), "teaches_edges": len(edges)}


__all__ = [
    "SkillRecord",
    "discover_skills",
    "load_skill_index",
    "parse_skill_md",
    "seed_skills",
    "skill_graph_elements",
    "skill_node_id",
]
