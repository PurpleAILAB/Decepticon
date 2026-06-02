"""Skillogy graph builder — CI-time compiler that turns SKILL.md +
seeds + MITRE STIX into ``skills/.graph/skills.cypher``.

The builder is the one component that owns the graph schema. Its output
is a deterministic Cypher dump checked into the repo so every change is
reviewable via PR diff. Runtime (the skillogy server) loads the dump
into Neo4j on startup; it does not invoke the builder.

Layout
------
- ``seeds/*.yaml`` — canonical seed data (Phase, AssetType, MoC).
- ``seeds.py`` — typed loader for the seed YAML.
- (forthcoming) ``model.py`` — Cypher node/edge dataclasses.
- (forthcoming) ``skills.py`` — SKILL.md → :Skill node + explicit edges.
- (forthcoming) ``mitre_stix.py`` — MITRE ATT&CK Enterprise v19.1 importer.
- (forthcoming) ``emit.py`` — deterministic Cypher emitter.
- (forthcoming) ``validate.py`` — Cypher rules R1–R6 (see spec §5.9).
- (forthcoming) ``manifest.py`` — manifest.json with build stats + version pins.
- (forthcoming) ``cli.py`` — ``python -m decepticon.skillogy.builder``.

See ``docs/design/skillogy-brain-redesign.md`` §5 for the full spec.
"""

from decepticon.skillogy.builder.seeds import (
    AssetTypeSeed,
    MocSeed,
    PhaseSeed,
    load_asset_types,
    load_mocs,
    load_phases,
)

__all__ = [
    "AssetTypeSeed",
    "MocSeed",
    "PhaseSeed",
    "load_asset_types",
    "load_mocs",
    "load_phases",
]
