"""Skillogy v0.2 — capability-plane planner for Decepticon skill chains.

Provides two public functions:

* :func:`suggest_next`  — given a set of acquired capabilities and active RoE
  constraints, return the ranked next skills the operator should invoke.
* :func:`get_skill_chain` — compute a full attack chain from a desired end-state
  capability back to the current state, respecting RoE and composability.

Both functions operate on an in-memory graph derived from the Cypher files
shipped under ``skills/.graph/``.  No Neo4j driver is required — the module
parses the ``.cypher`` files at import time and builds adjacency structures
in plain Python.

Python 3.13+, type hints throughout, no external dependencies beyond stdlib.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Capability:
    """An abstract artifact class that skills produce or consume."""

    name: str
    description: str = ""
    phase: str = ""


@dataclass(frozen=True, slots=True)
class SkillEdge:
    """A typed directed edge between a skill and a capability (or another skill)."""

    source: str
    target: str
    rel: str
    props: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A single skill suggestion returned by :func:`suggest_next`.

    Attributes:
        skill: Skill name (slug).
        produces: Capabilities this skill can generate.
        consumes: Capabilities this skill requires.
        satisfied: Which consumed capabilities are already acquired.
        missing: Which consumed capabilities are *not* yet acquired.
        score: Heuristic ranking score (higher is better).
        reason: Human-readable explanation of why this skill was suggested.
    """

    skill: str
    produces: tuple[str, ...]
    consumes: tuple[str, ...]
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    score: float
    reason: str


@dataclass(frozen=True, slots=True)
class ChainStep:
    """One step in a skill chain returned by :func:`get_skill_chain`.

    Attributes:
        order: 0-indexed position in the chain (0 = first skill to run).
        skill: Skill name (slug).
        produces: Capabilities unlocked by this step.
        requires: Capabilities that must exist before this step runs.
        composable_with: Skills that can run in parallel at this step.
    """

    order: int
    skill: str
    produces: tuple[str, ...]
    requires: tuple[str, ...]
    composable_with: tuple[str, ...]


# ---------------------------------------------------------------------------
# Cypher micro-parser
# ---------------------------------------------------------------------------

_RE_MERGE_NODE = re.compile(
    r"MERGE\s+\(\w+:(\w+)\s+\{name:\s*'([^']+)'\}\)",
)
_RE_SET_PROP = re.compile(
    r"(\w+)\.(\w+)\s*=\s*'([^']*)'",
)
_RE_MATCH_EDGE = re.compile(
    r"MATCH\s+\(\w+:(\w+)\s+\{name:\s*'([^']+)'\}\)"
    r"\s*,\s*"
    r"\(\w+:(\w+)\s+\{name:\s*'([^']+)'\}\)",
)
_RE_MERGE_EDGE = re.compile(
    r"MERGE\s+\(\w+\)-\[:(\w+)"
    r"(?:\s+\{([^}]*)\})?"
    r"\s*\]->\(\w+\)",
)


def _parse_edge_props(raw: str | None) -> dict[str, str]:
    """Parse ``{key: 'value', ...}`` property strings from Cypher edges."""
    if not raw:
        return {}
    out: dict[str, str] = {}
    for m in re.finditer(r"(\w+):\s*'([^']*)'", raw):
        out[m.group(1)] = m.group(2)
    return out


class _GraphStore:
    """In-memory adjacency store built from parsed Cypher files."""

    def __init__(self) -> None:
        self.capabilities: dict[str, Capability] = {}
        self.skill_produces: dict[str, list[str]] = defaultdict(list)
        self.skill_consumes: dict[str, list[str]] = defaultdict(list)
        self.consumes_required: dict[tuple[str, str], bool] = {}
        self.composes_with: dict[str, list[str]] = defaultdict(list)
        self.substitutes: dict[str, list[str]] = defaultdict(list)
        self.forbidden_by: dict[str, list[str]] = defaultdict(list)
        self.roe_constraints: dict[str, str] = {}  # name → description

    # -- loader ------------------------------------------------------------

    def load_cypher(self, text: str) -> None:
        """Parse a single ``.cypher`` file and populate adjacency maps."""
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # --- Capability / RoEConstraint node ---
            m_node = _RE_MERGE_NODE.match(line)
            if m_node:
                label, name = m_node.group(1), m_node.group(2)
                props: dict[str, str] = {}
                # collect SET continuation lines
                j = i + 1
                while j < len(lines):
                    sline = lines[j].strip()
                    if sline.startswith("SET ") or sline.startswith("    "):
                        for pm in _RE_SET_PROP.finditer(sline):
                            props[pm.group(2)] = pm.group(3)
                        j += 1
                    else:
                        break
                if label == "Capability":
                    self.capabilities[name] = Capability(
                        name=name,
                        description=props.get("description", ""),
                        phase=props.get("phase", ""),
                    )
                elif label == "RoEConstraint":
                    self.roe_constraints[name] = props.get("description", "")
                i = j
                continue

            # --- MATCH ... MERGE edge block ---
            m_match = _RE_MATCH_EDGE.match(line)
            if m_match:
                src_label = m_match.group(1)
                src_name = m_match.group(2)
                tgt_label = m_match.group(3)
                tgt_name = m_match.group(4)
                # next non-blank line should be the MERGE edge
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    m_edge = _RE_MERGE_EDGE.match(lines[j].strip())
                    if m_edge:
                        rel_type = m_edge.group(1)
                        edge_props = _parse_edge_props(m_edge.group(2))
                        self._store_edge(
                            src_label, src_name,
                            tgt_label, tgt_name,
                            rel_type, edge_props,
                        )
                        i = j + 1
                        continue
            i += 1

    def _store_edge(
        self,
        src_label: str, src_name: str,
        tgt_label: str, tgt_name: str,
        rel_type: str, props: dict[str, str],
    ) -> None:
        if rel_type == "PRODUCES" and src_label == "Skill" and tgt_label == "Capability":
            self.skill_produces[src_name].append(tgt_name)
        elif rel_type == "CONSUMES" and src_label == "Skill" and tgt_label == "Capability":
            self.skill_consumes[src_name].append(tgt_name)
            self.consumes_required[(src_name, tgt_name)] = props.get("required", "false") == "true"
        elif rel_type == "COMPOSES_WITH" and src_label == "Skill" and tgt_label == "Skill":
            self.composes_with[src_name].append(tgt_name)
            self.composes_with[tgt_name].append(src_name)
        elif rel_type == "SUBSTITUTES" and src_label == "Skill" and tgt_label == "Skill":
            self.substitutes[src_name].append(tgt_name)
        elif rel_type == "FORBIDDEN_BY" and src_label == "Skill" and tgt_label == "RoEConstraint":
            self.forbidden_by[src_name].append(tgt_name)

    # -- queries -----------------------------------------------------------

    def all_skill_names(self) -> set[str]:
        """Return every skill name that appears in PRODUCES or CONSUMES."""
        names: set[str] = set()
        names.update(self.skill_produces.keys())
        names.update(self.skill_consumes.keys())
        return names

    def is_forbidden(self, skill: str, active_roe: frozenset[str]) -> bool:
        """Return True if *skill* is blocked by any constraint in *active_roe*."""
        return bool(active_roe & frozenset(self.forbidden_by.get(skill, [])))

    def unsatisfied(self, skill: str, acquired: frozenset[str]) -> list[str]:
        """Return required capabilities of *skill* not yet in *acquired*."""
        out: list[str] = []
        for cap in self.skill_consumes.get(skill, []):
            if cap not in acquired and self.consumes_required.get((skill, cap), False):
                out.append(cap)
        return out


# ---------------------------------------------------------------------------
# Graph singleton loader
# ---------------------------------------------------------------------------

_GRAPH: _GraphStore | None = None


def _load_graph() -> _GraphStore:
    """Load and cache the capability graph from shipped Cypher files."""
    global _GRAPH  # noqa: PLW0603
    if _GRAPH is not None:
        return _GRAPH

    store = _GraphStore()

    # Resolve skills/.graph/ from the installed package
    graph_dir: Path | None = None
    try:
        pkg = files("decepticon") / "skills" / ".graph"
        with as_file(pkg) as p:
            graph_dir = Path(p)
    except (TypeError, FileNotFoundError, ModuleNotFoundError):
        # Fallback: resolve relative to this file
        graph_dir = Path(__file__).resolve().parent.parent / "skills" / ".graph"

    if graph_dir is not None and graph_dir.is_dir():
        for cypher_file in sorted(graph_dir.glob("*.cypher")):
            store.load_cypher(cypher_file.read_text(encoding="utf-8"))

    _GRAPH = store
    return _GRAPH


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def suggest_next(
    acquired: Iterable[str],
    *,
    active_roe: Iterable[str] = (),
    top_k: int = 10,
) -> list[Suggestion]:
    """Suggest the next skills to invoke given the current state.

    Args:
        acquired: Capability names the operator has already obtained
            (e.g. ``['subdomain-list', 'credential-set']``).
        active_roe: Active RoE constraint names that block certain skills
            (e.g. ``['no-wireless', 'no-social-engineering']``).
        top_k: Maximum number of suggestions to return.

    Returns:
        A list of :class:`Suggestion` objects sorted by descending score.
        Each suggestion explains *why* the skill is recommended and what
        new capabilities it would unlock.

    Scoring heuristic (higher → better):
        * +3 per new capability the skill would produce that is not yet acquired.
        * +2 if all required CONSUMES are already satisfied.
        * +1 per optional CONSUMES that is already satisfied.
        * −5 if the skill has unmet required prerequisites (still returned
          but ranked low, with ``missing`` populated).
    """
    g = _load_graph()
    acq = frozenset(acquired)
    roe = frozenset(active_roe)

    suggestions: list[Suggestion] = []

    for skill in g.all_skill_names():
        # Skip forbidden skills
        if g.is_forbidden(skill, roe):
            continue

        produces = tuple(g.skill_produces.get(skill, []))
        consumes = tuple(g.skill_consumes.get(skill, []))

        # New capabilities this skill would add
        new_caps = [c for c in produces if c not in acq]
        if not new_caps:
            # Skill produces nothing new — skip
            continue

        satisfied = tuple(c for c in consumes if c in acq)
        missing_required = g.unsatisfied(skill, acq)
        missing = tuple(c for c in consumes if c not in acq)

        # Score
        score: float = 0.0
        score += 3.0 * len(new_caps)
        if not missing_required:
            score += 2.0
        else:
            score -= 5.0
        score += 1.0 * len(satisfied)

        # Reason
        parts: list[str] = []
        if new_caps:
            parts.append(f"unlocks {', '.join(new_caps)}")
        if satisfied:
            parts.append(f"prerequisites met: {', '.join(satisfied)}")
        if missing_required:
            parts.append(f"BLOCKED — needs: {', '.join(missing_required)}")
        reason = "; ".join(parts) if parts else "available"

        suggestions.append(Suggestion(
            skill=skill,
            produces=produces,
            consumes=consumes,
            satisfied=satisfied,
            missing=missing,
            score=score,
            reason=reason,
        ))

    # Sort descending by score, then alphabetically for determinism
    suggestions.sort(key=lambda s: (-s.score, s.skill))
    return suggestions[:top_k]


def get_skill_chain(
    goal_capability: str,
    *,
    acquired: Iterable[str] = (),
    active_roe: Iterable[str] = (),
    max_depth: int = 12,
) -> list[ChainStep]:
    """Compute a skill chain that reaches *goal_capability* from the current state.

    Uses a backward BFS from the goal capability through CONSUMES → PRODUCES
    edges.  Each step in the returned list is ordered so that step 0 should
    be executed first.

    Args:
        goal_capability: The desired end-state capability name
            (e.g. ``'c2-channel'``).
        acquired: Capability names already obtained.
        active_roe: Active RoE constraint names.
        max_depth: Maximum chain length before the search gives up.

    Returns:
        An ordered list of :class:`ChainStep` objects from first-to-execute
        to the step that produces the goal.  Returns an empty list if no
        valid chain exists or the goal is already acquired.

    Algorithm:
        1. If *goal_capability* ∈ *acquired*, return ``[]``.
        2. Find all skills that PRODUCE the goal.  Filter by RoE.
        3. For each candidate, check its CONSUMES.  If all required
           capabilities are in *acquired*, the skill is directly runnable —
           emit a single-step chain.
        4. Otherwise, recursively resolve each missing required capability
           as a sub-goal (BFS, cycle-safe).
        5. Flatten, de-duplicate, and topologically sort the steps.
    """
    g = _load_graph()
    acq = frozenset(acquired)
    roe = frozenset(active_roe)

    if goal_capability in acq:
        return []

    # BFS state
    visited_caps: set[str] = set()
    # Accumulate (skill, produces_set, requires_set) tuples
    plan_edges: list[tuple[str, frozenset[str], frozenset[str]]] = []

    queue: deque[str] = deque([goal_capability])
    visited_caps.add(goal_capability)
    depth = 0

    while queue and depth < max_depth:
        next_queue: deque[str] = deque()
        for cap in queue:
            # Find skills that produce this capability
            for skill in g.all_skill_names():
                if g.is_forbidden(skill, roe):
                    continue
                if cap not in g.skill_produces.get(skill, []):
                    continue

                produces = frozenset(g.skill_produces.get(skill, []))
                required_consumes = frozenset(
                    c for c in g.skill_consumes.get(skill, [])
                    if g.consumes_required.get((skill, c), False)
                )

                plan_edges.append((skill, produces, required_consumes))

                # Enqueue any required capabilities not yet acquired
                for req_cap in required_consumes:
                    if req_cap not in acq and req_cap not in visited_caps:
                        visited_caps.add(req_cap)
                        next_queue.append(req_cap)

        queue = next_queue
        depth += 1

    if not plan_edges:
        return []

    # De-duplicate by skill name, keeping the first (shortest-path) entry
    seen_skills: set[str] = set()
    unique_edges: list[tuple[str, frozenset[str], frozenset[str]]] = []
    for skill, produces, requires in plan_edges:
        if skill not in seen_skills:
            seen_skills.add(skill)
            unique_edges.append((skill, produces, requires))

    # Topological sort: a skill with no unmet required deps goes first
    ordered: list[tuple[str, frozenset[str], frozenset[str]]] = []
    remaining = list(unique_edges)
    available = set(acq)

    for _ in range(len(unique_edges) + 1):
        if not remaining:
            break
        runnable = [
            e for e in remaining
            if e[2].issubset(available)
        ]
        if not runnable:
            # Take the one with fewest missing requirements (best effort)
            remaining.sort(key=lambda e: len(e[2] - available))
            runnable = [remaining[0]]
        for entry in runnable:
            ordered.append(entry)
            available.update(entry[1])
            remaining.remove(entry)

    # Build ChainStep objects
    steps: list[ChainStep] = []
    for idx, (skill, produces, requires) in enumerate(ordered):
        composable = tuple(g.composes_with.get(skill, []))
        steps.append(ChainStep(
            order=idx,
            skill=skill,
            produces=tuple(sorted(produces)),
            requires=tuple(sorted(requires)),
            composable_with=composable,
        ))

    return steps


# ---------------------------------------------------------------------------
# Convenience: capability listing
# ---------------------------------------------------------------------------


def list_capabilities() -> list[Capability]:
    """Return all Capability nodes defined in the graph."""
    g = _load_graph()
    return sorted(g.capabilities.values(), key=lambda c: c.name)


def list_roe_constraints() -> list[tuple[str, str]]:
    """Return ``(name, description)`` for every RoE constraint in the graph."""
    g = _load_graph()
    return sorted(g.roe_constraints.items())


__all__ = [
    "Capability",
    "ChainStep",
    "Suggestion",
    "get_skill_chain",
    "list_capabilities",
    "list_roe_constraints",
    "suggest_next",
]
