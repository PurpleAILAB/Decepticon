"""ScopeEntry.type is normalized to a canonical asset-type id, leniently."""

from __future__ import annotations

from decepticon_core.types.engagement import ScopeEntry


def test_known_type_is_canonicalized():
    assert ScopeEntry(target="*.acme.com", type="ip-range").type == "cidr"
    assert ScopeEntry(target="x", type="GraphQL Endpoint").type == "graphql-endpoint"


def test_unknown_type_is_preserved():
    e = ScopeEntry(target="HQ Building", type="cloud-resource")
    assert e.type == "cloud-resource"


def test_canonical_id_passthrough():
    assert ScopeEntry(target="acme.com", type="domain").type == "domain"
