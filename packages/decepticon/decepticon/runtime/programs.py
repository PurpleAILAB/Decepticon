"""Allowlisted bash-program capture for engagement analytics.

The event log's arg redaction correctly strips command strings, but that
also erased the answer to a question every retrospective asks: "was the
security arsenal used, or was everything hand-rolled curl/python?" The
recovery is an ALLOWLIST, not a parse: only basenames in this fixed set are
ever written, so a command can never smuggle a target, path, or secret into
``events.jsonl``. The set deliberately includes the generic utilities —
a ``curl``/``python3``-heavy log with zero dedicated tools is exactly the
under-use signal the retrospective measures.

Neutral home shared by the capture side
(:mod:`decepticon.middleware.event_logging`) and the analysis side
(:mod:`decepticon.tools.research.retrospective`) so the two never drift
apart — importing the middleware package from a tool module would pull in
the agent registry, and duplicating the lists would silently fork them.
"""

from __future__ import annotations

import re
from typing import Any

# Dedicated offensive / assessment tooling (Kali arsenal & friends).
SECURITY_PROGRAMS: frozenset[str] = frozenset(
    {
        # recon / enumeration
        "amass",
        "subfinder",
        "findomain",
        "assetfinder",
        "dnsx",
        "dnsrecon",
        "dnsenum",
        "theharvester",
        "shodan",
        "censys",
        "waybackurls",
        "gau",
        "waymore",
        "arjun",
        "paramspider",
        "hakrawler",
        "katana",
        # port & service scanning
        "nmap",
        "masscan",
        "rustscan",
        "naabu",
        "zmap",
        # web fuzzing / scanning
        "ffuf",
        "gobuster",
        "feroxbuster",
        "dirb",
        "dirsearch",
        "wfuzz",
        "nikto",
        "nuclei",
        "wpscan",
        "httpx",
        "gowitness",
        "eyewitness",
        # vuln-specific
        "sqlmap",
        "dalfox",
        "commix",
        "tplmap",
        "xsstrike",
        "jwt_tool",
        # credentials / cracking
        "hydra",
        "medusa",
        "ncrack",
        "john",
        "hashcat",
        "kerbrute",
        # SMB / AD
        "enum4linux",
        "enum4linux-ng",
        "smbmap",
        "crackmapexec",
        "netexec",
        "nxc",
        "responder",
        "mitm6",
        "certipy",
        "bloodhound",
        "bloodhound-python",
        "secretsdump.py",
        "psexec.py",
        "wmiexec.py",
        "smbexec.py",
        "getnpusers.py",
        "getuserspns.py",
        # exploitation frameworks
        "msfconsole",
        "msfvenom",
        "searchsploit",
        "sliver",
        "sliver-client",
        # TLS
        "testssl.sh",
        "sslscan",
        "sslyze",
        "tlsx",
        # secrets / supply chain
        "gitleaks",
        "trufflehog",
        "trivy",
        "semgrep",
        "grype",
        "syft",
        # cloud
        "pacu",
        "scout",
        "scoutsuite",
        "prowler",
        "cloud_enum",
        "s3scanner",
        # reversing / firmware
        "binwalk",
        "ghidra",
        "radare2",
        "r2",
        "gdb",
        "objdump",
        "checksec",
    }
)

# Web content-discovery subset of SECURITY_PROGRAMS — the class whose
# absence on an HTTP-heavy engagement is the clearest under-use signal.
WEB_SCANNER_PROGRAMS: frozenset[str] = frozenset(
    {
        "ffuf",
        "gobuster",
        "feroxbuster",
        "dirb",
        "dirsearch",
        "wfuzz",
        "nikto",
        "nuclei",
        "katana",
        "hakrawler",
        "wpscan",
    }
)

# Generic utilities — captured because their EXCLUSIVE presence is the
# hand-rolled-scripts signal.
GENERIC_PROGRAMS: frozenset[str] = frozenset(
    {
        "curl",
        "wget",
        "httpie",
        "http",
        "python3",
        "python",
        "bash",
        "sh",
        "nc",
        "ncat",
        "socat",
        "openssl",
        "dig",
        "host",
        "nslookup",
        "whois",
        "jq",
        "git",
        "ssh",
        "scp",
    }
)

KNOWN_PROGRAMS: frozenset[str] = SECURITY_PROGRAMS | GENERIC_PROGRAMS

_PROG_TOKEN_SPLIT = re.compile(r"[\s|;&<>(){}\[\]'\"$`\\]+")

#: Cap on programs recorded per bash call — bounds event size.
PROG_CAP = 12


def extract_programs(command: Any) -> list[str]:
    """Return allowlisted program basenames invoked by a bash command.

    Order-preserving, deduplicated, capped at ``PROG_CAP``. Anything not in
    ``KNOWN_PROGRAMS`` is dropped — including paths, script names, and
    arguments — so no engagement-identifying content can reach the log
    through this channel.
    """
    if not isinstance(command, str) or not command:
        return []
    seen: list[str] = []
    for token in _PROG_TOKEN_SPLIT.split(command):
        if not token:
            continue
        base = token.rsplit("/", 1)[-1].lower()
        if base in KNOWN_PROGRAMS and base not in seen:
            seen.append(base)
            if len(seen) >= PROG_CAP:
                break
    return seen
