"""Unit tests for the ATT&CK catalog — ID normalization, parsing, lookups."""

from __future__ import annotations

import pytest

from decepticon.tools.research.attack.catalog import (
    AttackTactic,
    AttackTechnique,
    load_attack_catalog,
    normalize,
    parse_catalog,
    parse_ids,
)


class TestParseIds:
    def test_splits_and_normalizes_comma_string(self) -> None:
        assert parse_ids("t1190, T1059, ta0003") == ["T1190", "T1059", "TA0003"]

    def test_accepts_list(self) -> None:
        assert parse_ids(["T1190", "t1059"]) == ["T1190", "T1059"]

    def test_drops_invalid_and_dedupes(self) -> None:
        assert parse_ids("T1190 junk T1190") == ["T1190"]

    def test_empty_and_none(self) -> None:
        assert parse_ids("") == []
        assert parse_ids(None) == []


# ── normalize() ──────────────────────────────────────────────────────────


class TestNormalize:
    def test_uppercases_lowercase_technique(self) -> None:
        assert normalize("t1190") == "T1190"

    def test_preserves_valid_technique(self) -> None:
        assert normalize("T1190") == "T1190"

    def test_preserves_subtechnique(self) -> None:
        assert normalize("t1558.003") == "T1558.003"

    def test_normalizes_tactic_id(self) -> None:
        assert normalize("ta0003") == "TA0003"

    def test_strips_whitespace(self) -> None:
        assert normalize("  T1190  ") == "T1190"

    def test_rejects_garbage(self) -> None:
        assert normalize("not-a-technique") is None

    def test_rejects_empty(self) -> None:
        assert normalize("") is None

    def test_rejects_none(self) -> None:
        assert normalize(None) is None

    def test_rejects_wrong_digit_count(self) -> None:
        assert normalize("T119") is None
        assert normalize("T11900") is None

    def test_rejects_malformed_subtechnique(self) -> None:
        assert normalize("T1558.3") is None


# ── parse_catalog() / AttackCatalog ──────────────────────────────────────

_FIXTURE = {
    "version": "17.1",
    "tactics": [
        {
            "id": "TA0043",
            "name": "Reconnaissance",
            "shortname": "reconnaissance",
            "description": "Gathering information.",
        },
        {
            "id": "TA0001",
            "name": "Initial Access",
            "shortname": "initial-access",
            "description": "Getting in.",
        },
    ],
    "techniques": [
        {
            "id": "T1190",
            "name": "Exploit Public-Facing Application",
            "tactics": ["initial-access"],
            "description": "Exploit a weakness in an internet-facing host.",
            "is_subtechnique": False,
            "parent": None,
            "url": "https://attack.mitre.org/techniques/T1190/",
        },
        {
            "id": "T1595",
            "name": "Active Scanning",
            "tactics": ["reconnaissance"],
            "description": "Probe victim infrastructure.",
            "is_subtechnique": False,
            "parent": None,
            "url": "https://attack.mitre.org/techniques/T1595/",
        },
        {
            "id": "T1595.001",
            "name": "Scanning IP Blocks",
            "tactics": ["reconnaissance"],
            "description": "Scan IP blocks.",
            "is_subtechnique": True,
            "parent": "T1595",
            "url": "https://attack.mitre.org/techniques/T1595/001/",
        },
    ],
}


class TestParseCatalog:
    def test_parses_version_and_counts(self) -> None:
        cat = parse_catalog(_FIXTURE)
        assert cat.version == "17.1"
        assert len(cat.techniques) == 3
        assert len(cat.tactics) == 2

    def test_technique_lookup_by_id(self) -> None:
        cat = parse_catalog(_FIXTURE)
        t = cat.technique("T1190")
        assert t is not None
        assert t.name == "Exploit Public-Facing Application"

    def test_technique_lookup_unknown_returns_none(self) -> None:
        cat = parse_catalog(_FIXTURE)
        assert cat.technique("T9999") is None

    def test_technique_lookup_normalizes_input(self) -> None:
        cat = parse_catalog(_FIXTURE)
        assert cat.technique("t1190") is not None

    def test_tactic_lookup_by_id(self) -> None:
        cat = parse_catalog(_FIXTURE)
        ta = cat.tactic("TA0043")
        assert ta is not None
        assert ta.shortname == "reconnaissance"

    def test_tactic_by_shortname(self) -> None:
        cat = parse_catalog(_FIXTURE)
        ta = cat.tactic_by_shortname("initial-access")
        assert ta is not None
        assert ta.id == "TA0001"

    def test_subtechnique_parent_link(self) -> None:
        cat = parse_catalog(_FIXTURE)
        sub = cat.technique("T1595.001")
        assert sub is not None
        assert sub.is_subtechnique is True
        assert sub.parent == "T1595"

    def test_tactic_ids_for_technique(self) -> None:
        cat = parse_catalog(_FIXTURE)
        # T1190 is in the initial-access tactic → TA0001
        assert cat.tactic_ids_for("T1190") == ["TA0001"]

    def test_tactic_ids_for_unknown_technique(self) -> None:
        cat = parse_catalog(_FIXTURE)
        assert cat.tactic_ids_for("T9999") == []


class TestModels:
    def test_technique_model_defaults(self) -> None:
        t = AttackTechnique(id="T1190", name="Exploit Public-Facing Application")
        assert t.tactics == []
        assert t.is_subtechnique is False
        assert t.parent is None

    def test_tactic_model(self) -> None:
        ta = AttackTactic(id="TA0043", name="Reconnaissance", shortname="reconnaissance")
        assert ta.description == ""


class TestBundledDataset:
    """Smoke tests for the build-time artifact ``data/attack_enterprise.json``."""

    def test_bundled_catalog_loads(self) -> None:
        cat = load_attack_catalog()
        assert cat.version != ""
        # Enterprise ATT&CK has hundreds of techniques and >10 tactics.
        assert len(cat.techniques) > 300
        assert len(cat.tactics) >= 10

    def test_bundled_catalog_has_known_technique(self) -> None:
        cat = load_attack_catalog()
        t = cat.technique("T1190")
        assert t is not None
        assert "initial-access" in t.tactics

    def test_bundled_catalog_subtechniques_have_parents(self) -> None:
        cat = load_attack_catalog()
        subs = [t for t in cat.techniques if t.is_subtechnique]
        assert subs, "expected sub-techniques in the bundled dataset"
        assert all(s.parent and cat.technique(s.parent) for s in subs)


def test_catalog_rejects_duplicate_technique_ids() -> None:
    bad = {
        "version": "1",
        "tactics": [],
        "techniques": [
            {"id": "T1190", "name": "A"},
            {"id": "T1190", "name": "B"},
        ],
    }
    with pytest.raises(ValueError):
        parse_catalog(bad)
