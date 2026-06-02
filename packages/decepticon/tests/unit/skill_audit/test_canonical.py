"""Tests for the canonical subdomain loader."""

from __future__ import annotations

from decepticon.skill_audit.canonical import (
    SUBDOMAIN_LIST_PATH,
    load_canonical_subdomains,
)


def test_subdomain_list_path_points_at_packaged_yaml() -> None:
    assert SUBDOMAIN_LIST_PATH.name == "subdomains.yaml"
    assert SUBDOMAIN_LIST_PATH.exists(), f"canonical YAML missing at {SUBDOMAIN_LIST_PATH}"


def test_load_canonical_subdomains_returns_frozenset_of_strings() -> None:
    subdomains = load_canonical_subdomains()
    assert isinstance(subdomains, frozenset)
    assert all(isinstance(s, str) for s in subdomains)
    assert subdomains, "canonical list must not be empty"


def test_canonical_list_contains_known_phases() -> None:
    subdomains = load_canonical_subdomains()
    # Sanity check: a handful of phases we know must be canonical.
    for must_be_present in ("reconnaissance", "execution", "ai-security"):
        assert must_be_present in subdomains, f"{must_be_present!r} missing from canonical list"


def test_canonical_list_excludes_known_aliases() -> None:
    subdomains = load_canonical_subdomains()
    # Aliases must be resolved out of the canonical list to force authors
    # to write the canonical form.
    for must_not_be_present in ("reverser", "contracts", "cloud-native"):
        assert must_not_be_present not in subdomains, (
            f"{must_not_be_present!r} should be an alias, not canonical"
        )
