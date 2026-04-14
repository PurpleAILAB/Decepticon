"""Unit tests for DockerDefenseBackend — all subprocess.run calls are mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from decepticon.backends.defense import DockerDefenseBackend
from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    DefenseRecommendation,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_action(
    action_type: DefenseActionType,
    target: str,
    parameters: dict[str, str] | None = None,
) -> DefenseRecommendation:
    return DefenseRecommendation(
        action_type=action_type,
        target=target,
        parameters=parameters or {},
        rationale="test",
    )


def _mock_run(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a mock subprocess.CompletedProcess with the given values."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ── block_port ─────────────────────────────────────────────────────────────────


async def test_block_port_success() -> None:
    backend = DockerDefenseBackend("test-container")
    action = _make_action(DefenseActionType.BLOCK_PORT, "tcp/8080")

    with patch("subprocess.run", return_value=_mock_run(0)) as mock_run:
        result = await backend.execute_action(action)

    assert result.success is True
    assert result.action_type == DefenseActionType.BLOCK_PORT
    assert result.target == "tcp/8080"
    assert result.rollback_command is not None
    assert "iptables -D INPUT" in result.rollback_command

    # Verify the iptables command was formed correctly
    called_cmd = mock_run.call_args[0][0]
    full_cmd = " ".join(called_cmd)
    assert "iptables" in full_cmd
    assert "8080" in full_cmd


async def test_block_port_failure() -> None:
    backend = DockerDefenseBackend("test-container")
    action = _make_action(DefenseActionType.BLOCK_PORT, "tcp/443")

    with patch("subprocess.run", return_value=_mock_run(1, stderr="iptables: permission denied")):
        result = await backend.execute_action(action)

    assert result.success is False
    assert result.rollback_command is None
    # Failed actions are not tracked
    assert await backend.list_applied_actions() == []


# ── add_firewall_rule ─────────────────────────────────────────────────────────


async def test_add_firewall_rule() -> None:
    backend = DockerDefenseBackend("test-container")
    rule = "-A INPUT -s 10.0.0.5 -j DROP"
    action = _make_action(DefenseActionType.ADD_FIREWALL_RULE, "network", {"rule": rule})

    with patch("subprocess.run", return_value=_mock_run(0)) as mock_run:
        result = await backend.execute_action(action)

    assert result.success is True
    assert result.rollback_command is not None
    assert "iptables -D" in result.rollback_command

    called_cmd = mock_run.call_args[0][0]
    assert "iptables" in " ".join(called_cmd)
    assert "-A INPUT" in " ".join(called_cmd)


# ── disable_service ───────────────────────────────────────────────────────────


async def test_disable_service() -> None:
    backend = DockerDefenseBackend("test-container")
    action = _make_action(DefenseActionType.DISABLE_SERVICE, "sshd")

    with patch("subprocess.run", return_value=_mock_run(0)) as mock_run:
        result = await backend.execute_action(action)

    assert result.success is True
    assert result.rollback_command is not None
    assert "systemctl enable" in result.rollback_command
    assert "systemctl start" in result.rollback_command

    # Verify systemctl stop && systemctl disable was issued
    called_cmd = mock_run.call_args[0][0]
    full_cmd = " ".join(called_cmd)
    assert "systemctl stop sshd" in full_cmd
    assert "systemctl disable sshd" in full_cmd


# ── verify_action ─────────────────────────────────────────────────────────────


async def test_verify_action_port_active() -> None:
    backend = DockerDefenseBackend("test-container")
    result = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/8080",
        success=True,
        message="Port blocked",
    )

    with patch("subprocess.run", return_value=_mock_run(0)):
        active = await backend.verify_action(result)

    assert active is True


async def test_verify_action_port_inactive() -> None:
    backend = DockerDefenseBackend("test-container")
    result = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/8080",
        success=True,
        message="Port blocked",
    )

    with patch("subprocess.run", return_value=_mock_run(1)):
        active = await backend.verify_action(result)

    assert active is False


# ── rollback_port_block ───────────────────────────────────────────────────────


async def test_rollback_port_block() -> None:
    backend = DockerDefenseBackend("test-container")
    applied = DefenseActionResult(
        action_type=DefenseActionType.BLOCK_PORT,
        target="tcp/9090",
        success=True,
        message="Port blocked",
        rollback_command="iptables -D INPUT -p tcp --dport 9090 -j DROP",
    )

    with patch("subprocess.run", return_value=_mock_run(0)) as mock_run:
        rollback_result = await backend.rollback_action(applied)

    assert rollback_result.success is True
    called_cmd = mock_run.call_args[0][0]
    assert "iptables -D" in " ".join(called_cmd)


# ── list_applied_actions ──────────────────────────────────────────────────────


async def test_list_applied_actions() -> None:
    backend = DockerDefenseBackend("test-container")
    action1 = _make_action(DefenseActionType.BLOCK_PORT, "tcp/80")
    action2 = _make_action(DefenseActionType.BLOCK_PORT, "tcp/443")

    with patch("subprocess.run", return_value=_mock_run(0)):
        await backend.execute_action(action1)
        await backend.execute_action(action2)

    applied = await backend.list_applied_actions()
    assert len(applied) == 2
    targets = {r.target for r in applied}
    assert "tcp/80" in targets
    assert "tcp/443" in targets
