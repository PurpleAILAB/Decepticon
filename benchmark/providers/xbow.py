from __future__ import annotations

import hashlib
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
from decepticon.core.engagement import EngagementState

log = logging.getLogger(__name__)


class XBOWProvider(BaseBenchmarkProvider):
    """Benchmark provider for XBOW validation benchmarks.

    Loads challenges from local benchmark directories, manages Docker-based
    challenge environments, and evaluates flag capture results.
    """

    def __init__(self, benchmarks_dir: Path | None = None) -> None:
        self._benchmarks_dir = benchmarks_dir or Path(
            "benchmark/xbow-validation-benchmarks/benchmarks"
        )

    @property
    def name(self) -> str:
        return "xbow"

    def load_challenges(self, filters: FilterConfig) -> list[Challenge]:
        """Load and filter challenges from benchmark subdirectories."""
        challenges: list[Challenge] = []

        if not self._benchmarks_dir.is_dir():
            return challenges

        for subdir in sorted(self._benchmarks_dir.iterdir()):
            if not subdir.is_dir():
                continue
            benchmark_file = subdir / "benchmark.json"
            if not benchmark_file.exists():
                continue

            data = json.loads(benchmark_file.read_text())
            challenges.append(
                Challenge(
                    id=subdir.name,
                    name=data["name"],
                    description=data["description"],
                    level=int(data["level"]),
                    tags=data["tags"],
                    win_condition=data.get("win_condition", "flag"),
                    compose_dir=subdir,
                )
            )

        if filters.levels:
            challenges = [c for c in challenges if c.level in filters.levels]

        if filters.tags:
            filter_tags = set(filters.tags)
            challenges = [c for c in challenges if set(c.tags) & filter_tags]

        # range is 1-based from the user; convert start to 0-based
        start = (filters.range_start - 1) if filters.range_start is not None else None
        end = filters.range_end if filters.range_end is not None else None
        if start is not None or end is not None:
            challenges = challenges[start:end]

        return challenges

    def preflight_build(self, challenges: list[Challenge]) -> dict[str, str]:
        """Pre-build all challenge images via make build. Returns {id: error} for failures."""
        failures: dict[str, str] = {}
        for challenge in challenges:
            result = subprocess.run(
                ["make", "build"],
                cwd=challenge.compose_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Retry with NO_CACHE=1
                retry = subprocess.run(
                    ["make", "build", "NO_CACHE=1"],
                    cwd=challenge.compose_dir,
                    capture_output=True,
                    text=True,
                )
                if retry.returncode != 0:
                    failures[challenge.id] = (
                        retry.stderr[-500:] if retry.stderr else "Unknown build error"
                    )
        return failures

    def setup(self, challenge: Challenge) -> SetupResult:
        """Build and start the challenge Docker environment via make."""
        try:
            result = subprocess.run(
                ["make", "build"],
                cwd=challenge.compose_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Retry with NO_CACHE=1 on failure
                subprocess.run(
                    ["make", "build", "NO_CACHE=1"],
                    cwd=challenge.compose_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )

            subprocess.run(
                ["make", "run"],
                cwd=challenge.compose_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                cwd=challenge.compose_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            http_port = ""
            extra_ports: dict[int, int] = {}  # target_port -> published_port
            for line in result.stdout.strip().splitlines():
                container = json.loads(line)
                publishers = container.get("Publishers", [])
                for pub in publishers:
                    published = pub.get("PublishedPort", 0)
                    target = pub.get("TargetPort", 0)
                    if published:
                        if target == 80:
                            http_port = str(published)
                        else:
                            extra_ports[target] = published

            # Prefer HTTP port 80; fall back to first available port
            if not http_port:
                if extra_ports:
                    http_port = str(next(iter(extra_ports.values())))
                else:
                    http_port = "80"

            target_url = f"http://host.docker.internal:{http_port}"

            # TCP pre-flight: verify all required ports are accepting connections.
            # Ports that never open indicate a failed container start — abort early
            # rather than dispatching the agent into a dead target (saves ~20 min).
            all_ports = [int(http_port)] + list(extra_ports.values())
            for port in all_ports:
                if not self._wait_for_tcp("localhost", port, timeout=30):
                    return SetupResult(
                        target_url="",
                        success=False,
                        error=f"TCP pre-flight failed: port {port} not accepting connections after 30s",
                    )

            # HTTP readiness check on the primary port
            for attempt in range(15):
                try:
                    r = httpx.get(
                        f"http://localhost:{http_port}/",
                        timeout=3,
                        follow_redirects=True,
                    )
                    log.info(
                        "Challenge %s ready (HTTP %d) after %ds",
                        challenge.id,
                        r.status_code,
                        attempt * 2,
                    )
                    break
                except Exception:
                    time.sleep(2)
            else:
                log.warning(
                    "Challenge %s: HTTP health check timed out after 30s, proceeding anyway",
                    challenge.id,
                )

            return SetupResult(
                target_url=target_url,
                success=True,
                extra_ports=extra_ports,
            )

        except subprocess.CalledProcessError as e:
            error_detail = str(e)
            if e.stderr:
                error_detail += f"\nSTDERR: {e.stderr[-500:]}"
            return SetupResult(target_url="", success=False, error=error_detail)

    def evaluate(
        self,
        challenge: Challenge,
        state: EngagementState,
        workspace: Path,
    ) -> ChallengeResult:
        """Evaluate whether the expected flag was captured."""
        flag_value = hashlib.sha256(challenge.id.upper().encode()).hexdigest()
        expected_flag = f"FLAG{{{flag_value}}}"

        combined_output = "".join(ir.raw_output for ir in state.iteration_history)
        match = re.search(r"FLAG\{[a-f0-9]+\}", combined_output)

        if match:
            captured = match.group(0)
            passed = captured == expected_flag
            return ChallengeResult(
                challenge_id=challenge.id,
                challenge_name=challenge.name,
                level=challenge.level,
                tags=challenge.tags,
                passed=passed,
                flag_captured=captured,
            )

        return ChallengeResult(
            challenge_id=challenge.id,
            challenge_name=challenge.name,
            level=challenge.level,
            tags=challenge.tags,
            passed=False,
        )

    def _wait_for_tcp(self, host: str, port: int, timeout: int = 30) -> bool:
        """Return True if TCP port accepts a connection within timeout seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                time.sleep(2)
        return False

    def teardown(self, challenge: Challenge) -> None:
        """Stop and remove challenge containers (best-effort)."""
        try:
            # Use docker compose down -v for thorough cleanup (removes volumes)
            subprocess.run(
                ["docker", "compose", "down", "-v"],
                cwd=challenge.compose_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            # Remove build guard so next run rebuilds with fresh flag
            guard = challenge.compose_dir / ".xben_build_done"
            guard.unlink(missing_ok=True)
        except subprocess.CalledProcessError:
            pass
