from __future__ import annotations

from pathlib import Path

from decepticon.capabilities.contracts import (
    CapabilityLane,
    discover_contracts,
    validate_contract_metadata,
)
from decepticon.skill_audit.rules import RuleId, validate_skill_file


def _contract() -> dict[str, object]:
    return {
        "lane": "web3",
        "scope": "isolated-lab",
        "environment": ["anvil"],
        "required_tools": ["forge", "slither"],
        "evidence": ["poc-test", "trace"],
        "verification": "forge test --match-test testExploit",
        "negative_control": "forge test --match-test testBaseline",
        "scorecard": ["validated-rate"],
        "benchmark": "held-out-web3",
    }


def test_contract_metadata_accepts_complete_contract() -> None:
    assert validate_contract_metadata({"capability_contract": _contract()}) == []


def test_contract_metadata_rejects_unknown_fields_and_missing_negative_control() -> None:
    raw = _contract()
    raw.pop("negative_control")
    raw["surprise"] = "unsupported"

    details = validate_contract_metadata({"capability_contract": raw})

    assert any("negative_control" in detail for detail in details)
    assert any("surprise" in detail for detail in details)


def test_skill_audit_reports_invalid_capability_contract() -> None:
    text = """---
name: malformed-contract
description: test skill
metadata:
  subdomain: smart-contracts
  when_to_use: test
  upstream_ref: test fixture
  capability_contract: not-a-mapping
---
body
"""

    violations = validate_skill_file("/skills/standard/contracts/test/SKILL.md", text)

    assert [violation.rule_id for violation in violations] == [RuleId.BAD_CAPABILITY_CONTRACT]


def test_discover_contracts_loads_only_declared_valid_contracts(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    web3 = root / "standard" / "contracts" / "web3"
    web3.mkdir(parents=True)
    web3.joinpath("SKILL.md").write_text(
        "---\n"
        "name: web3-contract\n"
        "description: test contract\n"
        "metadata:\n"
        "  subdomain: smart-contracts\n"
        "  when_to_use: test\n"
        "  capability_contract:\n"
        "    lane: web3\n"
        "    scope: isolated-lab\n"
        "    environment: [anvil]\n"
        "    required_tools: [forge]\n"
        "    evidence: [poc-test]\n"
        "    verification: forge test\n"
        "    negative_control: forge test --match-test baseline\n"
        "    scorecard: [validated-rate]\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    legacy = root / "standard" / "recon" / "legacy"
    legacy.mkdir(parents=True)
    legacy.joinpath("SKILL.md").write_text(
        "---\nname: legacy\ndescription: legacy\nmetadata:\n  subdomain: reconnaissance\n"
        "  when_to_use: test\n---\nbody\n",
        encoding="utf-8",
    )
    contracts, issues = discover_contracts(root)

    assert issues == []
    assert len(contracts) == 1
    assert contracts[0].skill_name == "web3-contract"
    assert contracts[0].contract.lane is CapabilityLane.WEB3


def test_shipped_specialist_contracts_cover_every_supported_lane() -> None:
    from decepticon.backends import SKILLS_LOCAL_PATH

    contracts, issues = discover_contracts(Path(SKILLS_LOCAL_PATH))

    assert issues == []
    assert {item.contract.lane for item in contracts} == {
        CapabilityLane.WEB,
        CapabilityLane.WEB3,
        CapabilityLane.REVERSE_ENGINEERING,
        CapabilityLane.ACTIVE_DIRECTORY,
        CapabilityLane.WINDOWS_INTERNALS,
        CapabilityLane.GAME_SECURITY,
    }
