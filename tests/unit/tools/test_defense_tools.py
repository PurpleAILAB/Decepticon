"""Unit tests for decepticon.tools.defense.tools @tool functions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    DefenseBrief,
)
from decepticon.tools.defense import tools as defense_tools
from decepticon.tools.defense.tools import (
    defense_execute_action,
    defense_generate_brief,
    defense_read_brief,
    defense_verify_status,
    set_defense_backend,
)

# ── defense_read_brief ────────────────────────────────────────────────────────


def test_defense_read_brief_exists(tmp_path: Path) -> None:
    brief = DefenseBrief(
        finding_ref="FIND-001",
        finding_title="Test Finding",
        severity="high",
        attack_vector="Unauthenticated RCE via tcp/8080",
        affected_assets=["10.0.0.1"],
    )
    (tmp_path / "defense-brief.json").write_text(brief.model_dump_json(), encoding="utf-8")

    result_str = defense_read_brief.invoke({"workspace_path": str(tmp_path)})
    result = json.loads(result_str)

    assert result["finding_ref"] == "FIND-001"
    assert result["finding_title"] == "Test Finding"
    assert result["severity"] == "high"
    assert result["affected_assets"] == ["10.0.0.1"]


def test_defense_read_brief_missing(tmp_path: Path) -> None:
    result_str = defense_read_brief.invoke({"workspace_path": str(tmp_path)})
    result = json.loads(result_str)

    assert "error" in result
    assert "defense-brief.json" in result["error"]


# ── defense_execute_action ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_defense_execute_action_success() -> None:
    mock_backend = MagicMock()
    expected_result = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/8080",
        success=True,
        message="Port blocked",
        rollback_command="iptables -D INPUT -p tcp --dport 8080 -j DROP",
    )
    mock_backend.execute_action = AsyncMock(return_value=expected_result)

    set_defense_backend(mock_backend)

    result_str = await defense_execute_action.ainvoke(
        {
            "action_type": "block_port",
            "target": "tcp/8080",
            "parameters": "{}",
        }
    )

    result = json.loads(result_str)
    assert result["success"] is True
    assert result["target"] == "tcp/8080"
    assert result["action_type"] == "block_port"

    # Cleanup
    set_defense_backend(None)


@pytest.mark.asyncio
async def test_defense_execute_action_no_backend() -> None:
    set_defense_backend(None)

    result_str = await defense_execute_action.ainvoke(
        {
            "action_type": "block_port",
            "target": "tcp/8080",
        }
    )
    result = json.loads(result_str)
    assert "error" in result
    assert "not initialized" in result["error"]


# ── defense_log_action ────────────────────────────────────────────────────────


def test_defense_log_action() -> None:
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # run() returns a record-like object; single() returns a dict-like with ["cnt"]
    mock_record = MagicMock()
    mock_record.__getitem__ = MagicMock(side_effect=lambda k: 1)
    mock_session.run.return_value.single.return_value = mock_record

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    mock_store = MagicMock()
    mock_store._driver = mock_driver
    mock_store._database = "neo4j"

    with patch.object(defense_tools, "_get_neo4j", return_value=mock_store):
        from decepticon.tools.defense.tools import defense_log_action

        result_str = defense_log_action.invoke(
            {
                "action_type": "block_port",
                "target": "tcp/22",
                "success": True,
                "finding_ref": "FIND-001",
                "message": "Port blocked",
            }
        )

    result = json.loads(result_str)
    assert result["status"] == "logged"
    assert "FIND-001" in result["node_key"]
    assert "block_port" in result["node_key"]
    # Verify Cypher was executed (MERGE + 3 relationship queries)
    assert mock_session.run.call_count >= 1


# ── defense_verify_status ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_defense_verify_status() -> None:
    mock_backend = MagicMock()
    mock_backend.verify_action = AsyncMock(return_value=True)

    set_defense_backend(mock_backend)

    result_str = await defense_verify_status.ainvoke(
        {
            "action_type": "block_port",
            "target": "tcp/8080",
        }
    )

    result = json.loads(result_str)
    assert result["active"] is True

    set_defense_backend(None)


# ── defense_generate_brief ────────────────────────────────────────────────────


def test_defense_generate_brief(tmp_path: Path) -> None:
    findings_dir = tmp_path / "findings"
    findings_dir.mkdir()

    finding_md = findings_dir / "FIND-001.md"
    finding_md.write_text(
        "# Exposed SSH Service\n\n"
        "**Severity**: high\n\n"
        "**Attack Vector**: SSH brute-force over open port tcp/22\n\n"
        "**Affected**: 10.0.0.1, 10.0.0.2\n\n"
        "## Evidence\n\nNmap scan confirmed port 22 open and accepting connections.\n",
        encoding="utf-8",
    )

    result_str = defense_generate_brief.invoke(
        {
            "finding_ref": "FIND-001",
            "workspace_path": str(tmp_path),
        }
    )

    result = json.loads(result_str)
    assert result["finding_ref"] == "FIND-001"
    assert "SSH" in result["finding_title"] or result["finding_title"] == "Exposed SSH Service"
    assert result["severity"] == "high"

    # Verify brief was written to disk
    brief_path = tmp_path / "defense-brief.json"
    assert brief_path.exists()
    on_disk = json.loads(brief_path.read_text())
    assert on_disk["finding_ref"] == "FIND-001"


def test_defense_generate_brief_missing_finding(tmp_path: Path) -> None:
    result_str = defense_generate_brief.invoke(
        {
            "finding_ref": "FIND-999",
            "workspace_path": str(tmp_path),
        }
    )
    result = json.loads(result_str)
    assert "error" in result
    assert "FIND-999" in result["error"]
