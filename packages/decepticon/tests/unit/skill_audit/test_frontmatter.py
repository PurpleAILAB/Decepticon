"""Tests for SKILL.md frontmatter parsing."""

from __future__ import annotations

import pytest

from decepticon.skill_audit.frontmatter import (
    FrontmatterParseError,
    parse_frontmatter,
)


def test_parses_minimal_valid_frontmatter() -> None:
    text = (
        "---\n"
        "name: web-recon\n"
        "description: short summary\n"
        "metadata:\n"
        "  subdomain: reconnaissance\n"
        "  when_to_use: web recon\n"
        "---\n"
        "Body content here.\n"
    )
    meta, body = parse_frontmatter(text)
    assert meta["name"] == "web-recon"
    assert meta["description"] == "short summary"
    assert meta["metadata"]["subdomain"] == "reconnaissance"
    assert meta["metadata"]["when_to_use"] == "web recon"
    assert body == "Body content here.\n"


def test_handles_list_valued_mitre_field() -> None:
    text = (
        "---\n"
        "name: example\n"
        "description: x\n"
        "metadata:\n"
        "  subdomain: reconnaissance\n"
        "  when_to_use: x\n"
        "  mitre_attack:\n"
        "    - T1190\n"
        "    - T1595.001\n"
        "---\n"
        "body\n"
    )
    meta, _body = parse_frontmatter(text)
    assert meta["metadata"]["mitre_attack"] == ["T1190", "T1595.001"]


def test_handles_comma_separated_mitre_field() -> None:
    # Real corpus has many files where mitre_attack is a CSV string.
    text = (
        "---\n"
        "name: example\n"
        "description: x\n"
        "metadata:\n"
        "  subdomain: reconnaissance\n"
        "  when_to_use: x\n"
        "  mitre_attack: T1190, T1595.001\n"
        "---\n"
        "body\n"
    )
    meta, _body = parse_frontmatter(text)
    assert meta["metadata"]["mitre_attack"] == "T1190, T1595.001"


def test_raises_when_frontmatter_block_is_missing() -> None:
    text = "# A SKILL.md without frontmatter\nbody\n"
    with pytest.raises(FrontmatterParseError, match="no YAML frontmatter"):
        parse_frontmatter(text)


def test_raises_when_yaml_is_malformed() -> None:
    text = "---\nname: ok\n  bad:indent: oh\n---\nbody\n"
    with pytest.raises(FrontmatterParseError, match="YAML"):
        parse_frontmatter(text)


def test_returns_empty_body_when_only_frontmatter_present() -> None:
    text = (
        "---\n"
        "name: x\n"
        "description: x\n"
        "metadata:\n"
        "  subdomain: reconnaissance\n"
        "  when_to_use: x\n"
        "---\n"
    )
    _meta, body = parse_frontmatter(text)
    assert body == ""
