# ATT&CK Group Registry C1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing offline MITRE STIX importer to emit typed threat-actor nodes and their live ATT&CK technique relationships without changing its public interface.

**Architecture:** Reuse `emit_mitre_records()` and the existing `Node`/`Edge` graph model. Parse `intrusion-set` objects in the importer that already owns MITRE STIX, emit `:ThreatActor` nodes keyed by MITRE group ID, and emit `USES_TECHNIQUE` edges from live `uses` relationships. Do not add a parallel registry class, dependency, fixture file, CLI option, overlay system, or generated coverage report in C1.

**Tech Stack:** Python 3.13 standard library, existing Skillogy builder dataclasses, pytest, Ruff, basedpyright.

## Global Constraints

- Ponytail intensity is **Full** for every step: understand the complete path, then stop at the first ladder rung that works.
- Reuse `decepticon.skillogy.builder.mitre_stix.emit_mitre_records`; its signature remains `emit_mitre_records(bundle_path: Path) -> tuple[list[Node], list[Edge]]`.
- Add no runtime dependency and no public API.
- Production changes are limited to `mitre_stix.py`; tests stay in one new test module.
- Keep the C1 runtime diff below 400 lines, total changed files at or below 10, and one logical concern.
- Preserve current tactic, technique, sub-technique, and `MatrixVersion` behavior.
- Do not implement curated overlays, coverage JSON, Navigator output, Skillogy retrieval, Soundwave routing, documentation generation, or playbooks in C1.
- Do not weaken RoE, OPSEC, sandbox, or command-safety controls.
- Commit the failing tests before their corresponding implementation so the red/green sequence remains visible.
- Open a draft PR; never push to `main`.

## File Structure

- Modify `packages/decepticon/decepticon/skillogy/builder/mitre_stix.py`: parse MITRE groups, derive lifecycle status, emit `ThreatActor` nodes, and map live group `uses` relationships to techniques.
- Create `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`: one small STIX-shaped input builder plus the node, relationship, filtering, and deterministic-output checks.

## C1 Graph Contract

### `ThreatActor` Node

Natural key: `id`.

| Property | Type | Source |
|---|---|---|
| `id` | `str` | MITRE external ID, for example `G0016` |
| `stix_id` | `str` | STIX object ID |
| `name` | `str` | MITRE `name` |
| `description` | `str` | MITRE `description`, empty when absent |
| `mitre_aliases` | `list[str]` | Sorted unique string aliases from MITRE |
| `status` | `str` | `active`, `deprecated`, or `revoked`; revoked wins when both flags are true |
| `created` | `str` | STIX timestamp, empty when absent |
| `modified` | `str` | STIX timestamp, empty when absent |
| `matrix` | `str` | Constant `enterprise` |
| `framework` | `str` | Constant `attack` |
| `attck_version` | `str` | Existing `_ATTCK_VERSION` |
| `deprecated` | `bool` | `x_mitre_deprecated` |
| `revoked` | `bool` | `revoked` |

### Relationship

`(:ThreatActor {id})-[:USES_TECHNIQUE]->(:Technique {id})`

Only live STIX `relationship` objects with `relationship_type == "uses"`, a parsed MITRE group source, and a live imported technique target produce an edge. Unknown endpoints, software targets, deprecated techniques, revoked relationships, and malformed objects are ignored.

---

### Task 1: Commit the Failing Threat-Actor Node Contract

**Files:**
- Create: `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`

**Interfaces:**
- Consumes: `emit_mitre_records(bundle_path: Path) -> tuple[list[Node], list[Edge]]`.
- Produces: an executable contract for `ThreatActor` identity, aliases, lineage, and lifecycle state.

- [ ] **Step 1: Create the one-file STIX test input and failing node test**

Create `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decepticon.skillogy.builder.mitre_stix import emit_mitre_records


def _write_bundle(path: Path) -> Path:
    objects: list[dict[str, Any]] = [
        {
            "type": "x-mitre-tactic",
            "id": "x-mitre-tactic--initial-access",
            "name": "Initial Access",
            "x_mitre_shortname": "initial-access",
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "TA0001"}
            ],
        },
        {
            "type": "attack-pattern",
            "id": "attack-pattern--valid",
            "name": "Valid Accounts: Cloud Accounts",
            "description": "Use a valid cloud account.",
            "x_mitre_is_subtechnique": True,
            "x_mitre_platforms": ["IaaS", "Office Suite"],
            "kill_chain_phases": [
                {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}
            ],
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "T1078.004"}
            ],
        },
        {
            "type": "attack-pattern",
            "id": "attack-pattern--revoked-relation-target",
            "name": "Exploit Public-Facing Application",
            "description": "Exploit an exposed service.",
            "x_mitre_is_subtechnique": False,
            "x_mitre_platforms": ["Linux"],
            "kill_chain_phases": [
                {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}
            ],
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "T1190"}
            ],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--apt29",
            "name": "APT29",
            "description": "A test actor.",
            "aliases": ["Cozy Bear", "APT 29", "Cozy Bear"],
            "created": "2017-05-31T21:31:53.197Z",
            "modified": "2026-04-10T18:05:06.814Z",
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "G0016"}
            ],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--deprecated",
            "name": "Deprecated Group",
            "aliases": [],
            "created": "2018-01-01T00:00:00.000Z",
            "modified": "2020-01-01T00:00:00.000Z",
            "x_mitre_deprecated": True,
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "G9998"}
            ],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--revoked",
            "name": "Revoked Group",
            "aliases": ["Old Alias"],
            "created": "2018-01-01T00:00:00.000Z",
            "modified": "2021-01-01T00:00:00.000Z",
            "revoked": True,
            "x_mitre_deprecated": True,
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "G9999"}
            ],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--no-mitre-id",
            "name": "Unidentified Group",
            "external_references": [{"source_name": "vendor", "external_id": "V1"}],
        },
        {
            "type": "relationship",
            "id": "relationship--live-uses",
            "relationship_type": "uses",
            "source_ref": "intrusion-set--apt29",
            "target_ref": "attack-pattern--valid",
        },
        {
            "type": "relationship",
            "id": "relationship--revoked-uses",
            "relationship_type": "uses",
            "source_ref": "intrusion-set--apt29",
            "target_ref": "attack-pattern--revoked-relation-target",
            "revoked": True,
        },
    ]
    path.write_text(json.dumps({"type": "bundle", "objects": objects}), encoding="utf-8")
    return path


def test_emit_mitre_records_emits_threat_actor_contract(tmp_path: Path) -> None:
    nodes, _ = emit_mitre_records(_write_bundle(tmp_path / "enterprise.json"))
    actors = {node.key: node.properties for node in nodes if node.label == "ThreatActor"}

    assert set(actors) == {"G0016", "G9998", "G9999"}
    assert actors["G0016"] == {
        "id": "G0016",
        "stix_id": "intrusion-set--apt29",
        "name": "APT29",
        "description": "A test actor.",
        "mitre_aliases": ["APT 29", "Cozy Bear"],
        "status": "active",
        "created": "2017-05-31T21:31:53.197Z",
        "modified": "2026-04-10T18:05:06.814Z",
        "matrix": "enterprise",
        "framework": "attack",
        "attck_version": "19.1",
        "deprecated": False,
        "revoked": False,
    }
    assert actors["G9998"]["status"] == "deprecated"
    assert actors["G9999"]["status"] == "revoked"
```

- [ ] **Step 2: Run the focused test and observe the missing actor behavior**

Run:

```bash
uv run pytest packages/decepticon/tests/unit/skillogy/test_mitre_stix.py::test_emit_mitre_records_emits_threat_actor_contract -v
```

Expected: FAIL because `actors` is empty and does not contain `G0016`, `G9998`, or `G9999`.

- [ ] **Step 3: Commit the red test**

```bash
git add packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
git commit -m "test(skillogy): define threat actor import contract"
```

Expected: one commit containing only the failing contract test.

---

### Task 2: Emit Minimal Threat-Actor Nodes

**Files:**
- Modify: `packages/decepticon/decepticon/skillogy/builder/mitre_stix.py`
- Test: `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`

**Interfaces:**
- Consumes: `_attck_id(obj)` and the existing `Node` graph record.
- Produces: `_group_status(obj: dict[str, Any]) -> str` and `ThreatActor` nodes returned by the unchanged `emit_mitre_records()` interface.

- [ ] **Step 1: Add the lifecycle helper beside `_is_alive`**

Add:

```python
def _group_status(obj: dict[str, Any]) -> str:
    if obj.get("revoked"):
        return "revoked"
    if obj.get("x_mitre_deprecated"):
        return "deprecated"
    return "active"
```

- [ ] **Step 2: Collect MITRE `intrusion-set` objects in the existing parse loop**

Initialize the group map beside `technique_by_id`:

```python
group_by_id: dict[str, dict[str, Any]] = {}
```

Add this branch before relationship handling:

```python
elif otype == "intrusion-set":
    attck_id = _attck_id(obj)
    if not attck_id:
        continue
    group_by_id[attck_id] = obj
    uuid_to_attck[str(obj.get("id") or "")] = attck_id
```

- [ ] **Step 3: Emit the actor nodes before the `MatrixVersion` node**

Add:

```python
for attck_id, group in sorted(group_by_id.items()):
    aliases = sorted(
        {alias for alias in group.get("aliases") or [] if isinstance(alias, str) and alias}
    )
    nodes.append(
        Node(
            label="ThreatActor",
            key_field="id",
            properties={
                "id": attck_id,
                "stix_id": str(group.get("id") or ""),
                "name": str(group.get("name") or ""),
                "description": str(group.get("description") or ""),
                "mitre_aliases": aliases,
                "status": _group_status(group),
                "created": str(group.get("created") or ""),
                "modified": str(group.get("modified") or ""),
                "matrix": "enterprise",
                "framework": "attack",
                "attck_version": _ATTCK_VERSION,
                "deprecated": bool(group.get("x_mitre_deprecated", False)),
                "revoked": bool(group.get("revoked", False)),
            },
        )
    )
```

- [ ] **Step 4: Run the node contract test**

Run:

```bash
uv run pytest packages/decepticon/tests/unit/skillogy/test_mitre_stix.py::test_emit_mitre_records_emits_threat_actor_contract -v
```

Expected: PASS.

- [ ] **Step 5: Run focused lint and format checks**

Run:

```bash
uv run ruff check packages/decepticon/decepticon/skillogy/builder/mitre_stix.py packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
uv run ruff format --check packages/decepticon/decepticon/skillogy/builder/mitre_stix.py packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit the green implementation**

```bash
git add packages/decepticon/decepticon/skillogy/builder/mitre_stix.py
git commit -m "feat(skillogy): import MITRE threat actors"
```

Expected: the previously committed node test now passes without changing its assertions.

---

### Task 3: Commit the Failing Actor-to-Technique Relationship Contract

**Files:**
- Modify: `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`

**Interfaces:**
- Consumes: the `ThreatActor` nodes from Task 2 and existing live `Technique` nodes.
- Produces: the exact `USES_TECHNIQUE` edge and revoked-relationship filtering contract.

- [ ] **Step 1: Append the failing relationship test**

Append:

```python
def test_emit_mitre_records_links_only_live_group_technique_usage(tmp_path: Path) -> None:
    _, edges = emit_mitre_records(_write_bundle(tmp_path / "enterprise.json"))
    uses = [edge for edge in edges if edge.edge_type == "USES_TECHNIQUE"]

    assert len(uses) == 1
    edge = uses[0]
    assert (
        edge.from_label,
        edge.from_key_field,
        edge.from_key,
        edge.to_label,
        edge.to_key_field,
        edge.to_key,
    ) == ("ThreatActor", "id", "G0016", "Technique", "id", "T1078.004")
```

- [ ] **Step 2: Run the relationship test and observe the missing edge**

Run:

```bash
uv run pytest packages/decepticon/tests/unit/skillogy/test_mitre_stix.py::test_emit_mitre_records_links_only_live_group_technique_usage -v
```

Expected: FAIL because `uses` is empty.

- [ ] **Step 3: Commit the red relationship test**

```bash
git add packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
git commit -m "test(skillogy): define actor technique relationships"
```

Expected: one commit containing only the failing edge assertion.

---

### Task 4: Emit Live `USES_TECHNIQUE` Edges

**Files:**
- Modify: `packages/decepticon/decepticon/skillogy/builder/mitre_stix.py`
- Test: `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`

**Interfaces:**
- Consumes: `uuid_to_attck`, `group_by_id`, `technique_by_id`, and live STIX `uses` relationships.
- Produces: deterministic `Edge(edge_type="USES_TECHNIQUE", ...)` records from `ThreatActor` to `Technique`.

- [ ] **Step 1: Track live group-use relationships without changing sub-technique behavior**

Initialize a second relationship list:

```python
uses_relationships: list[dict[str, Any]] = []
```

Replace only the relationship branch with:

```python
elif otype == "relationship":
    relationship_type = obj.get("relationship_type")
    if relationship_type == "subtechnique-of":
        relationships.append(obj)
    elif relationship_type == "uses" and _is_alive(obj):
        uses_relationships.append(obj)
```

- [ ] **Step 2: Emit group-to-technique edges after sub-technique edges**

Add:

```python
for rel in uses_relationships:
    group_id = uuid_to_attck.get(str(rel.get("source_ref") or ""))
    technique_id = uuid_to_attck.get(str(rel.get("target_ref") or ""))
    if group_id not in group_by_id or technique_id not in technique_by_id:
        continue
    edges.append(
        Edge(
            edge_type="USES_TECHNIQUE",
            from_label="ThreatActor",
            from_key_field="id",
            from_key=group_id,
            to_label="Technique",
            to_key_field="id",
            to_key=technique_id,
        )
    )
```

- [ ] **Step 3: Run the complete focused test module**

Run:

```bash
uv run pytest packages/decepticon/tests/unit/skillogy/test_mitre_stix.py -v
```

Expected: 2 tests pass. The revoked relationship to `T1190` produces no edge.

- [ ] **Step 4: Run focused lint, format, and type checks**

Run:

```bash
uv run ruff check packages/decepticon/decepticon/skillogy/builder/mitre_stix.py packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
uv run ruff format --check packages/decepticon/decepticon/skillogy/builder/mitre_stix.py packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
uv run basedpyright packages/decepticon/decepticon/skillogy/builder/mitre_stix.py packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
```

Expected: all commands exit 0 with no errors.

- [ ] **Step 5: Commit the green relationship implementation**

```bash
git add packages/decepticon/decepticon/skillogy/builder/mitre_stix.py
git commit -m "feat(skillogy): link actors to ATT&CK techniques"
```

Expected: the red relationship test from Task 3 passes unchanged.

---

### Task 5: Add the Determinism Check and Verify the Real Builder Path

**Files:**
- Modify: `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`

**Interfaces:**
- Consumes: `emit_mitre_records()` and the production `emit_cypher()` renderer.
- Produces: one runnable regression check proving input order cannot change generated actor Cypher.

- [ ] **Step 1: Import the production emitter and append the determinism test**

Add this import:

```python
from decepticon.skillogy.builder.emit import emit_cypher
```

Append:

```python
def test_threat_actor_cypher_is_independent_of_stix_object_order(tmp_path: Path) -> None:
    original = _write_bundle(tmp_path / "original.json")
    payload = json.loads(original.read_text(encoding="utf-8"))
    payload["objects"].reverse()
    reversed_bundle = tmp_path / "reversed.json"
    reversed_bundle.write_text(json.dumps(payload), encoding="utf-8")

    assert emit_cypher(*emit_mitre_records(original)) == emit_cypher(
        *emit_mitre_records(reversed_bundle)
    )
```

- [ ] **Step 2: Run all focused tests**

Run:

```bash
uv run pytest packages/decepticon/tests/unit/skillogy/test_mitre_stix.py -v
```

Expected: 3 tests pass.

- [ ] **Step 3: Run the actual builder against the pinned Enterprise bundle**

Run:

```bash
uv run python -m decepticon.skillogy.builder \
  --stix-bundle "${SKILLOGY_STIX_BUNDLE:-$HOME/.cache/skillogy/mitre/enterprise-attack-19.1.json}" \
  --frozen-built-at \
  --out /tmp/decepticon-c1-skills.cypher
rg -n "MERGE \(n:ThreatActor \{id: 'G0016'\}\)|USES_TECHNIQUE" /tmp/decepticon-c1-skills.cypher | head
rm /tmp/decepticon-c1-skills.cypher
```

Expected: the builder exits 0; the first `rg` output includes the `G0016` `ThreatActor` merge and at least one `USES_TECHNIQUE` edge. If the pinned bundle is unavailable, stop and acquire the exact v19.1 bundle; do not substitute a moving `master` snapshot or claim end-to-end verification from unit tests alone.

- [ ] **Step 4: Commit the deterministic regression check**

```bash
git add packages/decepticon/tests/unit/skillogy/test_mitre_stix.py
git commit -m "test(skillogy): lock actor import determinism"
```

Expected: one test-only commit; branch head remains green.

---

### Task 6: Run Project Gates and Ponytail Full Review

**Files:**
- Review only: `packages/decepticon/decepticon/skillogy/builder/mitre_stix.py`
- Review only: `packages/decepticon/tests/unit/skillogy/test_mitre_stix.py`

**Interfaces:**
- Consumes: the complete C1 diff.
- Produces: merge evidence and a draft PR with no unresolved complexity findings.

- [ ] **Step 1: Run the repository PR gates**

Run:

```bash
make ci-lint
make ci-test
```

Expected: both targets exit 0. Record the final output in the PR body.

- [ ] **Step 2: Verify the diff budget and banned-pattern contract**

Run:

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
git diff --numstat main...HEAD
rg -n "except Exception: pass|except:|# type: ignore($| )|# pyright: ignore($| )|# noqa($| )|T[O]DO|F[I]XME|NotImplementedError|pytest.mark.(skip|xfail)" \
  packages/decepticon/decepticon/skillogy/builder/mitre_stix.py \
  packages/decepticon/tests/unit/skillogy/test_mitre_stix.py || true
```

Expected: no whitespace errors, at most 2 changed implementation/test files, runtime diff below 400 lines, and no banned-pattern match introduced by C1.

- [ ] **Step 3: Apply Ponytail Full to the final diff**

Review `git diff main...HEAD` using the official Ponytail ladder and `ponytail-review` format:

1. Confirm C1 still needs to exist to satisfy the approved denominator foundation.
2. Confirm it reuses `emit_mitre_records`, `Node`, `Edge`, `_attck_id`, `_is_alive`, `uuid_to_attck`, and `emit_cypher`.
3. Confirm all new behavior uses the standard library and existing test stack.
4. Confirm there is no new class, schema framework, config flag, fixture file, dependency, public API, or speculative overlay hook.
5. Report any complexity finding as `file:L<line>: <tag> <what>. <replacement>.` and fix it before opening the PR.
6. If nothing can be removed, record `Lean already. Ship.` in the PR body.

Expected: no unresolved Ponytail finding.

- [ ] **Step 4: Write the end-to-end verification statement**

Use the observed values from Task 5 and the project gates. The statement must name:

- the exact pinned bundle path and ATT&CK version;
- the builder command;
- the observed actor node and relationship output;
- the focused test count;
- `make ci-lint` and `make ci-test` results;
- any honest environment gap.

- [ ] **Step 5: Push the isolated branch and open a draft C1 PR**

Use branch `agent/attck-group-registry-c1`. Target the branch containing approved C0 until C0 merges; retarget to `main` after merge. The PR body must include What changed, Why, Impact, Ponytail Full review, Testing, End-to-end verification, and Anti-goal sections.

Expected: draft PR contains only C1 runtime/test changes and preserves the red/green commit sequence.
