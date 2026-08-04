"""Cybench benchmark provider.

Wires the [Cybench](https://cybench.github.io/) professional-CTF suite
(Stanford, ICLR 2025 — 40 tasks from 4 recent competitions) into the
Decepticon benchmark harness. Cybench is the field's de-facto reference
CTF benchmark and the common third-party benchmark cited across the
frontier-lab system cards, so scoring Decepticon against it gives a
directly comparable capability number.

Scope (v1): **docker-served tasks only** — the web/pwn tasks that ship a
``start_docker.sh`` and expose a network service, exactly parallel to the
XBOW provider (build/run a target, point the agent at it, match the
flag). Local-file tasks (crypto/rev/forensics that hand the agent files
instead of a service) are skipped for now because staging their files
into the sandbox without also leaking ``flag.txt`` / ``metadata/`` needs
per-task curation; the number skipped is logged, never silently dropped.

Unlike XBOW's synthetic ``FLAG{sha256(id)}``, each Cybench task carries
its competition-native flag (``HTB{...}``, ``flag{...}``) as the answer
of its final subtask; the provider reads that literal and matches it
verbatim, so a loose flag-shaped token in the transcript cannot false-pass.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

from benchmark.providers.base import BaseBenchmarkProvider
from benchmark.schemas import Challenge, ChallengeResult, FilterConfig, SetupResult
from benchmark.state import BenchmarkRunState

log = logging.getLogger(__name__)

# Cybench compose files attach to this pre-existing external Docker
# network (``networks: shared_net: external: true``). The provider
# creates it on demand; it is shared across tasks and intentionally
# left in place on teardown.
_SHARED_NET = "shared_net"


class CybenchProvider(BaseBenchmarkProvider):
    """Benchmark provider for the Cybench professional-CTF suite."""

    def __init__(self, benchmarks_dir: Path | None = None) -> None:
        # Default assumes the upstream repo is checked out at
        # ``benchmark/cybench`` (see README-cybench.md); tasks live under
        # its ``benchmark/`` subtree.
        self._benchmarks_dir = benchmarks_dir or Path("benchmark/cybench/benchmark")

    @property
    def name(self) -> str:
        return "cybench"

    def load_challenges(self, filters: FilterConfig) -> list[Challenge]:
        """Discover docker-served Cybench tasks and apply filters."""
        challenges: list[Challenge] = []
        skipped_local = 0
        skipped_no_flag = 0

        if not self._benchmarks_dir.is_dir():
            return challenges

        for meta_path in sorted(self._benchmarks_dir.rglob("metadata/metadata.json")):
            task_dir = meta_path.parent.parent
            # v1: only tasks that expose a network service via start_docker.sh.
            if not (task_dir / "start_docker.sh").exists():
                skipped_local += 1
                continue

            try:
                data = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            rel = task_dir.relative_to(self._benchmarks_dir)
            expected_flag = self._extract_flag(data.get("subtasks", []))
            if expected_flag is None:
                # No flag-shaped answer to grade against — the task could only
                # ever score False. Skip rather than burn an agent run on it.
                skipped_no_flag += 1
                continue
            challenges.append(
                Challenge(
                    id=self._slug(rel),
                    name=self._display_name(task_dir.name),
                    description=(data.get("hard_prompt") or data.get("easy_prompt") or "")[:2000],
                    level=self._difficulty_to_level(data.get("difficulty", "2")),
                    tags=self._extract_tags(data),
                    win_condition="flag",
                    compose_dir=task_dir,
                    expected_flag=expected_flag,
                    flag_format=self._flag_format(expected_flag),
                )
            )

        if skipped_local:
            log.info(
                "cybench: skipped %d local-file task(s) without start_docker.sh "
                "(docker-served tasks only in v1)",
                skipped_local,
            )
        if skipped_no_flag:
            log.info(
                "cybench: skipped %d docker task(s) with no flag-shaped subtask answer",
                skipped_no_flag,
            )

        if filters.levels:
            challenges = [c for c in challenges if c.level in filters.levels]
        if filters.tags:
            wanted = set(filters.tags)
            challenges = [c for c in challenges if set(c.tags) & wanted]
        if filters.ids:
            wanted = set(filters.ids)
            challenges = [c for c in challenges if c.id in wanted]

        start = (filters.range_start - 1) if filters.range_start is not None else None
        end = filters.range_end if filters.range_end is not None else None
        if start is not None or end is not None:
            challenges = challenges[start:end]

        return challenges

    def setup(self, challenge: Challenge) -> SetupResult:
        """Start the task's docker service and return a reachable target URL."""
        task_dir = challenge.compose_dir
        if task_dir is None:
            return SetupResult(target_url="", success=False, error="no task dir")

        try:
            # The compose files reference an external ``shared_net`` — create
            # it idempotently (create is a no-op if it already exists).
            subprocess.run(
                ["docker", "network", "create", _SHARED_NET],
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["bash", "start_docker.sh"],
                cwd=task_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            ps = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                cwd=task_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            http_port = ""
            extra_ports: dict[int, int] = {}
            for line in ps.stdout.strip().splitlines():
                container = json.loads(line)
                for pub in container.get("Publishers", []):
                    published = pub.get("PublishedPort", 0)
                    target = pub.get("TargetPort", 0)
                    if not published:
                        continue
                    if target == 80:
                        http_port = str(published)
                    else:
                        extra_ports[target] = published

            if not http_port:
                if extra_ports:
                    http_port = str(next(iter(extra_ports.values())))
                else:
                    return SetupResult(
                        target_url="",
                        success=False,
                        error="no published port after start_docker.sh",
                    )

            all_ports = [int(http_port)] + list(extra_ports.values())
            for port in all_ports:
                if not self._wait_for_tcp("localhost", port, timeout=30):
                    return SetupResult(
                        target_url="",
                        success=False,
                        error=f"TCP pre-flight failed: port {port} not open after 30s",
                    )

            # Best-effort HTTP readiness on the primary port (many Cybench
            # services are raw TCP, not HTTP — a failed probe is non-fatal).
            for _ in range(10):
                try:
                    httpx.get(f"http://localhost:{http_port}/", timeout=3, follow_redirects=True)
                    break
                except Exception:
                    time.sleep(2)

            return SetupResult(
                target_url=f"http://host.docker.internal:{http_port}",
                success=True,
                extra_ports=extra_ports,
            )

        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
            detail = str(e)
            if isinstance(e, subprocess.CalledProcessError) and e.stderr:
                detail += f"\nSTDERR: {e.stderr[-500:]}"
            return SetupResult(target_url="", success=False, error=detail)

    def evaluate(
        self,
        challenge: Challenge,
        state: BenchmarkRunState,
        workspace: Path,
    ) -> ChallengeResult:
        """Pass iff the task's literal flag appears in the transcript/workspace."""
        expected = challenge.expected_flag
        haystack = "".join(step.raw_output for step in state.step_history)
        haystack += self._scan_workspace(workspace)

        captured: str | None = None
        # Surface any flag-shaped token for debugging even on a miss.
        m = re.search(r"[A-Za-z0-9_]{2,}\{[^}\n]{1,200}\}", haystack)
        if m:
            captured = m.group(0)

        passed = bool(expected) and expected in haystack
        if passed:
            captured = expected

        return ChallengeResult(
            challenge_id=challenge.id,
            challenge_name=challenge.name,
            level=challenge.level,
            tags=challenge.tags,
            passed=passed,
            flag_captured=captured,
        )

    def teardown(self, challenge: Challenge) -> None:
        """Stop the task's docker service (best-effort, idempotent)."""
        task_dir = challenge.compose_dir
        if task_dir is None:
            return
        script = "stop_docker.sh" if (task_dir / "stop_docker.sh").exists() else None
        try:
            if script:
                subprocess.run(
                    ["bash", script], cwd=task_dir, capture_output=True, text=True, check=True
                )
            else:
                subprocess.run(
                    ["docker", "compose", "down", "-v"],
                    cwd=task_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
        except (OSError, subprocess.CalledProcessError) as exc:
            log.warning("cybench: teardown failed for %s: %s", challenge.id, exc)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _slug(rel: Path) -> str:
        """Stable, CLI-friendly id from a task's path relative to the suite."""
        raw = "cybench/" + rel.as_posix()
        raw = raw.lower().replace("[", "").replace("]", "")
        return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")

    @staticmethod
    def _display_name(dirname: str) -> str:
        # Strip the ``[Easy] `` / ``[Hard] `` difficulty prefix.
        return re.sub(r"^\[[^\]]*\]\s*", "", dirname).strip()

    @staticmethod
    def _difficulty_to_level(difficulty: object) -> int:
        try:
            n = int(str(difficulty))
        except (TypeError, ValueError):
            return 2
        # Cybench difficulties run 0..N; fold into the harness 1..3 scale.
        if n <= 1:
            return 1
        if n == 2:
            return 2
        return 3

    @staticmethod
    def _extract_tags(data: dict) -> list[str]:
        tags = [str(c).lower() for c in data.get("categories", [])]
        tools = data.get("tools", {})
        if isinstance(tools, dict):
            tags += [str(t).lower() for t in tools.get("other", [])]
        # De-dupe, preserve order.
        seen: set[str] = set()
        out: list[str] = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    @staticmethod
    def _extract_flag(subtasks: list) -> str | None:
        """The final-subtask answer is the full flag by Cybench convention.

        Returns the last subtask answer that looks like a flag
        (``prefix{...}``), or ``None`` if none is flag-shaped. There is
        deliberately no fallback to an arbitrary answer: ``evaluate`` does a
        substring match, so returning a short non-flag answer (``"Java"``, a
        count) would risk a false-pass.
        """
        answers = [
            str(s.get("answer", "")) for s in subtasks if isinstance(s, dict) and s.get("answer")
        ]
        for ans in reversed(answers):
            if re.fullmatch(r"[A-Za-z0-9_]{2,}\{.*\}", ans):
                return ans
        return None

    @staticmethod
    def _flag_format(expected_flag: str | None) -> str:
        if expected_flag and "{" in expected_flag:
            return expected_flag.split("{", 1)[0] + "{...}"
        return "FLAG{<64-char-hex>}"

    @staticmethod
    def _scan_workspace(workspace: Path) -> str:
        if not workspace.is_dir():
            return ""
        chunks: list[str] = []
        for f in sorted(workspace.rglob("*")):
            if f.is_file():
                try:
                    chunks.append(f.read_text(errors="ignore"))
                except OSError:
                    continue
        return "".join(chunks)

    @staticmethod
    def _wait_for_tcp(host: str, port: int, timeout: int = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                time.sleep(2)
        return False
