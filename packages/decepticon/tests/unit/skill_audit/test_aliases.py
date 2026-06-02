"""Tests for subdomain alias resolution."""

from __future__ import annotations

import pytest

from decepticon.skill_audit.aliases import (
    SUBDOMAIN_ALIASES,
    resolve_subdomain,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("reverser", "reverse-engineering"),
        ("re", "reverse-engineering"),
        ("contracts", "smart-contracts"),
        ("cloud-native", "cloud"),
        ("ad", "active-directory"),
        # Already canonical: returned unchanged.
        ("reconnaissance", "reconnaissance"),
        ("ai-security", "ai-security"),
    ],
)
def test_resolve_subdomain_returns_canonical_form(raw: str, expected: str) -> None:
    assert resolve_subdomain(raw) == expected


def test_resolve_subdomain_passes_through_unknown_values() -> None:
    # Unknown subdomains are returned as-is; the validator decides whether
    # to reject them by consulting the canonical list separately.
    assert resolve_subdomain("totally-unknown") == "totally-unknown"


def test_resolve_subdomain_is_case_insensitive() -> None:
    assert resolve_subdomain("Reverser") == "reverse-engineering"
    assert resolve_subdomain("CONTRACTS") == "smart-contracts"


def test_alias_map_is_exposed_and_well_formed() -> None:
    assert isinstance(SUBDOMAIN_ALIASES, dict)
    # No canonical form should appear as a key in the alias map (a
    # canonical → canonical entry would be a no-op + footgun).
    canonical_values = set(SUBDOMAIN_ALIASES.values())
    aliases = set(SUBDOMAIN_ALIASES.keys())
    overlap = canonical_values & aliases
    assert not overlap, f"alias map has canonical values used as keys: {overlap}"
