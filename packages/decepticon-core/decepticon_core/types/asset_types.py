"""Canonical asset-type taxonomy — the single source of truth for the 75
asset/domain types Decepticon can be scoped against.

Pure stdlib (no langchain/langgraph) so it is importable from any context,
including the dependency-light contract layer. Consumed by:

  * ``engagement.ScopeEntry.type`` validation (normalize free-form input),
  * ``EngagementContextMiddleware`` (the flag-gated Asset Coverage Brief),
  * ``scripts/asset_coverage.py`` (the coverage report).

The taxonomy mirrors the HackerOne/Bugcrowd structured-scope ``asset_type``
enum (#1-15) plus an expansion (#16-75). ``coverage`` is an honesty flag:
"covered" = existing skills handle it; "partial" = some skills, gaps remain;
"gap" = no dedicated skill yet (domain waves fill these).
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass

CATEGORIES: tuple[str, ...] = (
    "core",
    "web-network",
    "cloud-infra",
    "desktop-software",
    "web3",
    "ai-ml",
    "identity-auth",
    "networking-physical",
    "data-storage",
    "comms-integrations",
)

VALID_ROE_KINDS: tuple[str, ...] = ("cidr", "ip", "host", "domain-glob", "non-network")
VALID_COVERAGE: tuple[str, ...] = ("covered", "partial", "gap")

VALID_AGENT_ROLES: frozenset[str] = frozenset(
    {
        "decepticon",
        "soundwave",
        "recon",
        "exploit",
        "postexploit",
        "analyst",
        "reverser",
        "ad_operator",
        "cloud_hunter",
        "phisher",
        "mobile_operator",
        "wireless_operator",
        "contract_auditor",
        "blue_cell",
        "defender",
        "scanner",
        "exploiter",
        "verifier",
        "patcher",
        "detector",
        "vulnresearch",
    }
)


@dataclass(frozen=True, slots=True)
class AssetType:
    id: str
    number: int
    label: str
    category: str
    agents: tuple[str, ...]
    coverage: str
    roe_kind: str
    aliases: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    recon_entrypoint: str = ""
    opsec_default: str = "standard"
    safety_critical: bool = False
    gated_by_conops: str = ""
    profile: str | None = None

    @property
    def skill_tag(self) -> str:
        return f"asset:{self.id}"


ASSET_TYPES: tuple[AssetType, ...] = (
    AssetType(
        "cidr",
        1,
        "CIDR",
        "core",
        ("recon", "exploit", "postexploit"),
        "covered",
        "cidr",
        aliases=("ip-range", "cidr-block"),
    ),
    AssetType(
        "domain", 2, "Domain", "core", ("recon",), "covered", "domain-glob", aliases=("fqdn",)
    ),
    AssetType(
        "ios-appstore",
        3,
        "iOS : App Store",
        "core",
        ("mobile_operator", "reverser"),
        "partial",
        "non-network",
    ),
    AssetType(
        "ios-testflight",
        4,
        "iOS : TestFlight",
        "core",
        ("mobile_operator",),
        "partial",
        "non-network",
    ),
    AssetType(
        "ios-ipa",
        5,
        "iOS : .IPA",
        "core",
        ("mobile_operator", "reverser"),
        "covered",
        "non-network",
        aliases=("ipa",),
    ),
    AssetType(
        "android-playstore",
        6,
        "Android : Play Store",
        "core",
        ("mobile_operator",),
        "partial",
        "non-network",
    ),
    AssetType(
        "android-apk",
        7,
        "Android : .APK",
        "core",
        ("mobile_operator", "reverser"),
        "covered",
        "non-network",
        aliases=("apk",),
    ),
    AssetType(
        "windows-msstore",
        8,
        "Windows : Microsoft Store",
        "core",
        ("reverser",),
        "gap",
        "non-network",
    ),
    AssetType(
        "source-code", 9, "Source Code", "core", ("analyst", "reverser"), "partial", "non-network"
    ),
    AssetType("executable", 10, "Executable", "core", ("reverser",), "covered", "non-network"),
    AssetType(
        "smart-contract",
        11,
        "Smart Contract",
        "core",
        ("contract_auditor",),
        "covered",
        "non-network",
    ),
    AssetType("wildcard", 12, "Wildcard", "core", ("recon",), "covered", "domain-glob"),
    AssetType(
        "ip-address",
        13,
        "IP Address",
        "core",
        ("recon", "exploit"),
        "covered",
        "ip",
        aliases=("ip",),
    ),
    AssetType("hardware-iot", 14, "Hardware / IoT", "core", ("reverser",), "partial", "host"),
    AssetType(
        "other-asset", 15, "Other Asset", "core", ("recon", "analyst"), "covered", "non-network"
    ),
    AssetType("ai-model", 16, "AI Model", "core", ("analyst",), "covered", "non-network"),
    AssetType("api", 17, "API", "core", ("recon", "exploit"), "covered", "host"),
    AssetType(
        "aws-account", 18, "AWS Account", "core", ("cloud_hunter",), "covered", "non-network"
    ),
    AssetType(
        "azure-account", 19, "Azure Account", "core", ("cloud_hunter",), "covered", "non-network"
    ),
    AssetType(
        "blockchain", 20, "Blockchain", "core", ("contract_auditor",), "partial", "non-network"
    ),
    AssetType("dlt", 21, "DLT", "core", ("contract_auditor",), "partial", "non-network"),
    AssetType("url", 22, "URL", "web-network", ("recon", "exploit"), "covered", "host"),
    AssetType("subdomain", 23, "Subdomain", "web-network", ("recon",), "covered", "host"),
    AssetType(
        "graphql-endpoint",
        24,
        "GraphQL Endpoint",
        "web-network",
        ("exploit", "recon"),
        "covered",
        "host",
    ),
    AssetType(
        "websocket",
        25,
        "WebSocket (wss://)",
        "web-network",
        ("exploit",),
        "covered",
        "host",
        aliases=("wss", "ws"),
    ),
    AssetType("grpc", 26, "gRPC Service", "web-network", ("exploit",), "covered", "host"),
    AssetType(
        "rest-api", 27, "REST API Endpoint", "web-network", ("exploit", "recon"), "covered", "host"
    ),
    AssetType(
        "oauth-sso", 28, "OAuth / SSO Provider", "web-network", ("exploit",), "covered", "host"
    ),
    AssetType(
        "vpn-gateway",
        29,
        "VPN / Remote Access Gateway",
        "web-network",
        ("recon", "exploit", "postexploit"),
        "gap",
        "host",
    ),
    AssetType(
        "cdn-edge",
        30,
        "CDN / Edge Infrastructure",
        "web-network",
        ("exploit", "recon"),
        "partial",
        "host",
    ),
    AssetType("dns-infra", 31, "DNS Infrastructure", "web-network", ("recon",), "partial", "host"),
    AssetType(
        "gcp-account",
        32,
        "GCP Account / Project",
        "cloud-infra",
        ("cloud_hunter",),
        "covered",
        "non-network",
    ),
    AssetType(
        "google-workspace",
        33,
        "Google Workspace",
        "cloud-infra",
        ("cloud_hunter",),
        "gap",
        "non-network",
    ),
    AssetType(
        "m365-tenant",
        34,
        "Microsoft 365 / Office 365 Tenant",
        "cloud-infra",
        ("cloud_hunter",),
        "partial",
        "non-network",
    ),
    AssetType(
        "s3-bucket",
        35,
        "AWS S3 Bucket / Storage Object",
        "cloud-infra",
        ("cloud_hunter",),
        "covered",
        "host",
    ),
    AssetType(
        "azure-blob",
        36,
        "Azure Blob / Storage",
        "cloud-infra",
        ("cloud_hunter",),
        "partial",
        "host",
    ),
    AssetType(
        "docker-registry",
        37,
        "Docker Registry / Container Image",
        "cloud-infra",
        ("cloud_hunter", "reverser"),
        "partial",
        "host",
    ),
    AssetType(
        "k8s-cluster",
        38,
        "Kubernetes Cluster / API Server",
        "cloud-infra",
        ("cloud_hunter",),
        "covered",
        "host",
    ),
    AssetType(
        "cicd-pipeline", 39, "CI/CD Pipeline", "cloud-infra", ("exploit",), "covered", "non-network"
    ),
    AssetType(
        "serverless", 40, "Serverless Function", "cloud-infra", ("cloud_hunter",), "gap", "host"
    ),
    AssetType(
        "vm-image",
        41,
        "Container / VM Image (AMI, OVA, VMDK)",
        "cloud-infra",
        ("reverser", "cloud_hunter"),
        "gap",
        "non-network",
    ),
    AssetType(
        "macos-app",
        42,
        "macOS Application (.app / .dmg / .pkg)",
        "desktop-software",
        ("reverser", "postexploit"),
        "partial",
        "non-network",
    ),
    AssetType(
        "linux-binary",
        43,
        "Linux Binary / Package (.deb / .rpm / ELF)",
        "desktop-software",
        ("reverser", "postexploit"),
        "covered",
        "non-network",
        aliases=("deb", "rpm", "elf"),
    ),
    AssetType(
        "electron-app",
        44,
        "Electron / Cross-platform Desktop App",
        "desktop-software",
        ("reverser",),
        "gap",
        "non-network",
    ),
    AssetType(
        "browser-extension",
        45,
        "Browser Extension (Chrome / Firefox / Edge)",
        "desktop-software",
        ("reverser", "analyst"),
        "gap",
        "non-network",
    ),
    AssetType(
        "firmware",
        46,
        "Firmware (Router / Embedded / OT / SCADA)",
        "desktop-software",
        ("reverser",),
        "covered",
        "non-network",
    ),
    AssetType(
        "blockchain-node",
        47,
        "Blockchain Node / Client",
        "web3",
        ("contract_auditor", "recon"),
        "gap",
        "host",
    ),
    AssetType(
        "defi-dapp",
        48,
        "DeFi Protocol / dApp",
        "web3",
        ("contract_auditor",),
        "covered",
        "non-network",
    ),
    AssetType(
        "nft-token",
        49,
        "NFT / Token Contract",
        "web3",
        ("contract_auditor",),
        "partial",
        "non-network",
    ),
    AssetType(
        "bridge",
        50,
        "Bridge / Cross-chain Infrastructure",
        "web3",
        ("contract_auditor",),
        "covered",
        "non-network",
    ),
    AssetType(
        "oracle-integration",
        51,
        "Oracle Integration",
        "web3",
        ("contract_auditor",),
        "covered",
        "non-network",
    ),
    AssetType(
        "wallet",
        52,
        "Wallet (Custodial / Non-custodial)",
        "web3",
        ("contract_auditor", "reverser"),
        "gap",
        "non-network",
    ),
    AssetType(
        "crypto-library",
        53,
        "Cryptographic Library / Primitive",
        "web3",
        ("reverser", "analyst"),
        "partial",
        "non-network",
    ),
    AssetType(
        "llm-safety-classifier",
        54,
        "LLM Safety Classifier / Alignment Layer",
        "ai-ml",
        ("analyst",),
        "covered",
        "host",
    ),
    AssetType(
        "ml-weights",
        55,
        "ML Model Weights / Artifact",
        "ai-ml",
        ("analyst", "reverser"),
        "covered",
        "non-network",
    ),
    AssetType(
        "ai-inference-endpoint",
        56,
        "AI Inference Endpoint",
        "ai-ml",
        ("analyst", "exploit"),
        "partial",
        "host",
    ),
    AssetType(
        "training-pipeline",
        57,
        "Training Data Pipeline",
        "ai-ml",
        ("analyst",),
        "partial",
        "non-network",
    ),
    AssetType(
        "saml-oidc-idp",
        58,
        "SAML / OIDC Identity Provider",
        "identity-auth",
        ("exploit",),
        "covered",
        "host",
    ),
    AssetType(
        "ldap-ad",
        59,
        "SSO / LDAP / Active Directory Integration",
        "identity-auth",
        ("ad_operator",),
        "covered",
        "host",
    ),
    AssetType(
        "fido2",
        60,
        "Hardware Security Key / FIDO2 Implementation",
        "identity-auth",
        ("exploit", "analyst"),
        "gap",
        "non-network",
    ),
    AssetType(
        "ca-pki",
        61,
        "Certificate Authority (CA) / PKI Infrastructure",
        "identity-auth",
        ("ad_operator",),
        "partial",
        "host",
    ),
    AssetType(
        "asn",
        62,
        "ASN (Autonomous System Number)",
        "networking-physical",
        ("recon",),
        "partial",
        "non-network",
        aliases=("autonomous-system",),
    ),
    AssetType(
        "ics-scada",
        63,
        "OT / SCADA / ICS",
        "networking-physical",
        ("exploit",),
        "partial",
        "host",
        safety_critical=True,
    ),
    AssetType(
        "physical-facility",
        64,
        "Physical Facility / Access Control System",
        "networking-physical",
        (),
        "gap",
        "non-network",
        gated_by_conops="physical_engagement",
    ),
    AssetType(
        "network-device",
        65,
        "Network Device (Switch / Firewall / Router)",
        "networking-physical",
        ("recon", "postexploit", "ad_operator"),
        "partial",
        "host",
    ),
    AssetType(
        "satellite-rf",
        66,
        "Satellite / Radio / RF Interface",
        "networking-physical",
        ("wireless_operator",),
        "partial",
        "non-network",
        safety_critical=True,
    ),
    AssetType(
        "database-exposed",
        67,
        "Database (Exposed Instance)",
        "data-storage",
        ("recon", "exploit"),
        "partial",
        "host",
    ),
    AssetType(
        "data-warehouse",
        68,
        "Data Warehouse / Analytics Platform",
        "data-storage",
        ("cloud_hunter", "analyst"),
        "gap",
        "host",
    ),
    AssetType(
        "secrets-vault",
        69,
        "Secrets Manager / Vault",
        "data-storage",
        ("cloud_hunter",),
        "partial",
        "host",
    ),
    AssetType(
        "backup-snapshot",
        70,
        "Backup / Snapshot Storage",
        "data-storage",
        ("cloud_hunter",),
        "gap",
        "host",
    ),
    AssetType(
        "email-infra",
        71,
        "Email Infrastructure (MX / DMARC / SMTP)",
        "comms-integrations",
        ("recon", "phisher"),
        "partial",
        "host",
    ),
    AssetType(
        "chat-integration",
        72,
        "Chat / Messaging Platform Integration",
        "comms-integrations",
        ("exploit", "analyst"),
        "gap",
        "non-network",
    ),
    AssetType(
        "sdk-library",
        73,
        "SDK / Client Library (npm / PyPI / crates.io)",
        "comms-integrations",
        ("exploit", "analyst"),
        "covered",
        "non-network",
    ),
    AssetType("webhook", 74, "Webhook Endpoint", "comms-integrations", ("exploit",), "gap", "host"),
    AssetType(
        "third-party-oauth",
        75,
        "Third-party Integration / Plugin / OAuth App",
        "comms-integrations",
        ("exploit", "cloud_hunter"),
        "partial",
        "non-network",
    ),
)

_BY_ID: dict[str, AssetType] = {a.id: a for a in ASSET_TYPES}
_BY_NUMBER: dict[int, AssetType] = {a.number: a for a in ASSET_TYPES}
# alias → id; consumed by normalize_type() (added in Task 2)
_BY_ALIAS: dict[str, str] = {alias.lower(): a.id for a in ASSET_TYPES for alias in a.aliases}


def all() -> tuple[AssetType, ...]:  # noqa: A001
    return ASSET_TYPES


def get(asset_id: str) -> AssetType | None:
    return _BY_ID.get(asset_id)


def by_number(n: int) -> AssetType | None:
    return _BY_NUMBER.get(n)


def by_category(category: str) -> tuple[AssetType, ...]:
    return tuple(a for a in ASSET_TYPES if a.category == category)


def coverage_summary() -> dict[str, int]:
    counts = Counter(a.coverage for a in ASSET_TYPES)
    return {k: counts.get(k, 0) for k in VALID_COVERAGE}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


_BY_LABEL_SLUG: dict[str, str] = {_slug(a.label): a.id for a in ASSET_TYPES}

_HEX40 = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ASN = re.compile(r"^as\d+$", re.IGNORECASE)
_DOMAIN = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
_STORE_HOST_IDS: tuple[tuple[str, str], ...] = (
    ("apps.apple.com", "ios-appstore"),
    ("itunes.apple.com", "ios-appstore"),
    ("testflight.apple.com", "ios-testflight"),
    ("play.google.com", "android-playstore"),
    ("apps.microsoft.com", "windows-msstore"),
)
_EXT_IDS: tuple[tuple[str, str], ...] = (
    (".apk", "android-apk"),
    (".ipa", "ios-ipa"),
    (".deb", "linux-binary"),
    (".rpm", "linux-binary"),
    (".dmg", "macos-app"),
    (".pkg", "macos-app"),
    (".exe", "executable"),
    (".dll", "executable"),
)


def normalize_type(value: str) -> str | None:
    """Normalise a free-form type string to a canonical asset-type id.

    Lookup order: exact id → alias → slugified id → slugified label.
    Returns ``None`` if nothing matches (callers keep the raw value).
    """
    if not value:
        return None
    key = value.strip().lower()
    if key in _BY_ID:
        return key
    if key in _BY_ALIAS:
        return _BY_ALIAS[key]
    slug = _slug(value)
    if slug in _BY_ID:
        return slug
    return _BY_LABEL_SLUG.get(slug)


def classify(target: str | None, hint: str | None = None) -> AssetType | None:
    """Infer the AssetType for a target string.

    ``hint`` is tried first via ``normalize_type``; a resolving hint wins.
    Otherwise the heuristic chain tries, in order: contract address, ASN,
    WebSocket URL, wildcard, CIDR, IP address, app-store URL, file
    extension, generic URL, bare domain, then literal type-name lookup —
    falling back to ``other-asset`` when nothing matches.
    """
    if hint:
        hid = normalize_type(hint)
        if hid:
            return _BY_ID[hid]

    raw = (target or "").strip()
    if not raw:
        return _BY_ID["other-asset"]

    low = raw.lower()

    if _HEX40.match(raw):
        return _BY_ID["smart-contract"]
    if _ASN.match(raw):
        return _BY_ID["asn"]
    if low.startswith("wss://") or low.startswith("ws://"):
        return _BY_ID["websocket"]
    if raw.startswith("*."):
        return _BY_ID["wildcard"]
    if "/" in raw:
        try:
            ipaddress.ip_network(raw, strict=False)
            return _BY_ID["cidr"]
        except ValueError:
            pass
    try:
        ipaddress.ip_address(raw)
        return _BY_ID["ip-address"]
    except ValueError:
        pass
    for host, aid in _STORE_HOST_IDS:
        if host in low:
            return _BY_ID[aid]
    for ext, aid in _EXT_IDS:
        if low.endswith(ext):
            return _BY_ID[aid]
    if "://" in low:
        return _BY_ID["url"]
    if _DOMAIN.match(low):
        return _BY_ID["domain"]

    nid = normalize_type(raw)
    if nid:
        return _BY_ID[nid]
    return _BY_ID["other-asset"]
