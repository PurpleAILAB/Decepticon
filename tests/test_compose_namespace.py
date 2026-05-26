"""Verify docker-compose.yml respects DECEPTICON_IMAGE_NAMESPACE override.

Renders the compose file via `docker compose config` with the env var set,
then asserts that every Decepticon image reference uses the override prefix.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.yml"
DOTENV = REPO_ROOT / ".env"


@pytest.fixture(autouse=True)
def _ensure_dotenv():
    """`docker compose config` fails if env_file targets are missing.

    Services in docker-compose.yml declare `env_file: .env`, which the
    operator normally generates via the launcher onboard flow. In CI /
    fresh checkouts that file isn't present, so create an empty stand-in
    for the duration of the test and remove it afterward if we created it.
    """
    created = False
    if not DOTENV.exists():
        DOTENV.touch()
        created = True
    try:
        yield
    finally:
        if created:
            DOTENV.unlink(missing_ok=True)


def _render(env_overrides: dict[str, str]) -> dict:
    """Run `docker compose config` and parse the result."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")
    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"`docker compose config` failed (exit {result.returncode}):\n"
            f"--- stderr ---\n{result.stderr}\n--- stdout ---\n{result.stdout}"
        )
    return yaml.safe_load(result.stdout)


def _decepticon_image_refs(rendered: dict) -> list[str]:
    """Return every `image:` value for a namespaced Decepticon image.

    Images without a `/` (e.g. local-build `decepticon-sandbox-reversing`)
    are excluded by design — they have no registry prefix to override.
    """
    refs: list[str] = []
    for svc in (rendered.get("services") or {}).values():
        img = svc.get("image", "")
        if "/" not in img:
            continue  # local-build image; no registry prefix to namespace
        if "decepticon-" in img:
            refs.append(img)
    return refs


def test_default_namespace_is_purpleailab():
    rendered = _render({})
    refs = _decepticon_image_refs(rendered)
    assert refs, "expected at least one decepticon image reference"
    for ref in refs:
        assert ref.startswith("ghcr.io/purpleailab/decepticon-"), (
            f"default namespace should be ghcr.io/purpleailab/, got: {ref}"
        )


def test_namespace_override_via_env():
    rendered = _render({"DECEPTICON_IMAGE_NAMESPACE": "example.invalid/test-ns"})
    refs = _decepticon_image_refs(rendered)
    assert refs, "expected at least one decepticon image reference"
    for ref in refs:
        assert ref.startswith("example.invalid/test-ns/decepticon-"), (
            f"override should rewrite namespace, got: {ref}"
        )
