"""DECEPTICON_ASSET_ROUTING gates an Asset Coverage Brief into the prompt."""

from __future__ import annotations

import json

from decepticon.middleware.engagement import (
    _asset_routing_active,
    _build_asset_coverage_injection,
    _load_roe_scope,
)


def _write_roe(tmp_path, entries):
    plan = tmp_path / "plan"
    plan.mkdir()
    (plan / "roe.json").write_text(json.dumps({"in_scope": entries}), encoding="utf-8")
    return str(tmp_path)


def test_load_roe_scope(tmp_path):
    ws = _write_roe(
        tmp_path,
        [
            {"target": "*.acme.com", "type": "wildcard"},
            {"target": "api.acme.com", "type": "graphql-endpoint"},
        ],
    )
    scope = _load_roe_scope(ws)
    assert scope == [("*.acme.com", "wildcard"), ("api.acme.com", "graphql-endpoint")]


def test_load_roe_scope_missing(tmp_path):
    assert _load_roe_scope(str(tmp_path)) == []


def test_brief_names_agents_and_tags():
    brief = _build_asset_coverage_injection(
        [("api.acme.com", "graphql-endpoint"), ("device", "ics-scada")]
    )
    assert "Asset Coverage Brief" in brief
    assert "graphql-endpoint" in brief
    assert "asset:graphql-endpoint" in brief
    assert "exploit" in brief
    assert "SAFETY-CRITICAL" in brief
    assert "ics-scada" in brief


def test_brief_empty_when_no_scope():
    assert _build_asset_coverage_injection([]) == ""


def test_asset_routing_flag_gate(monkeypatch):
    monkeypatch.delenv("DECEPTICON_ASSET_ROUTING", raising=False)
    assert _asset_routing_active() is False
    for falsy in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("DECEPTICON_ASSET_ROUTING", falsy)
        assert _asset_routing_active() is False
    for truthy in ("1", "true", "yes", "on", "anything-else"):
        monkeypatch.setenv("DECEPTICON_ASSET_ROUTING", truthy)
        assert _asset_routing_active() is True
