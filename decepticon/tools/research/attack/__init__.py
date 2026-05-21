"""ATT&CK spine — MITRE ATT&CK as the join key between the skill library
and the attack knowledge graph.

This package bundles a pruned, offline ATT&CK Enterprise dataset and the
loaders/seeders that promote ``Technique`` and ``Skill`` to first-class,
pre-seeded layers in the Neo4j attack graph. Everything here works without
network access — engagements run in network-isolated sandboxes.
"""
