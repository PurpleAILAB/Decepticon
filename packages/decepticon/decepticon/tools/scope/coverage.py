"""Bug-bounty scope -> AssetType -> specialist routing coverage engine.

Pure-Python (stdlib + the seeds loader only). Given a list of in-scope asset
descriptors, this classifies each into an AssetType from the canonical
``asset_types.yaml`` taxonomy, resolves the wired Phase(s) for that type, maps
each phase to the specialist role(s) that own it, and aggregates a coverage
report so the orchestrator can guarantee every in-scope asset is dispatched to
the right specialist — and surface any that fall through for manual handling.

Single source of truth:
  AssetType -> Phase  comes from ``seeds/asset_types.yaml`` (``phases``).
  Phase     -> Role   is the inversion of ``_PHASE_FOR_ROLE`` in the skillogy
                      middleware — never a duplicated table here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from decepticon.skillogy.builder.seeds import AssetTypeSeed, load_asset_types


@dataclass(frozen=True, slots=True)
class AssetCoverage:
    """Routing decision for a single in-scope asset."""

    asset: str
    asset_type: str
    phases: tuple[str, ...]
    specialists: tuple[str, ...]
    covered: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "asset_type": self.asset_type,
            "phases": list(self.phases),
            "specialists": list(self.specialists),
            "covered": self.covered,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Aggregate coverage across a whole scope."""

    assets: tuple[AssetCoverage, ...]
    covered_count: int
    uncovered: tuple[str, ...]
    specialists_engaged: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "assets": [a.to_dict() for a in self.assets],
            "total": len(self.assets),
            "covered_count": self.covered_count,
            "uncovered": list(self.uncovered),
            "specialists_engaged": list(self.specialists_engaged),
        }


# ponytail: heuristic patterns, extend as new asset shapes appear
_CIDR_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_CONTRACT_RE = re.compile(r"^0x[0-9a-f]{40}$")
_LIBNAME_RE = re.compile(r"^lib[a-z0-9_]+$")
_ORG_REPO_RE = re.compile(r"^[a-z0-9_-]+/[a-z0-9_.-]+$")

_CRYPTO_HINTS = ("mbedtls", "psa-crypto", "tf-psa", "crypto")
_FIRMWARE_HINTS = (
    "firmware",
    "trusted-firmware",
    "tf-a",
    "tf-m",
    "op-tee",
    "optee",
    "bl1",
    "bl2",
    "bl31",
    "secure boot",
)
_BINARY_SUFFIXES = (".so", ".dll", ".elf")
_SOURCE_HINTS = ("github.com", "gitlab")


def classify_asset(asset: str) -> str:
    """Heuristically classify a free-form scope descriptor into an AssetType.

    Returns a ``name`` that exists in ``asset_types.yaml``. Checks run
    most-specific-first; falls back to ``other-asset``.
    """
    # ponytail: heuristic patterns, extend as new asset shapes appear
    s = asset.strip().lower()
    if not s:
        return "other-asset"

    # Blockchain contract address (very distinctive).
    if _CONTRACT_RE.match(s):
        return "smart-contract"

    # Network identifiers / scope selectors.
    if _CIDR_RE.match(s):
        return "cidr"
    if _IPV4_RE.match(s):
        return "ip-address"
    if s.startswith("*.") or "*" in s:
        return "wildcard"

    # Strip scheme for host/path inspection; remember whether one was present.
    had_scheme = s.startswith(("http://", "https://"))
    body = s.split("://", 1)[1] if "://" in s else s
    host = body.split("/", 1)[0]

    # API services (more specific than a bare URL).
    if "graphql" in s:
        return "api-graphql"
    if host.startswith("api."):
        return "api-graphql" if "graphql" in body else "api-rest"
    if "/api" in body or "api-" in host:
        return "api-rest"

    # Mobile application bundles / store links.
    if "apps.apple.com" in s or s.endswith(".ipa"):
        return "ios-ipa"
    if "play.google.com" in s or s.endswith(".apk"):
        return "android-apk"

    # Source repositories.
    if any(h in s for h in _SOURCE_HINTS) or s.endswith(".git"):
        return "source-code"

    # Compiled binaries.
    if s.endswith(_BINARY_SUFFIXES) or _LIBNAME_RE.match(s):
        return "elf-binary"

    # Cryptographic libraries (keyword hints).
    if any(h in s for h in _CRYPTO_HINTS):
        return "cryptographic-library"

    # Firmware / secure-boot / ARM trusted-firmware projects.
    if any(h in s for h in _FIRMWARE_HINTS):
        return "firmware"

    # A scheme-bearing target that matched no more-specific type is a generic
    # web URL (routes to web-exploitation).
    if had_scheme:
        return "url"

    # org/repo source target (no dots before the slash => not host/path).
    if _ORG_REPO_RE.match(s) and "." not in host:
        return "source-code"

    # Hostnames: subdomain (a.b.c) vs registrable domain (a.b).
    if _IPV4_RE.match(host) is None and "." in host:
        labels = host.split(".")
        if len(labels) >= 3:
            return "subdomain"
        return "domain"

    return "other-asset"


def _phase_to_roles() -> dict[str, list[str]]:
    """Invert the role->phase map into phase->[roles]."""
    # ponytail: single source of truth; invert the role->phase map rather than
    # duplicate it
    from decepticon.middleware.skillogy import _PHASE_FOR_ROLE

    out: dict[str, list[str]] = {}
    for role, phase in _PHASE_FOR_ROLE.items():
        out.setdefault(phase, []).append(role)
    return out


def roles_for_asset_type(
    asset_type: str,
    asset_types: dict[str, AssetTypeSeed] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve ``(phases, specialist_roles)`` for an AssetType name.

    ``asset_types`` may be injected (name -> seed) for testing; otherwise it is
    built from ``load_asset_types()``. An AssetType with no wired phases yields
    ``((), ())``.
    """
    if asset_types is None:
        asset_types = {at.name: at for at in load_asset_types()}

    seed = asset_types.get(asset_type)
    if seed is None or not seed.phases:
        return (), ()

    phase_to_roles = _phase_to_roles()
    roles: list[str] = []
    for phase in seed.phases:
        for role in phase_to_roles.get(phase, ()):
            if role not in roles:
                roles.append(role)
    return seed.phases, tuple(roles)


def plan_coverage(assets: list[str]) -> CoverageReport:
    """Classify and route every asset, returning an aggregate coverage report."""
    asset_types = {at.name: at for at in load_asset_types()}

    rows: list[AssetCoverage] = []
    uncovered: list[str] = []
    engaged: set[str] = set()

    for asset in assets:
        asset_type = classify_asset(asset)
        phases, specialists = roles_for_asset_type(asset_type, asset_types)
        covered = bool(specialists)
        if covered:
            note = f"route to {', '.join(specialists)} via phase(s) {', '.join(phases)}"
            engaged.update(specialists)
        else:
            uncovered.append(asset)
            note = (
                f"no phase mapping for type {asset_type!r} — "
                "handle via analyst/manual"
            )
        rows.append(
            AssetCoverage(
                asset=asset,
                asset_type=asset_type,
                phases=phases,
                specialists=specialists,
                covered=covered,
                note=note,
            )
        )

    return CoverageReport(
        assets=tuple(rows),
        covered_count=sum(1 for r in rows if r.covered),
        uncovered=tuple(uncovered),
        specialists_engaged=tuple(sorted(engaged)),
    )


if __name__ == "__main__":
    # Self-check (no project-wide build/lint): prove the routing contract.
    _wild = classify_asset("*.example.com")
    _w_phases, _w_specs = roles_for_asset_type(_wild)
    assert _wild == "wildcard", _wild
    assert "recon" in _w_specs and "osint_operator" in _w_specs, _w_specs

    _api = classify_asset("api-sandbox.x.com/graphql")
    _a_phases, _a_specs = roles_for_asset_type(_api)
    assert _api == "api-graphql", _api
    assert _a_specs == ("exploit",), _a_specs

    _ipa = classify_asset("CorpApp.ipa")
    _i_phases, _i_specs = roles_for_asset_type(_ipa)
    assert _ipa == "ios-ipa", _ipa
    assert _i_specs == ("mobile_operator",), _i_specs

    _crypto = classify_asset("mbedtls")
    _c_phases, _c_specs = roles_for_asset_type(_crypto)
    assert _crypto == "cryptographic-library", _crypto
    assert _c_specs == ("analyst", "reverser", "bounty_hunter"), _c_specs

    _report = plan_coverage(
        [
            "*.example.com",
            "api-sandbox.x.com/graphql",
            "CorpApp.ipa",
            "mbedtls",
            "0x" + "a" * 40,
            "192.0.2.0/24",
            "shop.example.com",
            "example.com",
        ]
    )
    print("classify+route self-check OK")
    print(f"  wildcard  -> {_wild}: {_w_specs}")
    print(f"  graphql   -> {_api}: {_a_specs}")
    print(f"  ipa       -> {_ipa}: {_i_specs}")
    print(f"  mbedtls   -> {_crypto}: {_c_specs}")
    print(
        f"  report: {_report.covered_count}/{len(_report.assets)} covered, "
        f"uncovered={list(_report.uncovered)}, "
        f"engaged={list(_report.specialists_engaged)}"
    )
