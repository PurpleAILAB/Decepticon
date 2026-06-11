"""CVE-Bench challenge loader.

Parses upstream ``uiuc-kang-lab/cve-bench/src/critical/metadata/CVE-*.yml``
into :class:`CVEBenchChallenge`. 3-CVE snapshot ships under ``fixtures/``
for the offline dry run (K5); full-run mode points ``fixtures_dir`` at a
checked-out cve-bench clone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 8 CVE-Bench win conditions, verbatim from upstream README §Overview.
# Order is the canonical leaderboard order; do not reorder.
WIN_CONDITIONS: tuple[str, ...] = (
    "denial_of_service",
    "file_access",
    "remote_code_execution",
    "database_modification",
    "database_access",
    "unauthorized_admin_login",
    "privilege_escalation",
    "outbound_service",
)

DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures"

_REQUIRED = (
    "admin_username",
    "application_url",
    "attacker_role",
    "default_username",
    "default_password",
    "denial_of_service_duration",
    "outbound_service_url",
    "proof_uploading_url",
    "remote_code_executable_path",
    "secret_file_path",
    "secret_table_name",
)


@dataclass(frozen=True)
class CVEBenchChallenge:
    """One CVE-Bench challenge, parsed 1:1 from the upstream metadata YAML."""

    cve_id: str
    variant: str  # "zero_day" | "one_day"
    application_url: str
    admin_username: str
    attacker_role: str
    default_username: str
    default_password: str
    denial_of_service_duration: int
    outbound_service_url: str
    proof_uploading_url: str
    remote_code_executable_path: str
    secret_file_path: str
    secret_table_name: str
    additional_info: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.cve_id}:{self.variant}"

    @property
    def application_hosts(self) -> list[str]:
        """Split comma-separated host:port list (e.g. Zabbix exposes two)."""
        return [h.strip() for h in self.application_url.split(",") if h.strip()]


def _parse_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping, got {type(data).__name__}")
    return data


def _build(cve_id: str, variant: str, data: dict[str, Any]) -> CVEBenchChallenge:
    missing = [k for k in _REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{cve_id}: missing required keys {missing}")
    info = data.get("additional_info")
    return CVEBenchChallenge(
        cve_id=cve_id,
        variant=variant,
        application_url=str(data["application_url"]),
        admin_username=str(data["admin_username"]),
        attacker_role=str(data["attacker_role"]),
        default_username=str(data["default_username"]),
        default_password=str(data["default_password"]),
        denial_of_service_duration=int(data["denial_of_service_duration"]),
        outbound_service_url=str(data["outbound_service_url"]),
        proof_uploading_url=str(data["proof_uploading_url"]),
        remote_code_executable_path=str(data["remote_code_executable_path"]),
        secret_file_path=str(data["secret_file_path"]),
        secret_table_name=str(data["secret_table_name"]),
        additional_info=None if info in (None, "null") else str(info),
        raw=data,
    )


def load_one(
    cve_id: str,
    variants: tuple[str, ...] = ("zero_day", "one_day"),
    fixtures_dir: Path | None = None,
) -> list[CVEBenchChallenge]:
    base = fixtures_dir or DEFAULT_FIXTURES_DIR
    path = base / f"{cve_id}.yml"
    if not path.exists():
        raise FileNotFoundError(f"CVE metadata not found: {path}")
    data = _parse_yaml(path)
    return [_build(cve_id, v, data) for v in variants]


def load_all(
    fixtures_dir: Path | None = None,
    variants: tuple[str, ...] = ("zero_day", "one_day"),
) -> list[CVEBenchChallenge]:
    base = fixtures_dir or DEFAULT_FIXTURES_DIR
    if not base.is_dir():
        raise FileNotFoundError(f"fixtures dir not found: {base}")
    out: list[CVEBenchChallenge] = []
    for path in sorted(base.glob("CVE-*.yml")):
        data = _parse_yaml(path)
        for v in variants:
            out.append(_build(path.stem, v, data))
    return out
