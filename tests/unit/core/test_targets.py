"""Tests for the multi-target ingestion model."""

from __future__ import annotations

import json

import pytest

from decepticon.core.targets import (
    Target,
    TargetKind,
    TargetSet,
    correlate_targets,
    detect_kind,
)

# ── detect_kind ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://github.com/foo/bar", TargetKind.SOURCE),
        ("http://gitlab.com/x/y", TargetKind.SOURCE),
        ("https://www.bitbucket.com/a/b", TargetKind.SOURCE),
        ("./local-repo", TargetKind.SOURCE_PATH),
        ("/abs/repo", TargetKind.SOURCE_PATH),
        ("~/repo", TargetKind.SOURCE_PATH),
        ("file:///opt/app", TargetKind.SOURCE_PATH),
        ("https://app.example.com", TargetKind.LIVE_URL),
        ("http://api.example.com/v1", TargetKind.LIVE_URL),
        ("10.0.0.1", TargetKind.IP_RANGE),
        ("192.168.1.0/24", TargetKind.IP_RANGE),
        ("example.com", TargetKind.HOST),
        ("api.subdomain.example.com", TargetKind.HOST),
    ],
)
def test_detect_kind(value, expected):
    assert detect_kind(value) == expected


@pytest.mark.parametrize("bad", ["", "   ", "::not-a-target"])
def test_detect_kind_rejects_garbage(bad):
    with pytest.raises(ValueError):
        detect_kind(bad)


def test_detect_kind_rejects_non_string():
    with pytest.raises(TypeError):
        detect_kind(123)  # type: ignore[arg-type]


# ── Target.parse ─────────────────────────────────────────────────


def test_target_parse_github_url():
    t = Target.parse("https://github.com/PurpleAILAB/Decepticon")
    assert t.kind is TargetKind.SOURCE
    assert t.id == "github"
    assert t.value == "https://github.com/PurpleAILAB/Decepticon"


def test_target_parse_live_url_id_from_host():
    t = Target.parse("https://api.example.com/v1")
    assert t.kind is TargetKind.LIVE_URL
    assert t.id == "example"


def test_target_parse_explicit_id_overrides():
    t = Target.parse("https://example.com", target_id="prod-web")
    assert t.id == "prod-web"


def test_target_parse_label_defaults_to_value():
    t = Target.parse("https://app.example.com")
    assert t.label == "https://app.example.com"


def test_target_parse_label_explicit():
    t = Target.parse("https://app.example.com", label="Production Web")
    assert t.label == "Production Web"


def test_target_static_dynamic_helpers():
    src = Target.parse("https://github.com/x/y")
    live = Target.parse("https://x.com")
    assert src.is_static and not src.is_dynamic
    assert live.is_dynamic and not live.is_static


def test_target_id_validator_rejects_uppercase():
    with pytest.raises(Exception):
        Target(id="Bad-ID", kind=TargetKind.LIVE_URL, value="https://x")


def test_target_id_validator_rejects_starting_hyphen():
    with pytest.raises(Exception):
        Target(id="-bad", kind=TargetKind.LIVE_URL, value="https://x")


def test_target_id_validator_caps_length():
    with pytest.raises(Exception):
        Target(id="a" * 33, kind=TargetKind.LIVE_URL, value="https://x")


# ── TargetSet semantics ──────────────────────────────────────────


def test_targetset_from_strings_orders_input():
    ts = TargetSet.from_strings(
        [
            "https://github.com/x/y",
            "https://app.example.com",
            "10.0.0.1",
        ]
    )
    assert len(ts) == 3
    kinds = [t.kind for t in ts]
    assert kinds == [TargetKind.SOURCE, TargetKind.LIVE_URL, TargetKind.IP_RANGE]


def test_targetset_get_by_id():
    ts = TargetSet.from_strings(["https://app.example.com", "https://api.example.com"])
    # Both have id "example" → second is auto-suffixed
    assert ts.get("example") is not None
    assert ts.get("example-2") is not None


def test_targetset_static_and_dynamic_partitions():
    ts = TargetSet.from_strings(
        [
            "https://github.com/x/y",
            "./local-src",
            "https://app.example.com",
            "10.0.0.0/24",
        ]
    )
    assert len(ts.static) == 2
    assert len(ts.dynamic) == 2


def test_targetset_dedup_same_id_same_value():
    ts = TargetSet()
    a = ts.add("https://github.com/x/y")
    b = ts.add("https://github.com/x/y")
    assert a is b
    assert len(ts) == 1


def test_targetset_distinct_value_same_id_raises():
    ts = TargetSet()
    ts.add(Target(id="src", kind=TargetKind.SOURCE, value="https://github.com/x/y"))
    with pytest.raises(ValueError, match="already mapped"):
        ts.add(Target(id="src", kind=TargetKind.SOURCE, value="https://github.com/other/repo"))


def test_targetset_contains_works_for_id_and_value():
    ts = TargetSet.from_strings(["https://app.example.com"])
    assert "example" in ts
    assert "https://app.example.com" in ts
    assert "missing" not in ts


def test_targetset_json_roundtrip():
    ts = TargetSet.from_strings(["https://github.com/x/y", "https://app.example.com"])
    blob = ts.to_json()
    restored = TargetSet.from_json(blob)
    assert len(restored) == 2
    assert [t.value for t in restored] == [t.value for t in ts]


def test_targetset_from_json_accepts_dict_envelope():
    payload = json.dumps(
        {
            "targets": [
                {"id": "src", "kind": "source", "value": "https://github.com/x/y"},
                {"id": "web", "kind": "live_url", "value": "https://x.com"},
            ]
        }
    )
    ts = TargetSet.from_json(payload)
    assert [t.id for t in ts] == ["src", "web"]


def test_targetset_from_json_rejects_garbage():
    with pytest.raises(ValueError):
        TargetSet.from_json('"just a string"')


# ── correlate_targets ───────────────────────────────────────────


def test_correlate_returns_unrelated_for_distinct_domains():
    src = Target.parse("https://github.com/foo/bar")
    live = Target.parse("https://example.com")
    out = correlate_targets(src, live)
    assert out["link_kind"] == "unrelated"


def test_correlate_same_host_link():
    src = Target.parse("https://example.com/source")
    live = Target.parse("https://example.com/api")
    out = correlate_targets(src, live)
    assert out["link_kind"] == "same_host"


def test_correlate_subdomain_match():
    src = Target.parse("https://example.com/source")
    live = Target.parse("https://api.example.com")
    out = correlate_targets(src, live)
    assert out["link_kind"] == "same_host"


def test_correlate_same_base_domain():
    src = Target.parse("https://docs.example.com/source")
    live = Target.parse("https://api.example.com")
    out = correlate_targets(src, live)
    assert out["link_kind"] == "same_base_domain"


def test_correlate_optional_finding_value_attached():
    src = Target.parse("https://github.com/x/y")
    live = Target.parse("https://x.com")
    out = correlate_targets(src, live, finding_value="GET /admin")
    assert out["finding_value"] == "GET /admin"
    assert out["static_id"] == src.id
    assert out["dynamic_id"] == live.id


def test_correlate_records_kind_metadata():
    src = Target.parse("https://github.com/x/y")
    live = Target.parse("https://x.com")
    out = correlate_targets(src, live)
    assert out["static_kind"] == "source"
    assert out["dynamic_kind"] == "live_url"


# ── error paths ────────────────────────────────────────────────


def test_target_parse_strips_whitespace():
    t = Target.parse("   https://app.example.com   ")
    assert t.value == "https://app.example.com"


def test_targetset_add_string_uses_parser():
    ts = TargetSet()
    t = ts.add("https://app.example.com")
    assert t.kind is TargetKind.LIVE_URL


def test_targetset_iteration_returns_targets():
    ts = TargetSet.from_strings(["https://x.com", "https://y.com"])
    seen = list(ts)
    assert all(isinstance(t, Target) for t in seen)
    assert len(seen) == 2
