"""Validate the skill knowledge graph declared by SKILL.md frontmatter.

Checks the skill-to-skill edges (``requires`` / ``chains_to`` / ``refines``)
and ATT&CK tags for authoring mistakes:

* dangling references — a skill points at a skill that does not exist        (error)
* self references — a skill lists itself as a relation                       (error)
* ``requires`` / ``refines`` cycles — break dependency ordering              (error)
* ``chains_to`` cycles — usually a mistake, but routing tolerates them        (warning)
* ATT&CK IDs absent from the bundled catalog                                 (warning)

``scripts/build_attack_dataset.py`` runs this as a hard gate (errors fail the
build). At runtime it is advisory — a bad edge is simply never created.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from decepticon.tools.research.attack.catalog import AttackCatalog, load_attack_catalog
from decepticon.tools.research.attack.skill_index import SkillRecord

# The skill-to-skill edge fields, paired with how a cycle in each is treated.
_EDGE_FIELDS: tuple[tuple[str, str], ...] = (
    ("requires", "error"),
    ("refines", "error"),
    ("chains_to", "warning"),
)


@dataclass
class SkillGraphDiagnostics:
    """Outcome of :func:`validate_skill_graph` — errors, warnings, and counts."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when there are no hard errors (warnings are tolerated)."""
        return not self.errors


def _find_cycles(records: list[SkillRecord], attr: str, known: set[str]) -> list[list[str]]:
    """Return distinct cycles in the directed graph of one edge field.

    Self-loops and dangling targets are excluded — those are reported
    separately and cannot form a multi-node cycle.
    """
    adj: dict[str, list[str]] = {rec.path: [] for rec in records}
    for rec in records:
        targets = sorted(t for t in getattr(rec, attr) if t != rec.path and t in known)
        adj[rec.path] = targets

    white, gray, black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(adj, white)
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()

    def visit(node: str, stack: list[str]) -> None:
        color[node] = gray
        stack.append(node)
        for nxt in adj[node]:
            if color[nxt] == gray:
                cycle = stack[stack.index(nxt) :] + [nxt]
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif color[nxt] == white:
                visit(nxt, stack)
        stack.pop()
        color[node] = black

    for path in sorted(adj):
        if color[path] == white:
            visit(path, [])
    return cycles


def validate_skill_graph(
    records: list[SkillRecord],
    catalog: AttackCatalog | None = None,
) -> SkillGraphDiagnostics:
    """Validate skill-to-skill edges and ATT&CK tags across ``records``."""
    catalog = catalog or load_attack_catalog()
    diag = SkillGraphDiagnostics()
    known = {rec.path for rec in records}

    # Dangling and self references.
    for rec in records:
        for attr, _severity in _EDGE_FIELDS:
            for target in getattr(rec, attr):
                if target == rec.path:
                    diag.errors.append(f"{rec.path}: '{attr}' references itself")
                elif target not in known:
                    diag.errors.append(f"{rec.path}: '{attr}' references unknown skill {target}")

    # Cycles, per edge field.
    for attr, severity in _EDGE_FIELDS:
        for cycle in _find_cycles(records, attr, known):
            message = f"{attr} cycle: {' -> '.join(cycle)}"
            bucket = diag.errors if severity == "error" else diag.warnings
            bucket.append(message)

    # ATT&CK IDs not present in the bundled catalog.
    for rec in records:
        for tid in rec.mitre:
            if catalog.technique(tid) is None and catalog.tactic(tid) is None:
                diag.warnings.append(f"{rec.path}: ATT&CK ID {tid} not in catalog")

    diag.counts = {
        "skills": len(records),
        "errors": len(diag.errors),
        "warnings": len(diag.warnings),
    }
    return diag


__all__ = ["SkillGraphDiagnostics", "validate_skill_graph"]
