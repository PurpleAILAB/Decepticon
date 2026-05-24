"""Curated catalogue of third-party security knowledge repositories.

The catalogue is intentionally small and high-signal — every entry
earns its place because an agent will want to reach for it during
active engagement. Adding noise makes the router worse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReferenceEntry:
    slug: str
    name: str
    url: str
    category: str
    topics: tuple[str, ...]
    use_cases: tuple[str, ...]
    fetch_hint: str = "git"  # git | web | api
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "url": self.url,
            "category": self.category,
            "topics": list(self.topics),
            "use_cases": list(self.use_cases),
            "fetch_hint": self.fetch_hint,
            "description": self.description,
        }


REFERENCES: tuple[ReferenceEntry, ...] = (
    ReferenceEntry(
        slug="hackerone-reports",
        name="HackerOne Disclosed Reports",
        url="https://github.com/reddelexc/hackerone-reports",
        category="report-corpus",
        topics=(
            "bug-bounty",
            "writeups",
            "real-world",
            "triage",
            "cvss",
            "sla",
        ),
        use_cases=(
            "Look up how a similar finding was previously reported + rewarded",
            "Study target-specific disclosure patterns",
            "Calibrate severity + reward expectations by bug class",
            "Copy the proven report layout",
        ),
        description=(
            "Scraped archive of every publicly disclosed HackerOne report. "
            "Invaluable for calibrating CVSS, reward expectations, and the "
            "reporting format that triagers actually reward."
        ),
    ),
    ReferenceEntry(
        slug="payloads-all-the-things",
        name="PayloadsAllTheThings",
        url="https://github.com/swisskyrepo/PayloadsAllTheThings",
        category="payload-library",
        topics=(
            "sqli",
            "xss",
            "ssrf",
            "xxe",
            "ssti",
            "rce",
            "ldap",
            "nosql",
            "deserialization",
            "file-upload",
            "idor",
            "oauth",
            "graphql",
            "jwt",
            "smtp-injection",
        ),
        use_cases=(
            "Canonical payload sets per vuln class with bypass variants",
            "Ready-to-paste obfuscation + WAF bypass strings",
            "Cheatsheet per platform (Java/.NET/PHP/Node)",
        ),
        description=(
            "The canonical payload library for every web vuln class. "
            "Mirrored offline via BUNDLED_PAYLOADS for critical subsets."
        ),
    ),
    ReferenceEntry(
        slug="book-of-secret-knowledge",
        name="The Book of Secret Knowledge",
        url="https://github.com/trimstray/the-book-of-secret-knowledge",
        category="cheat-sheet",
        topics=(
            "shell",
            "oneliners",
            "networking",
            "recon",
            "linux",
            "dns",
            "http",
            "ssh",
            "tcpdump",
            "nmap",
        ),
        use_cases=(
            "Lookup forgotten one-liners",
            "Shell / awk / jq recipe reference",
            "Network troubleshooting commands",
            "SSH tricks + tunneling",
        ),
        description=(
            "Pentester's bookshelf — CLIs, one-liners, cheat sheets, "
            "troubleshooting recipes across networking and Linux."
        ),
    ),
    ReferenceEntry(
        slug="pentagi",
        name="PentAGI",
        url="https://github.com/vxcontrol/pentagi",
        category="reference-agent",
        topics=(
            "multi-agent",
            "pentest",
            "autonomous",
            "architecture",
        ),
        use_cases=(
            "Reference architecture for multi-agent pentest platforms",
            "Compare orchestration patterns",
            "Borrow tool idioms and prompt patterns",
        ),
        description=(
            "Competing multi-agent pentest platform — useful to compare "
            "Decepticon's orchestrator + sub-agent architecture against."
        ),
    ),
    ReferenceEntry(
        slug="pentestgpt",
        name="PentestGPT",
        url="https://github.com/GreyDGL/PentestGPT",
        category="reference-agent",
        topics=(
            "llm",
            "pentest",
            "ctf",
            "htb",
            "research",
        ),
        use_cases=(
            "Reference prompt patterns for pentest LLMs",
            "Benchmark suggestions for HTB/CTF targets",
            "Compare thought-process and task decomposition",
        ),
        description=(
            "Early academic-quality pentest LLM agent. Strong references "
            "for HTB / CTF workflow decomposition."
        ),
    ),
    ReferenceEntry(
        slug="redteam-tools",
        name="RedTeam-Tools",
        url="https://github.com/A-poc/RedTeam-Tools",
        category="tool-index",
        topics=(
            "recon",
            "initial-access",
            "privesc",
            "lateral",
            "persistence",
            "c2",
            "exfil",
        ),
        use_cases=(
            "Find the right tool for each MITRE ATT&CK phase",
            "Discover less-known red team utilities",
            "Quick mapping from capability → install command",
        ),
        description=(
            "Curated index of offensive tooling organised by kill-chain "
            "phase. Quick router from 'I need to do X' → 'use tool Y'."
        ),
    ),
    ReferenceEntry(
        slug="trickest-cve",
        name="trickest/cve",
        url="https://github.com/trickest/cve",
        category="cve-poc",
        topics=(
            "cve",
            "poc",
            "exploits",
            "n-day",
        ),
        use_cases=(
            "Look up PoC for a specific CVE ID",
            "Seed exploit development for a disclosed vulnerability",
            "Identify which CVEs have public working exploits",
        ),
        fetch_hint="git",
        description=(
            "Continuously-updated corpus of CVEs with links to public "
            "PoCs, grouped by year. Perfect companion to the NVD/EPSS "
            "lookup — NVD tells you the score, this tells you if there "
            "is actually a working PoC."
        ),
    ),
    ReferenceEntry(
        slug="penetration-testing-poc",
        name="Penetration_Testing_POC",
        url="https://github.com/Mr-xn/Penetration_Testing_POC",
        category="cve-poc",
        topics=(
            "cve",
            "poc",
            "scanner",
            "exploit",
            "tool",
        ),
        use_cases=(
            "Additional PoC mirror when trickest/cve is sparse",
            "Chinese pentest community PoC contributions",
            "Scanner plugin references",
        ),
        description=(
            "Second-opinion PoC mirror — often has exploits the English "
            "corpora miss for recently disclosed CVEs."
        ),
    ),
    ReferenceEntry(
        slug="all-about-bug-bounty",
        name="AllAboutBugBounty",
        url="https://github.com/daffainfo/AllAboutBugBounty",
        category="methodology",
        topics=(
            "bug-bounty",
            "methodology",
            "writeups",
            "idor",
            "ssrf",
            "account-takeover",
            "oauth",
            "business-logic",
        ),
        use_cases=(
            "Methodology guide per vuln class",
            "Writeup index organised by bug type",
            "Chain-building inspiration from disclosed reports",
        ),
        description=(
            "Curated per-class bug bounty methodology + writeup index. "
            "Maps cleanly to analyst hunting lanes."
        ),
    ),
    ReferenceEntry(
        slug="shannon",
        name="Shannon",
        url="https://github.com/KeygraphHQ/shannon",
        category="reference-agent",
        topics=("llm", "agent", "security", "autonomous"),
        use_cases=(
            "Reference implementation patterns from another autonomous agent",
            "Compare tool-call + memory architectures",
        ),
        description=(
            "Keygraph's autonomous security agent framework — reference "
            "for memory + tool orchestration patterns."
        ),
    ),
    ReferenceEntry(
        slug="strix",
        name="Strix",
        url="https://github.com/usestrix/strix",
        category="reference-agent",
        topics=("llm", "agent", "pentest", "autonomous", "recon"),
        use_cases=(
            "Alternative autonomous pentest agent for architecture comparison",
            "Borrow workflow ideas + tool wrappers",
        ),
        description=(
            "Usestrix's autonomous security agent — compare workflow "
            "decomposition against Decepticon's orchestrator."
        ),
    ),
    ReferenceEntry(
        slug="hexstrike-ai",
        name="HexStrike AI",
        url="https://github.com/0x4m4/hexstrike-ai",
        category="reference-agent",
        topics=("llm", "agent", "pentest", "mcp", "150-tools", "hacking"),
        use_cases=(
            "Reference for wiring LLM → 150+ security tools via MCP",
            "Study how to wrap massive tool inventories under a single agent",
            "Per-tool prompt design examples",
        ),
        description=(
            "AI-powered offensive security framework exposing 150+ "
            "security tools via MCP — reference for large tool sets."
        ),
    ),
    ReferenceEntry(
        slug="neurosploit",
        name="NeuroSploit",
        url="https://github.com/CyberSecurityUP/NeuroSploit",
        category="reference-agent",
        topics=("llm", "agent", "metasploit", "exploit", "pentest"),
        use_cases=(
            "Reference for LLM + Metasploit integration patterns",
            "Post-exploitation workflow ideas",
            "Agent prompts for MSF module selection",
        ),
        description=(
            "LLM-powered Metasploit driver — reference for MSF module "
            "selection prompting and exploitation workflow patterns."
        ),
    ),
    ReferenceEntry(
        slug="excalibur",
        name="Excalibur",
        url="https://anonymous.4open.science/r/Excalibur-FA7D/README.md",
        category="research",
        topics=("llm", "agent", "academic", "pentest", "research", "benchmark"),
        use_cases=(
            "Academic reference implementation — compare methodology",
            "Benchmark design for LLM-driven pentest tasks",
            "Experimental methodology for autonomous security work",
        ),
        fetch_hint="web",
        description=(
            "Anonymous double-blind academic artifact for an LLM pentest "
            "agent — reference for benchmark design and methodology."
        ),
    ),
)


# ── Query helpers ───────────────────────────────────────────────────────


def references_by_category(category: str) -> list[ReferenceEntry]:
    """Return entries matching the given category slug."""
    return [r for r in REFERENCES if r.category == category]


def references_for_topic(topic: str) -> list[ReferenceEntry]:
    """Return entries whose topic tuple contains ``topic`` (case-insensitive)."""
    needle = topic.lower()
    return [
        r for r in REFERENCES if any(needle == t.lower() or needle in t.lower() for t in r.topics)
    ]


def suggest_for_finding(
    vuln_class: str | None = None,
    goal: str | None = None,
) -> list[ReferenceEntry]:
    """Suggest the best references for a given vuln class / engagement goal.

    Heuristic: match vuln class against topics, then add methodology
    + payload sources always.
    """
    picks: list[ReferenceEntry] = []
    seen: set[str] = set()

    def _add(entries: list[ReferenceEntry]) -> None:
        for e in entries:
            if e.slug not in seen:
                seen.add(e.slug)
                picks.append(e)

    if vuln_class:
        _add(references_for_topic(vuln_class))
    if goal:
        _add(references_for_topic(goal))
    # Always include the canonical payload + methodology libraries
    _add(references_by_category("payload-library"))
    _add(references_by_category("methodology"))
    _add(references_by_category("report-corpus"))
    return picks
