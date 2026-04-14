"""Decepticon entry point: `decepticon` or `python -m decepticon`.

Starts all Docker services and opens the interactive CLI — the same
environment that open-source users get via the bash launcher.

For development with hot-reload, use `make dev` + `make cli` instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Colors ───────────────────────────────────────────────────────
DIM = "\033[0;2m"
GREEN = "\033[0;32m"
RED = "\033[0;31m"
BOLD = "\033[1m"
NC = "\033[0m"

# Default LangGraph port when neither env nor .env pins one.
_DEFAULT_LANGGRAPH_PORT = 2024


def _find_project_root() -> Path:
    """Locate the repo root containing docker-compose.yml."""
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "docker-compose.yml").exists():
        return candidate
    cwd = Path.cwd()
    if (cwd / "docker-compose.yml").exists():
        return cwd
    print(f"{RED}Error: docker-compose.yml not found.{NC}")
    print(f"{DIM}Run from the repo root, or use the bash launcher if installed via curl|bash.{NC}")
    sys.exit(1)


def _compose(root: Path) -> list[str]:
    """Base docker compose command."""
    cmd = ["docker", "compose", "--project-directory", str(root)]
    env_file = root / ".env"
    if env_file.exists():
        cmd.extend(["--env-file", str(env_file)])
    return cmd


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser: ``KEY=VALUE`` lines, ``#`` comments, no shell."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            values[key] = val
    return values


def _resolve_env(root: Path) -> tuple[int, Path]:
    """Resolve runtime config from (os.environ ∪ .env).

    Precedence ``os.environ`` > ``.env`` > hardcoded default, matching
    ``docker compose --env-file``. Returns ``(port, home)``:

    - ``port``: LangGraph API port to poll, honoring ``LANGGRAPH_PORT``.
    - ``home``: Absolute path used for ``DECEPTICON_HOME``. Tilde is
      expanded here because Docker Compose cannot expand ``~`` on its
      own (see .env.example), and the compose file's default
      ``${DECEPTICON_HOME:-~/.decepticon}`` would otherwise create a
      literal ``~`` directory on the host.
    """
    env_file = _parse_env_file(root / ".env")

    port_raw = os.environ.get("LANGGRAPH_PORT") or env_file.get("LANGGRAPH_PORT")
    try:
        port = int(port_raw) if port_raw else _DEFAULT_LANGGRAPH_PORT
    except ValueError:
        print(f"{RED}Invalid LANGGRAPH_PORT: {port_raw!r}{NC}")
        sys.exit(2)

    home_raw = (
        os.environ.get("DECEPTICON_HOME") or env_file.get("DECEPTICON_HOME") or "~/.decepticon"
    )
    home = Path(home_raw).expanduser().resolve()
    return port, home


def _wait_for_server(port: int, timeout: int = 90) -> bool:
    """Block until LangGraph server is ready on ``port``."""
    waited = 0
    print(f"{DIM}Waiting for LangGraph server on :{port}", end="", flush=True)
    while waited < timeout:
        try:
            req = urllib.request.Request(
                f"http://localhost:{port}/assistants/search",
                data=b'{"graph_id":"decepticon","limit":1}',
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            if b"decepticon" in resp.read():
                print(f" {GREEN}ready{NC}")
                return True
        except (urllib.error.URLError, OSError):
            pass
        print(".", end="", flush=True)
        time.sleep(2)
        waited += 2
    print(f"{NC}\n{RED}Server failed to start within {timeout}s.{NC}")
    return False


def main() -> None:
    """Start services and open CLI — identical to production."""
    root = _find_project_root()
    compose = _compose(root)
    port, home = _resolve_env(root)

    # Propagate the expanded DECEPTICON_HOME into the compose subprocess
    # so the sandbox workspace bind mount (docker-compose.yml:69) resolves
    # to an absolute path rather than a literal ``~``.
    home.mkdir(parents=True, exist_ok=True)
    child_env = {**os.environ, "DECEPTICON_HOME": str(home)}

    print(f"{DIM}Building and starting services (DECEPTICON_HOME={home}, port={port})...{NC}")
    # Do NOT swallow stdout/stderr — build + pull errors should stream
    # live so a failure is visible immediately rather than masquerading
    # as a "Server failed to start within 90s" timeout later.
    result = subprocess.run(
        [*compose, "up", "-d", "--build"],
        env=child_env,
    )
    if result.returncode != 0:
        print(
            f"{RED}docker compose up failed (exit {result.returncode}).{NC} "
            f"{DIM}See the output above for the build/pull error.{NC}"
        )
        sys.exit(result.returncode)

    if not _wait_for_server(port=port):
        print(f"{DIM}Check logs: {BOLD}make logs{NC}")
        sys.exit(1)

    subprocess.run([*compose, "--profile", "cli", "run", "--rm", "cli"], env=child_env)


if __name__ == "__main__":
    main()
