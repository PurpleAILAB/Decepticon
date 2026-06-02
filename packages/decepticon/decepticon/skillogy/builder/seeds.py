"""Typed loader for the seed YAML in ``builder/seeds/``.

Each top-level seed (Phase, AssetType, MoC) is exposed as a frozen
dataclass + a ``load_*`` function that reads + validates the YAML
file. Validation is strict: missing required fields or unknown keys
fail the build, because seed drift is the most likely source of silent
schema corruption.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

_SEEDS_DIR: Final[Path] = Path(__file__).parent / "seeds"
PHASES_YAML: Final[Path] = _SEEDS_DIR / "phases.yaml"
ASSET_TYPES_YAML: Final[Path] = _SEEDS_DIR / "asset_types.yaml"
MOC_YAML: Final[Path] = _SEEDS_DIR / "moc.yaml"


@dataclass(frozen=True, slots=True)
class PhaseSeed:
    name: str
    kill_chain_order: int
    kind: str  # tactic | domain | meta


@dataclass(frozen=True, slots=True)
class AssetTypeSeed:
    name: str
    category: str


@dataclass(frozen=True, slots=True)
class MocSeed:
    name: str
    parent_phase: str
    description: str


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"seed YAML missing: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected YAML mapping at top level")
    return raw


def load_phases() -> list[PhaseSeed]:
    """Load canonical phases from ``seeds/phases.yaml``.

    Raises ``ValueError`` on duplicate names, missing fields, or unknown ``kind``.
    """
    raw = _read_yaml(PHASES_YAML)
    entries = raw.get("phases")
    if not isinstance(entries, list):
        raise ValueError(f"{PHASES_YAML}: top-level 'phases' must be a list")
    seen: set[str] = set()
    out: list[PhaseSeed] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{PHASES_YAML}: each entry must be a mapping")
        try:
            name = str(entry["name"])
            order = int(entry["kill_chain_order"])
            kind = str(entry["kind"])
        except KeyError as exc:
            raise ValueError(
                f"{PHASES_YAML}: missing required field {exc.args[0]!r} in entry {entry!r}"
            ) from exc
        if kind not in {"tactic", "domain", "meta"}:
            raise ValueError(
                f"{PHASES_YAML}: phase {name!r} has unknown kind {kind!r} (expected tactic|domain|meta)"
            )
        if name in seen:
            raise ValueError(f"{PHASES_YAML}: duplicate phase name {name!r}")
        seen.add(name)
        out.append(PhaseSeed(name=name, kill_chain_order=order, kind=kind))
    return out


def load_asset_types() -> list[AssetTypeSeed]:
    """Load AssetType taxonomy from ``seeds/asset_types.yaml``."""
    raw = _read_yaml(ASSET_TYPES_YAML)
    entries = raw.get("asset_types")
    if not isinstance(entries, list):
        raise ValueError(f"{ASSET_TYPES_YAML}: top-level 'asset_types' must be a list")
    seen: set[str] = set()
    out: list[AssetTypeSeed] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{ASSET_TYPES_YAML}: each entry must be a mapping")
        try:
            name = str(entry["name"])
            category = str(entry["category"])
        except KeyError as exc:
            raise ValueError(
                f"{ASSET_TYPES_YAML}: missing required field {exc.args[0]!r} in entry {entry!r}"
            ) from exc
        if name in seen:
            raise ValueError(f"{ASSET_TYPES_YAML}: duplicate asset type name {name!r}")
        seen.add(name)
        out.append(AssetTypeSeed(name=name, category=category))
    # Sanity check: every non-root category must also exist as a node.
    names = {at.name for at in out}
    for at in out:
        if at.category != "root" and at.category not in names:
            raise ValueError(
                f"{ASSET_TYPES_YAML}: asset type {at.name!r} points at category "
                f"{at.category!r} which is not declared as an asset type"
            )
    return out


def load_mocs() -> list[MocSeed]:
    """Load Map-of-Concepts entries from ``seeds/moc.yaml``."""
    raw = _read_yaml(MOC_YAML)
    entries = raw.get("mocs")
    if not isinstance(entries, list):
        raise ValueError(f"{MOC_YAML}: top-level 'mocs' must be a list")
    seen: set[str] = set()
    out: list[MocSeed] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{MOC_YAML}: each entry must be a mapping")
        try:
            name = str(entry["name"])
            parent = str(entry["parent_phase"])
            desc = str(entry["description"])
        except KeyError as exc:
            raise ValueError(
                f"{MOC_YAML}: missing required field {exc.args[0]!r} in entry {entry!r}"
            ) from exc
        if name in seen:
            raise ValueError(f"{MOC_YAML}: duplicate MoC name {name!r}")
        seen.add(name)
        out.append(MocSeed(name=name, parent_phase=parent, description=desc))
    # Sanity check: parent_phase must reference a real phase.
    phase_names = {p.name for p in load_phases()}
    for moc in out:
        if moc.parent_phase not in phase_names:
            raise ValueError(
                f"{MOC_YAML}: MoC {moc.name!r} references unknown parent_phase {moc.parent_phase!r}"
            )
    return out
