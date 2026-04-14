"""Defense backend abstraction and Docker implementation.

Provides an abstract interface for executing defensive actions on target
environments, and a concrete Docker implementation that runs commands via
`docker exec` inside a named container.

Architecture:
    AbstractDefenseBackend   — protocol all backends must implement
    DockerDefenseBackend     — executes iptables/systemctl/pkill via docker exec
"""

from __future__ import annotations

import asyncio
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from decepticon.core.logging import get_logger
from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    DefenseRecommendation,
)

log = get_logger("backends.defense")


# ─── Abstract base ────────────────────────────────────────────────────────────


class AbstractDefenseBackend(ABC):
    """Protocol all defense backends must implement.

    A defense backend is responsible for applying, rolling back, and verifying
    discrete defensive actions on a target environment. It is the counterpart
    to BaseSandbox on the offensive side.
    """

    @abstractmethod
    async def execute_action(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Execute a single defensive action on the target.

        Args:
            action: The recommendation from the offensive agent to apply.

        Returns:
            A DefenseActionResult describing success/failure and any rollback command.
        """
        ...

    @abstractmethod
    async def rollback_action(self, result: DefenseActionResult) -> DefenseActionResult:
        """Undo a previously applied defensive action.

        Args:
            result: The result from a prior execute_action() call. Must contain
                    a non-None rollback_command to be reversible.

        Returns:
            A new DefenseActionResult describing the rollback outcome.
        """
        ...

    @abstractmethod
    async def verify_action(self, result: DefenseActionResult) -> bool:
        """Check whether a defensive action is still active on the target.

        Args:
            result: The result from a prior execute_action() call.

        Returns:
            True if the defense is still in place, False if it has been removed
            or was never successfully applied.
        """
        ...

    @abstractmethod
    async def list_applied_actions(self) -> list[DefenseActionResult]:
        """Return all defensive actions currently tracked as applied.

        Returns:
            Ordered list of DefenseActionResult objects, oldest first.
        """
        ...


# ─── Docker implementation ────────────────────────────────────────────────────


class DockerDefenseBackend(AbstractDefenseBackend):
    """Defense backend that executes actions inside a Docker container.

    All shell commands are run via `docker exec <container_name> sh -c <cmd>`
    and offloaded to a thread pool via asyncio.to_thread() to avoid blocking
    the event loop.

    Applied actions are tracked in-process in `_applied`. This list is NOT
    persisted across process restarts — callers that need durability should
    serialize the list themselves.

    Args:
        container_name: Name or ID of the TARGET container (not the Kali
                        recon sandbox). Defensive commands are applied here.
        timeout: Maximum seconds to wait for any single shell command.
    """

    def __init__(self, container_name: str, timeout: int = 30) -> None:
        self._container = container_name
        self._timeout = timeout
        self._applied: list[DefenseActionResult] = []

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _run(self, cmd: str) -> tuple[int, str]:
        """Execute a shell command inside the container synchronously.

        Returns:
            (returncode, combined stdout+stderr output)
        """
        try:
            result = subprocess.run(
                ["docker", "exec", self._container, "sh", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout
            if result.stderr and result.stderr.strip():
                output += result.stderr
            return result.returncode, output.strip()
        except subprocess.TimeoutExpired:
            return 124, f"Command timed out after {self._timeout}s"
        except Exception as exc:
            return 1, str(exc)

    async def _exec(self, cmd: str) -> tuple[int, str]:
        """Async wrapper around _run() — non-blocking via asyncio.to_thread()."""
        return await asyncio.to_thread(self._run, cmd)

    def _make_result(
        self,
        action: DefenseRecommendation,
        *,
        success: bool,
        message: str,
        rollback_command: str | None,
    ) -> DefenseActionResult:
        return DefenseActionResult(
            action_type=action.action_type,
            target=action.target,
            success=success,
            message=message,
            rollback_command=rollback_command,
            executed_at=datetime.now(timezone.utc),
        )

    # ── Action dispatch ───────────────────────────────────────────────────────

    async def execute_action(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Dispatch to the correct handler based on action_type."""
        log.info(
            "Executing defense action type=%s target=%s container=%s",
            action.action_type,
            action.target,
            self._container,
        )

        handlers = {
            DefenseActionType.BLOCK_PORT: self._block_port,
            DefenseActionType.ADD_FIREWALL_RULE: self._add_firewall_rule,
            DefenseActionType.DISABLE_SERVICE: self._disable_service,
            DefenseActionType.RESTART_SERVICE: self._restart_service,
            DefenseActionType.KILL_PROCESS: self._kill_process,
            DefenseActionType.UPDATE_CONFIG: self._update_config,
            DefenseActionType.REVOKE_CREDENTIAL: self._revoke_credential,
        }

        handler = handlers.get(action.action_type)
        if handler is None:
            result = self._make_result(
                action,
                success=False,
                message=f"Unsupported action type: {action.action_type}",
                rollback_command=None,
            )
        else:
            result = await handler(action)

        if result.success:
            self._applied.append(result)

        log.info(
            "Defense action %s: success=%s target=%s",
            action.action_type,
            result.success,
            action.target,
        )
        return result

    # ── Action handlers ───────────────────────────────────────────────────────

    async def _block_port(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Block inbound TCP traffic on a port using iptables.

        target: port notation, e.g. 'tcp/8080' or '8080'
        """
        # Normalise target — accept 'tcp/8080', 'udp/53', or bare '8080'
        parts = action.target.split("/")
        if len(parts) == 2:
            proto, port = parts[0].lower(), parts[1]
        else:
            proto, port = "tcp", parts[0]

        apply_cmd = f"iptables -A INPUT -p {proto} --dport {port} -j DROP"
        rollback_cmd = f"iptables -D INPUT -p {proto} --dport {port} -j DROP"

        rc, output = await self._exec(apply_cmd)
        success = rc == 0
        message = (
            output if output else ("Port blocked successfully" if success else "iptables failed")
        )
        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=rollback_cmd if success else None,
        )

    async def _add_firewall_rule(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Add an arbitrary iptables rule.

        parameters: {'rule': '-A INPUT -s 10.0.0.5 -j DROP'}
        """
        rule = action.parameters.get("rule", "").strip()
        if not rule:
            return self._make_result(
                action,
                success=False,
                message="Missing required parameter 'rule'",
                rollback_command=None,
            )

        apply_cmd = f"iptables {rule}"
        # Build rollback by replacing the first -A/-I flag with -D
        rollback_rule = rule
        for flag in ("-A ", "-I "):
            if rollback_rule.startswith(flag):
                rollback_rule = "-D " + rollback_rule[len(flag) :]
                break
        rollback_cmd = f"iptables {rollback_rule}"

        rc, output = await self._exec(apply_cmd)
        success = rc == 0
        message = output if output else ("Firewall rule added" if success else "iptables failed")
        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=rollback_cmd if success else None,
        )

    async def _disable_service(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Stop and disable a systemd service.

        target: service name, e.g. 'sshd'
        """
        service = action.target
        apply_cmd = f"systemctl stop {service} && systemctl disable {service}"
        rollback_cmd = f"systemctl enable {service} && systemctl start {service}"

        rc, output = await self._exec(apply_cmd)
        success = rc == 0
        message = (
            output
            if output
            else (f"Service {service} stopped and disabled" if success else "systemctl failed")
        )
        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=rollback_cmd if success else None,
        )

    async def _restart_service(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Restart a systemd service (no rollback — restart is idempotent).

        target: service name, e.g. 'nginx'
        """
        service = action.target
        apply_cmd = f"systemctl restart {service}"

        rc, output = await self._exec(apply_cmd)
        success = rc == 0
        message = (
            output
            if output
            else (f"Service {service} restarted" if success else "systemctl failed")
        )
        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=None,
        )

    async def _kill_process(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Kill a process by name pattern (no rollback).

        target: process name or pattern, e.g. 'malware_payload'
        """
        process = action.target
        apply_cmd = f"pkill -f {process}"

        rc, output = await self._exec(apply_cmd)
        # pkill returns 1 if no processes matched — treat as partial success
        success = rc in (0, 1)
        if rc == 1:
            message = f"No processes matched pattern '{process}'"
        elif rc == 0:
            message = output if output else f"Process '{process}' killed"
        else:
            message = output if output else f"pkill failed (exit {rc})"
            success = False

        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=None,
        )

    async def _update_config(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Write a configuration value to a file on the target container.

        parameters:
            path:    absolute path to the config file, e.g. '/etc/ssh/sshd_config'
            content: full new content to write
        """
        path = action.parameters.get("path", "").strip()
        content = action.parameters.get("content", "")

        if not path:
            return self._make_result(
                action,
                success=False,
                message="Missing required parameter 'path'",
                rollback_command=None,
            )

        # Back up existing file before overwriting
        backup_path = f"{path}.dcptn_bak"
        backup_cmd = f"cp {path} {backup_path} 2>/dev/null || true"
        await self._exec(backup_cmd)

        # Write new content via printf to handle special characters safely
        escaped = content.replace("'", "'\\''")
        write_cmd = f"printf '%s' '{escaped}' > {path}"
        rc, output = await self._exec(write_cmd)

        success = rc == 0
        rollback_cmd = f"cp {backup_path} {path} && rm -f {backup_path}" if success else None
        message = (
            output
            if output
            else (f"Config updated at {path}" if success else f"Write failed (exit {rc})")
        )

        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=rollback_cmd,
        )

    async def _revoke_credential(self, action: DefenseRecommendation) -> DefenseActionResult:
        """Revoke a credential — implementation varies by type.

        target: credential identifier, e.g. 'user:alice' or 'key:/root/.ssh/authorized_keys'
        parameters:
            type: 'ssh_key' | 'user_account' | 'api_token' (optional, inferred from target)
        """
        cred_type = action.parameters.get("type", "").lower()
        target = action.target

        if cred_type == "ssh_key" or target.startswith("key:"):
            key_path = target.removeprefix("key:")
            apply_cmd = f"rm -f {key_path}"
        elif cred_type == "user_account" or target.startswith("user:"):
            username = target.removeprefix("user:")
            apply_cmd = f"usermod -L {username}"
        else:
            apply_cmd = f"passwd -l {target} 2>/dev/null || usermod -L {target} 2>/dev/null"

        rc, output = await self._exec(apply_cmd)
        success = rc == 0
        message = (
            output
            if output
            else (f"Credential '{target}' revoked" if success else f"Revocation failed (exit {rc})")
        )

        return self._make_result(
            action,
            success=success,
            message=message,
            rollback_command=None,
        )

    # ── Rollback ──────────────────────────────────────────────────────────────

    async def rollback_action(self, result: DefenseActionResult) -> DefenseActionResult:
        """Undo a previously applied defensive action via its stored rollback command."""
        if not result.rollback_command:
            log.warning(
                "No rollback command for action type=%s target=%s",
                result.action_type,
                result.target,
            )
            return DefenseActionResult(
                action_type=result.action_type,
                target=result.target,
                success=False,
                message="No rollback command available for this action",
                rollback_command=None,
                executed_at=datetime.now(timezone.utc),
            )

        log.info(
            "Rolling back action type=%s target=%s container=%s",
            result.action_type,
            result.target,
            self._container,
        )

        rc, output = await self._exec(result.rollback_command)
        success = rc == 0
        message = (
            output
            if output
            else ("Rollback successful" if success else f"Rollback failed (exit {rc})")
        )

        if success:
            self._applied = [
                a
                for a in self._applied
                if not (a.action_type == result.action_type and a.target == result.target)
            ]

        log.info(
            "Rollback %s: success=%s target=%s",
            result.action_type,
            success,
            result.target,
        )

        return DefenseActionResult(
            action_type=result.action_type,
            target=result.target,
            success=success,
            message=message,
            rollback_command=None,
            executed_at=datetime.now(timezone.utc),
        )

    # ── Verification ──────────────────────────────────────────────────────────

    async def verify_action(self, result: DefenseActionResult) -> bool:
        """Check whether a defensive action is still active on the target."""
        log.debug(
            "Verifying action type=%s target=%s container=%s",
            result.action_type,
            result.target,
            self._container,
        )

        if result.action_type == DefenseActionType.BLOCK_PORT:
            parts = result.target.split("/")
            proto, port = (parts[0].lower(), parts[1]) if len(parts) == 2 else ("tcp", parts[0])
            cmd = f"iptables -C INPUT -p {proto} --dport {port} -j DROP"
            rc, _ = await self._exec(cmd)
            return rc == 0

        if result.action_type == DefenseActionType.ADD_FIREWALL_RULE:
            # Verify by checking iptables-save output for the rollback rule pattern
            if result.rollback_command:
                # The rollback_command is "iptables -D <rule>" — reconstruct check
                # by replacing -D with -C
                check_rule = result.rollback_command.replace("iptables -D ", "-C ", 1)
                cmd = f"iptables {check_rule}"
                rc, _ = await self._exec(cmd)
                return rc == 0
            return False

        if result.action_type == DefenseActionType.DISABLE_SERVICE:
            service = result.target
            cmd = f"systemctl is-active {service}"
            rc, output = await self._exec(cmd)
            # Service should be inactive (stopped) — is-active returns non-zero when inactive
            return rc != 0 and output.strip() in ("inactive", "failed", "unknown")

        if result.action_type == DefenseActionType.RESTART_SERVICE:
            service = result.target
            cmd = f"systemctl is-active {service}"
            rc, _ = await self._exec(cmd)
            return rc == 0

        if result.action_type == DefenseActionType.KILL_PROCESS:
            process = result.target
            cmd = f"pgrep -f {process}"
            rc, _ = await self._exec(cmd)
            # Process is gone if pgrep finds nothing (exit 1)
            return rc != 0

        if result.action_type == DefenseActionType.UPDATE_CONFIG:
            path = result.target
            cmd = f"test -f {path}"
            rc, _ = await self._exec(cmd)
            return rc == 0

        if result.action_type == DefenseActionType.REVOKE_CREDENTIAL:
            target = result.target
            if target.startswith("user:"):
                username = target.removeprefix("user:")
                cmd = f"passwd -S {username}"
                rc, output = await self._exec(cmd)
                # 'L' in output means account is locked
                return rc == 0 and " L " in output
            if target.startswith("key:"):
                key_path = target.removeprefix("key:")
                cmd = f"test ! -f {key_path}"
                rc, _ = await self._exec(cmd)
                return rc == 0
            return False

        log.warning("verify_action: unhandled action type %s", result.action_type)
        return False

    # ── Listing ───────────────────────────────────────────────────────────────

    async def list_applied_actions(self) -> list[DefenseActionResult]:
        """Return all defensive actions currently tracked as applied."""
        return list(self._applied)
