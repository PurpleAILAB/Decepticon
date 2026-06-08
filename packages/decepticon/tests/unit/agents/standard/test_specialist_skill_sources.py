from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.agents.standard import (
    forensicator,
    ics_operator,
    iot_operator,
    mobile_operator,
    osint_operator,
    phisher,
    supply_chain_operator,
    wireless_operator,
)
from decepticon.backends import SKILLS_LOCAL_PATH

_SKILLS_ROOT = Path(SKILLS_LOCAL_PATH)

# Every bash specialist that overrides ``_SKILL_SOURCES`` to a directory
# whose name differs from its role (or that simply pins an explicit set).
# Mapping: module -> the /skills/standard/ dir its primary content lives in.
_EXPLICIT_SOURCE_AGENTS = [
    (mobile_operator, "/skills/standard/mobile/"),
    (wireless_operator, "/skills/standard/wireless/"),
    (phisher, "/skills/standard/phisher/"),
    (osint_operator, "/skills/standard/osint/"),
    (iot_operator, "/skills/standard/iot/"),
    (ics_operator, "/skills/standard/ics/"),
    (forensicator, "/skills/standard/dfir/"),
    (supply_chain_operator, "/skills/standard/supply-chain/"),
]

# Agents whose role name does NOT match a /skills/standard/<role>/ dir, so
# they MUST override ``_SKILL_SOURCES`` (otherwise the default
# ``skills_sources_for(role)`` would resolve to a non-existent directory —
# the exact phisher-class bug this guards against). ``phisher`` is excluded:
# its role name and skill dir intentionally coincide.
_ROLE_NE_DIR_AGENTS = [
    mobile_operator,
    wireless_operator,
    osint_operator,
    iot_operator,
    ics_operator,
    forensicator,
    supply_chain_operator,
]


def _resolve(source: str) -> Path:
    assert source.startswith("/skills/")
    return _SKILLS_ROOT / source[len("/skills/") :].strip("/")


@pytest.mark.parametrize(("module", "expected_standard_dir"), _EXPLICIT_SOURCE_AGENTS)
def test_specialist_skill_source_dir_exists_and_non_empty(module, expected_standard_dir):
    assert expected_standard_dir in module._SKILL_SOURCES
    resolved = _resolve(expected_standard_dir)
    assert resolved.is_dir()
    # The dir must carry real skill content, not just exist — this is what
    # the phisher agent silently lacked (only an empty subdir) before wiring.
    assert any(resolved.rglob("SKILL.md"))


@pytest.mark.parametrize("module", _ROLE_NE_DIR_AGENTS)
def test_specialist_role_named_skill_dir_does_not_exist(module):
    role_dir = _SKILLS_ROOT / "standard" / module._ROLE
    assert not role_dir.exists()


@pytest.mark.parametrize("module", [m for m, _ in _EXPLICIT_SOURCE_AGENTS])
def test_specialist_skill_sources_all_resolve_on_disk(module):
    for source in module._SKILL_SOURCES:
        assert _resolve(source).is_dir()
