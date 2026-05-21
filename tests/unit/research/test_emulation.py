"""Unit tests for adversary emulation — TTPs to OPPLAN objectives."""

from __future__ import annotations

import json

from decepticon.core.schemas import ThreatActor, ThreatProfile, ThreatTier
from decepticon.tools.research.attack.emulation import (
    plan_objectives_from_actor,
    plan_objectives_from_ttps,
    suggest_objectives_from_actor,
)

# Real, stable ATT&CK IDs spanning the kill chain:
#   T1595  Active Scanning              → reconnaissance  → recon
#   T1190  Exploit Public-Facing App    → initial-access  → initial-access
#   T1003  OS Credential Dumping        → credential-access → post-exploit
#   T1486  Data Encrypted for Impact    → impact          → exfiltration


class TestPlanObjectivesFromTtps:
    def test_builds_one_objective_per_technique(self) -> None:
        drafts = plan_objectives_from_ttps(["T1595", "T1190"])
        assert len(drafts) == 2
        assert all(d["mitre"] and d["title"] and d["acceptance_criteria"] for d in drafts)

    def test_objectives_ordered_by_kill_chain_phase(self) -> None:
        drafts = plan_objectives_from_ttps(["T1486", "T1595", "T1190"])
        phases = [d["phase"] for d in drafts]
        assert phases == ["recon", "initial-access", "exfiltration"]
        assert [d["priority"] for d in drafts] == [1, 2, 3]

    def test_credential_access_maps_to_post_exploit(self) -> None:
        drafts = plan_objectives_from_ttps(["T1003"])
        assert drafts[0]["phase"] == "post-exploit"

    def test_unknown_technique_is_skipped(self) -> None:
        drafts = plan_objectives_from_ttps(["T1190", "T9999"])
        assert len(drafts) == 1
        assert drafts[0]["mitre"] == ["T1190"]

    def test_dedupes_repeated_techniques(self) -> None:
        drafts = plan_objectives_from_ttps(["T1190", "t1190"])
        assert len(drafts) == 1

    def test_accepts_comma_string(self) -> None:
        drafts = plan_objectives_from_ttps("T1595, T1190")
        assert len(drafts) == 2

    def test_empty_input(self) -> None:
        assert plan_objectives_from_ttps([]) == []


class TestPlanObjectivesFromActor:
    def test_from_conops_threat_actor(self) -> None:
        actor = ThreatActor(
            name="APT-Test",
            sophistication="high",
            motivation="espionage",
            ttps=["T1595", "T1190"],
        )
        drafts = plan_objectives_from_actor(actor)
        assert len(drafts) == 2
        assert "APT-Test" in drafts[0]["description"]

    def test_from_threat_profile_includes_initial_access(self) -> None:
        profile = ThreatProfile(
            engagement_name="acme",
            actor_name="APT29-like",
            tier=ThreatTier.TIER_3,
            sophistication="high",
            motivation="espionage",
            initial_access=["T1190"],
            key_ttps=["T1003"],
        )
        drafts = plan_objectives_from_actor(profile)
        mitre = {d["mitre"][0] for d in drafts}
        assert mitre == {"T1190", "T1003"}


class TestSuggestObjectivesFromActorTool:
    def test_returns_draft_objectives(self) -> None:
        payload = json.loads(
            suggest_objectives_from_actor.invoke(
                {"actor_name": "APT29", "key_ttps": "T1595, T1190"}
            )
        )
        assert payload["count"] == 2
        assert payload["objectives"][0]["phase"] == "recon"
