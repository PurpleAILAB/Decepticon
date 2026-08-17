"""Fetch and verify the pinned MITRE ATT&CK STIX input for Skillogy.

The graph builder remains offline-only.  This explicit bootstrap step downloads
one immutable release URL, validates its SHA-256, and installs it atomically
under the caller's cache directory.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen

ATTACK_VERSION = "19.1"
STIX_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "6c3719993d0401de199203ecc3f369544d9e091c/"
    "enterprise-attack/enterprise-attack-19.1.json"
)
STIX_SHA256 = "bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"


def default_bundle_path() -> Path:
    """Return the single default consumed by the graph builder and bootstrapper."""
    configured = os.environ.get("SKILLOGY_STIX_BUNDLE")
    if configured:
        return Path(configured).expanduser()
    return (
        Path.home() / ".cache" / "skillogy" / "mitre" / f"enterprise-attack-{ATTACK_VERSION}.json"
    )


def sha256_file(path: Path) -> str:
    """Hash ``path`` without loading the STIX bundle into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_hash(path: Path, expected_sha256: str) -> None:
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"{path}: SHA-256 mismatch: expected {expected_sha256}, got {actual}. "
            "Delete the invalid file and rerun the bootstrap command."
        )


def ensure_stix_bundle(
    destination: Path | None = None,
    *,
    url: str = STIX_URL,
    expected_sha256: str = STIX_SHA256,
) -> Path:
    """Ensure a verified STIX bundle exists, fetching only when absent.

    Existing files are never silently replaced.  A corrupted or unexpected
    cache is an operator-visible failure rather than an opportunity for a
    mutable network response to alter the graph input.
    """
    output = (destination or default_bundle_path()).expanduser()
    if output.exists():
        _validate_hash(output, expected_sha256)
        return output

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle, urlopen(url, timeout=30) as response:  # noqa: S310 -- pinned HTTPS URL + hash below
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        _validate_hash(temporary, expected_sha256)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output
