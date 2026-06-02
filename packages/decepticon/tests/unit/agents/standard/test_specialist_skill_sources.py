from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.agents.standard import mobile_operator, wireless_operator
from decepticon.backends import SKILLS_LOCAL_PATH

_SKILLS_ROOT = Path(SKILLS_LOCAL_PATH)


def _resolve(source: str) -> Path:
    assert source.startswith("/skills/")
    return _SKILLS_ROOT / source[len("/skills/") :].strip("/")


@pytest.mark.parametrize(
    ("module", "expected_standard_dir"),
    [
        (mobile_operator, "/skills/standard/mobile/"),
        (wireless_operator, "/skills/standard/wireless/"),
    ],
)
def test_specialist_skill_source_dir_exists_and_non_empty(module, expected_standard_dir):
    assert expected_standard_dir in module._SKILL_SOURCES
    resolved = _resolve(expected_standard_dir)
    assert resolved.is_dir()
    assert any(resolved.iterdir())


@pytest.mark.parametrize("module", [mobile_operator, wireless_operator])
def test_specialist_role_named_skill_dir_does_not_exist(module):
    role_dir = _SKILLS_ROOT / "standard" / module._ROLE
    assert not role_dir.exists()


@pytest.mark.parametrize("module", [mobile_operator, wireless_operator])
def test_specialist_skill_sources_all_resolve_on_disk(module):
    for source in module._SKILL_SOURCES:
        assert _resolve(source).is_dir()
