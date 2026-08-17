"""Behavior tests for the Bash installer."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[5]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


def test_stable_resolver_reads_release_payload_from_curl(tmp_path: Path) -> None:
    script_without_main = INSTALL_SCRIPT.read_text(encoding="utf-8").rsplit('\nmain "$@"', 1)[0]
    releases = [
        {
            "tag_name": "v1.2.3",
            "published_at": "2020-01-01T00:00:00Z",
            "draft": False,
            "prerelease": False,
        }
    ]
    harness = tmp_path / "resolve-stable.sh"
    harness.write_text(
        f"""{script_without_main}
curl() {{
    printf '%s' "$RELEASES_JSON"
}}
resolve_stable_soaked
""",
        encoding="utf-8",
    )
    env = os.environ | {
        "DECEPTICON_STABLE_SOAK_DAYS": "7",
        "RELEASES_JSON": json.dumps(releases),
    }

    completed = subprocess.run(
        ["bash", str(harness)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert completed.stdout.strip() == "1.2.3"
