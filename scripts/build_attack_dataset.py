#!/usr/bin/env python3
"""Dev-only regenerator for the bundled ATT&CK dataset and skill index.

ONLINE — downloads the MITRE ATT&CK Enterprise STIX bundle and flattens it
into the pruned JSON the runtime loads offline
(``decepticon/tools/research/attack/data/attack_enterprise.json``). Also
re-discovers the skill→technique map from the repo ``skills/`` tree into
``data/skill_techniques.json``.

The runtime never runs this — engagements load the pre-built JSON with zero
network access. Re-run this when bumping the pinned ATT&CK version.

Usage:
    python scripts/build_attack_dataset.py [--stix-url URL]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "decepticon" / "tools" / "research" / "attack" / "data"
_DEFAULT_STIX_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack.json"
)


def _mitre_ref(obj: dict) -> dict | None:
    """Return the ``mitre-attack`` external reference of a STIX object."""
    for ref in obj.get("external_references", []) or []:
        if ref.get("source_name") == "mitre-attack":
            return ref
    return None


def flatten_stix(bundle: dict) -> dict:
    """Flatten a STIX bundle into the pruned ``{version, tactics, techniques}``."""
    objects = bundle.get("objects", [])
    version = "unknown"
    tactics: list[dict] = []
    techniques: list[dict] = []

    for obj in objects:
        otype = obj.get("type")
        if otype == "x-mitre-collection":
            version = str(obj.get("x_mitre_version", version))
        elif otype == "x-mitre-tactic":
            if obj.get("x_mitre_deprecated") or obj.get("revoked"):
                continue
            ref = _mitre_ref(obj)
            if not ref or not ref.get("external_id"):
                continue
            tactics.append(
                {
                    "id": ref["external_id"],
                    "name": obj.get("name", ""),
                    "shortname": obj.get("x_mitre_shortname", ""),
                    "description": obj.get("description", ""),
                }
            )
        elif otype == "attack-pattern":
            if obj.get("x_mitre_deprecated") or obj.get("revoked"):
                continue
            ref = _mitre_ref(obj)
            if not ref or not ref.get("external_id"):
                continue
            ext_id = ref["external_id"]
            is_sub = bool(obj.get("x_mitre_is_subtechnique"))
            phases = [
                p["phase_name"]
                for p in obj.get("kill_chain_phases", []) or []
                if p.get("kill_chain_name") == "mitre-attack" and p.get("phase_name")
            ]
            techniques.append(
                {
                    "id": ext_id,
                    "name": obj.get("name", ""),
                    "tactics": phases,
                    "description": obj.get("description", ""),
                    "is_subtechnique": is_sub,
                    # Sub-technique IDs are <parent>.<nnn> by ATT&CK convention.
                    "parent": ext_id.rsplit(".", 1)[0] if (is_sub and "." in ext_id) else None,
                    "url": ref.get("url", ""),
                }
            )

    tactics.sort(key=lambda t: t["id"])
    techniques.sort(key=lambda t: t["id"])
    return {"version": version, "tactics": tactics, "techniques": techniques}


def build_skill_index() -> list[dict]:
    """Discover the skill→technique map from the repo ``skills/`` tree."""
    # Imported lazily so the script can run before the package is installed.
    sys.path.insert(0, str(_REPO_ROOT))
    from decepticon.tools.research.attack.skill_index import discover_skills

    records = discover_skills(_REPO_ROOT / "skills")
    return [r.model_dump() for r in records]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stix-url", default=_DEFAULT_STIX_URL)
    args = parser.parse_args()

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading ATT&CK STIX bundle from {args.stix_url} ...")
    resp = httpx.get(args.stix_url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    bundle = resp.json()

    catalog = flatten_stix(bundle)
    attack_path = _DATA_DIR / "attack_enterprise.json"
    attack_path.write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"Wrote {attack_path.relative_to(_REPO_ROOT)} — "
        f"ATT&CK v{catalog['version']}, "
        f"{len(catalog['techniques'])} techniques, {len(catalog['tactics'])} tactics"
    )

    skills = build_skill_index()
    skills_path = _DATA_DIR / "skill_techniques.json"
    skills_path.write_text(json.dumps(skills, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {skills_path.relative_to(_REPO_ROOT)} — {len(skills)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
