from __future__ import annotations

import pytest

from decepticon_core.types import asset_types as at


def test_exactly_75_entries():
    assert len(at.all()) == 75


def test_numbers_are_1_to_75_unique():
    numbers = sorted(a.number for a in at.all())
    assert numbers == list(range(1, 76))


def test_ids_unique_and_kebab():
    ids = [a.id for a in at.all()]
    assert len(ids) == len(set(ids)), "duplicate id"
    for i in ids:
        assert i == i.lower(), i
        assert " " not in i and "_" not in i, i


def test_every_field_is_valid():
    for a in at.all():
        assert a.category in at.CATEGORIES, a.id
        assert a.coverage in at.VALID_COVERAGE, a.id
        assert a.roe_kind in at.VALID_ROE_KINDS, a.id
        for role in a.agents:
            assert role in at.VALID_AGENT_ROLES, (a.id, role)


def test_lookups():
    gql = at.get("graphql-endpoint")
    assert gql is not None and gql.number == 24
    ics = at.by_number(63)
    assert ics is not None and ics.id == "ics-scada"
    assert at.get("nonexistent") is None
    assert {a.id for a in at.by_category("web3")} >= {"defi-dapp", "bridge"}


def test_safety_flags():
    assert at.get("ics-scada").safety_critical is True
    assert at.get("satellite-rf").safety_critical is True
    assert at.get("physical-facility").gated_by_conops == "physical_engagement"


def test_skill_tag_property():
    assert at.get("graphql-endpoint").skill_tag == "asset:graphql-endpoint"


@pytest.mark.parametrize(
    "raw, expected_id",
    [
        ("domain", "domain"),
        ("ip-range", "cidr"),  # legacy alias
        ("physical", None),
        ("GraphQL Endpoint", "graphql-endpoint"),
        ("apk", "android-apk"),
        ("totally-made-up", None),
        ("", None),
    ],
)
def test_normalize_type(raw, expected_id):
    assert at.normalize_type(raw) == expected_id


@pytest.mark.parametrize(
    "target, expected_id",
    [
        ("10.0.0.0/24", "cidr"),
        ("192.168.1.5", "ip-address"),
        ("*.acme.com", "wildcard"),
        ("wss://api.acme.com/socket", "websocket"),
        ("0x" + "a" * 40, "smart-contract"),
        ("AS15169", "asn"),
        ("payload.apk", "android-apk"),
        ("app.ipa", "ios-ipa"),
        ("https://apps.apple.com/app/id123", "ios-appstore"),
        ("https://play.google.com/store/apps/details?id=x", "android-playstore"),
        ("acme.com", "domain"),
        ("https://acme.com/login", "url"),
        ("something weird", "other-asset"),
    ],
)
def test_classify(target, expected_id):
    result = at.classify(target)
    assert result is not None and result.id == expected_id


def test_classify_hint_wins():
    assert at.classify("anything", hint="k8s-cluster").id == "k8s-cluster"


def test_classify_invalid_hint_falls_through():
    assert at.classify("acme.com", hint="made-up-type").id == "domain"


def test_aliases_unique():
    seen: set[str] = set()
    for a in at.all():
        for alias in a.aliases:
            assert alias.lower() not in seen, alias
            seen.add(alias.lower())


def test_coverage_summary_counts():
    assert at.coverage_summary() == {"covered": 34, "partial": 26, "gap": 15}
