from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decepticon.skillogy.builder.emit import emit_cypher
from decepticon.skillogy.builder.mitre_stix import emit_mitre_records


def _write_bundle(path: Path) -> Path:
    objects: list[dict[str, Any]] = [
        {
            "type": "x-mitre-tactic",
            "id": "x-mitre-tactic--initial-access",
            "name": "Initial Access",
            "x_mitre_shortname": "initial-access",
            "external_references": [{"source_name": "mitre-attack", "external_id": "TA0001"}],
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
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1078.004"}],
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
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1190"}],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--apt29",
            "name": "APT29",
            "description": "A test actor.",
            "aliases": ["Cozy Bear", "APT 29", "Cozy Bear"],
            "created": "2017-05-31T21:31:53.197Z",
            "modified": "2026-04-10T18:05:06.814Z",
            "external_references": [{"source_name": "mitre-attack", "external_id": "G0016"}],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--deprecated",
            "name": "Deprecated Group",
            "aliases": [],
            "created": "2018-01-01T00:00:00.000Z",
            "modified": "2020-01-01T00:00:00.000Z",
            "x_mitre_deprecated": True,
            "external_references": [{"source_name": "mitre-attack", "external_id": "G9998"}],
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
            "external_references": [{"source_name": "mitre-attack", "external_id": "G9999"}],
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


def test_emit_mitre_records_rejects_missing_uses_endpoint_collision(tmp_path: Path) -> None:
    bundle_path = _write_bundle(tmp_path / "enterprise.json")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["objects"].extend(
        [
            {
                "type": "intrusion-set",
                "name": "Missing STIX ID",
                "external_references": [{"source_name": "mitre-attack", "external_id": "G9997"}],
            },
            {
                "type": "relationship",
                "id": "relationship--missing-source",
                "relationship_type": "uses",
                "target_ref": "attack-pattern--valid",
            },
        ]
    )
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    _, edges = emit_mitre_records(bundle_path)
    uses = [edge for edge in edges if edge.edge_type == "USES_TECHNIQUE"]

    assert [(edge.from_key, edge.to_key) for edge in uses] == [("G0016", "T1078.004")]


def test_threat_actor_cypher_is_independent_of_stix_object_order(tmp_path: Path) -> None:
    original = _write_bundle(tmp_path / "original.json")
    payload = json.loads(original.read_text(encoding="utf-8"))
    payload["objects"].reverse()
    reversed_bundle = tmp_path / "reversed.json"
    reversed_bundle.write_text(json.dumps(payload), encoding="utf-8")

    original_cypher = emit_cypher(*emit_mitre_records(original))
    reversed_cypher = emit_cypher(*emit_mitre_records(reversed_bundle))

    assert "MERGE (n:ThreatActor {id: 'G0016'})" in original_cypher
    assert "[r:USES_TECHNIQUE]" in original_cypher
    assert original_cypher == reversed_cypher
