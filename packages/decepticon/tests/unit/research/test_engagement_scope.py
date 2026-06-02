"""Tests for the per-engagement scoping context-var + Neo4j auto-tagging."""

from __future__ import annotations

import pytest

from decepticon.tools.research import _engagement_scope as _scope
from decepticon.tools.research._engagement_scope import (
    get_active_engagement,
    is_valid_engagement_label,
    reset_active_engagement,
    set_active_engagement,
    with_engagement_property,
)


@pytest.fixture(autouse=True)
def _reset_engagement_scope_context():
    """Isolate the engagement contextvar between tests.

    ``EngagementContextMiddleware.before_agent`` (exercised by middleware
    tests in the same pytest session) sets the contextvar and never
    resets it - that's correct production behavior because the
    engagement should persist for the agent's whole run. For unit
    tests we need fresh state every time, so we push None on entry and
    pop on exit via the standard Token.reset() pattern.
    """
    token = _scope._active_engagement.set(None)
    try:
        yield
    finally:
        _scope._active_engagement.reset(token)


class TestEngagementLabelValidation:
    @pytest.mark.parametrize(
        "label",
        ["acme-q2", "ENG_001", "client.test.42", "a", "A1", "X-Y_Z.123"],
    )
    def test_valid_labels_accepted(self, label: str) -> None:
        assert is_valid_engagement_label(label)

    @pytest.mark.parametrize(
        "label",
        [
            "",
            "-leading-dash",
            ".leading-dot",
            "_leading-underscore",
            "has space",
            "has/slash",
            "has\\backslash",
            "has\u200binvisible",
            "has;semicolon",
            "has'quote",
            "has`backtick",
            "has(paren",
            "x" * 129,
        ],
    )
    def test_invalid_labels_rejected(self, label: str) -> None:
        assert not is_valid_engagement_label(label)


class TestActiveEngagement:
    def test_default_is_none(self) -> None:
        assert get_active_engagement() is None

    def test_set_and_get(self) -> None:
        token = set_active_engagement("acme-q2")
        try:
            assert get_active_engagement() == "acme-q2"
        finally:
            reset_active_engagement(token)
        assert get_active_engagement() is None

    def test_reset_restores_prior(self) -> None:
        token1 = set_active_engagement("first")
        try:
            token2 = set_active_engagement("second")
            assert get_active_engagement() == "second"
            reset_active_engagement(token2)
            assert get_active_engagement() == "first"
        finally:
            reset_active_engagement(token1)

    def test_invalid_label_raises(self) -> None:
        with pytest.raises(ValueError):
            set_active_engagement("has space")

    def test_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_ENGAGEMENT", "from-env")
        assert get_active_engagement() == "from-env"

    def test_env_fallback_ignored_when_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_ENGAGEMENT", "has space")
        assert get_active_engagement() is None

    def test_contextvar_precedes_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_ENGAGEMENT", "from-env")
        token = set_active_engagement("from-contextvar")
        try:
            assert get_active_engagement() == "from-contextvar"
        finally:
            reset_active_engagement(token)


class TestWithEngagementProperty:
    def test_active_engagement_used(self) -> None:
        token = set_active_engagement("acme-q2")
        try:
            out = with_engagement_property({"ip": "10.0.0.5"})
            assert out["engagement"] == "acme-q2"
            assert out["ip"] == "10.0.0.5"
        finally:
            reset_active_engagement(token)

    def test_override_takes_precedence(self) -> None:
        token = set_active_engagement("acme-q2")
        try:
            out = with_engagement_property({"x": 1}, override="historical-import")
            assert out["engagement"] == "historical-import"
        finally:
            reset_active_engagement(token)

    def test_legacy_when_no_engagement_set(self) -> None:
        out = with_engagement_property({"x": 1})
        assert out["engagement"] == "_legacy"

    def test_none_props_safe(self) -> None:
        out = with_engagement_property(None)
        assert out["engagement"] == "_legacy"
        assert out == {"engagement": "_legacy"}

    def test_input_dict_not_mutated(self) -> None:
        original = {"ip": "10.0.0.5"}
        out = with_engagement_property(original)
        assert "engagement" not in original
        assert out is not original

    def test_existing_engagement_preserved_over_active(self) -> None:
        token = set_active_engagement("engagement-b")
        try:
            out = with_engagement_property({"engagement": "engagement-a", "ip": "10.0.0.9"})
            assert out["engagement"] == "engagement-a"
        finally:
            reset_active_engagement(token)

    def test_existing_engagement_preserved_when_no_active(self) -> None:
        out = with_engagement_property({"engagement": "engagement-a"})
        assert out["engagement"] == "engagement-a"

    def test_override_beats_existing_engagement(self) -> None:
        out = with_engagement_property({"engagement": "engagement-a"}, override="engagement-c")
        assert out["engagement"] == "engagement-c"


class TestNeo4jUpsertCypherShape:
    def test_upsert_node_cypher_sets_engagement(self) -> None:
        """The upsert template sets n.engagement = $engagement on every write."""
        from pathlib import Path

        source = (
            Path(
                __file__,
            ).parent.parent.parent.parent
            / "decepticon"
            / "tools"
            / "research"
            / "neo4j_store.py"
        )
        text = source.read_text(encoding="utf-8")
        assert "n.engagement = $engagement" in text, (
            "upsert_node Cypher template must set n.engagement = $engagement"
        )
        assert "r.engagement = $engagement" in text, (
            "upsert_edge Cypher template must set r.engagement = $engagement"
        )
        assert "n.engagement = row.engagement" in text, (
            "batch_upsert_nodes Cypher must set n.engagement = row.engagement"
        )
        assert "r.engagement = row.engagement" in text, (
            "batch_upsert_edges Cypher must set r.engagement = row.engagement"
        )

    def test_upsert_node_python_calls_with_engagement_property(self) -> None:
        """The upsert path must wrap props in with_engagement_property()."""
        from pathlib import Path

        source = (
            Path(
                __file__,
            ).parent.parent.parent.parent
            / "decepticon"
            / "tools"
            / "research"
            / "neo4j_store.py"
        )
        text = source.read_text(encoding="utf-8")
        assert text.count("with_engagement_property(") >= 4, (
            "every upsert path (single+batch, node+edge) must call with_engagement_property()"
        )
