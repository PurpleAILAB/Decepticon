"""Tests for the defender agent factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _mock_config():
    """Patch load_config so create_defender_agent() doesn't need a real config."""
    mock_cfg = MagicMock()
    mock_cfg.docker.sandbox_container_name = "test-sandbox"

    with patch("decepticon.agents.defender.load_config", return_value=mock_cfg):
        yield mock_cfg


@pytest.fixture
def _mock_llm_factory():
    """Patch LLMFactory so no real LLM client is created."""
    mock_factory = MagicMock()
    mock_factory.get_model.return_value = MagicMock()
    mock_factory.get_fallback_models.return_value = []

    with patch("decepticon.agents.defender.LLMFactory", return_value=mock_factory):
        yield mock_factory


@pytest.fixture(autouse=True)
def _mock_summarization():
    """Patch create_summarization_middleware so it doesn't validate the LLM type."""
    with patch(
        "decepticon.agents.defender.create_summarization_middleware",
        return_value=MagicMock(),
    ):
        yield


@pytest.fixture
def _mock_create_agent():
    """Patch create_agent to return a mock runnable."""
    mock_agent = MagicMock()
    mock_agent.with_config.return_value = mock_agent

    with patch("decepticon.agents.defender.create_agent", return_value=mock_agent) as m:
        yield m


def test_create_defender_agent_returns_agent(_mock_config, _mock_llm_factory, _mock_create_agent):
    """create_defender_agent() returns a runnable agent graph."""
    from decepticon.agents.defender import create_defender_agent

    agent = create_defender_agent()
    assert agent is not None
    _mock_create_agent.assert_called_once()


def test_create_defender_agent_has_defense_tools(
    _mock_config, _mock_llm_factory, _mock_create_agent
):
    """Defender agent includes all required defense tools."""
    from decepticon.agents.defender import create_defender_agent

    create_defender_agent()

    call_kwargs = _mock_create_agent.call_args
    tools = call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools", [])

    tool_names = {getattr(t, "name", str(t)) for t in tools}

    # Must have defense tools
    assert "defense_read_brief" in tool_names
    assert "defense_execute_action" in tool_names
    assert "defense_log_action" in tool_names
    assert "defense_verify_status" in tool_names

    # Must have KG query tools
    assert "kg_query" in tool_names
    assert "kg_neighbors" in tool_names

    # Must have bash
    assert "bash" in tool_names


def test_create_defender_agent_middleware_stack(
    _mock_config, _mock_llm_factory, _mock_create_agent
):
    """Defender agent has the correct middleware stack."""
    from decepticon.agents.defender import create_defender_agent

    create_defender_agent()

    call_kwargs = _mock_create_agent.call_args
    middleware = call_kwargs.kwargs.get("middleware") or call_kwargs[1].get("middleware", [])

    # Should have at least 5 middleware components
    assert len(middleware) >= 5


def test_create_defender_agent_name(_mock_config, _mock_llm_factory, _mock_create_agent):
    """Defender agent is named 'defender'."""
    from decepticon.agents.defender import create_defender_agent

    create_defender_agent()

    call_kwargs = _mock_create_agent.call_args
    name = call_kwargs.kwargs.get("name") or call_kwargs[1].get("name")
    assert name == "defender"
