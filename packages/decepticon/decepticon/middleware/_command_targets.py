"""Extract target hosts/IPs from common red-team commands.

Purpose: feed the RoE evaluator. Given a shell command issued via the
``bash`` tool, return the set of targets the command would reach. This
is best-effort - the parser handles ~30 tools used by the kill-chain
specialists and falls back to a generic URL/IP scrape otherwise.

This module deliberately uses regex extraction, not full shell
parsing, because:

  1. Shell parsing is fragile - any operator overload (`<()`, here-docs,
     environment-variable substitution) breaks shlex.
  2. The RoE evaluator runs on the *attempted* command. Extracting
     "this command intends to reach 10.0.0.5" from the literal command
     text is fine; we are not running the command to learn its
     resolved targets.
  3. False positives (more targets than the command would actually
     reach) are safer than false negatives. The RoE evaluator can
     refuse on a spurious target; the operator overrides.

The fallback (``_extract_generic``) catches IP literals, CIDR-like
``x.x.x.x/yy``, hostnames after ``://``, and bare hostnames after
common verbs (``curl``, ``ssh``). The result is the union of
tool-specific extraction + the generic scrape.

Fail-closed token scrape
------------------------
The generic scrape only recognises a host after ``://`` or a hardcoded
verb. A network tool *not* on that verb list, invoked with a bare
hostname (``ping evil.com``, ``nc evil.com 443``, ``./exploit
evil.com``), used to extract ZERO targets — leaving the RoE scope gate
nothing to evaluate, so it allowed the command by default. For an
allowlist enforcer that is the unsafe direction (a fail-OPEN bypass).
``_extract_token_hosts`` closes that class: when no tool-specific
extractor matched, every shell token that validates as a host / IP /
CIDR is treated as a candidate target unless it is a known non-target.
The failure mode flips from "missed target → allowed" to "spurious
target → refused (operator-overridable)", which matches the allowlist
posture the RoE evaluator already assumes.
"""

from __future__ import annotations

import ipaddress
import re
import shlex
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CIDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b")
# Capture the whole authority (up to the path/query/fragment/whitespace), NOT
# just the leading ``[^\s/:]+`` slice. The old slice stopped at the first ``:``
# and never crossed ``@``, so ``scheme://in-scope@evil.com/`` yielded the
# in-scope userinfo (or nothing) instead of the real connect host ``evil.com``
# — a scope-enforcement bypass. ``_host_from_authority`` then RFC-3986-splits
# off userinfo + port and de-brackets IPv6 literals.
_URL_AUTHORITY_RE = re.compile(
    r"\b(?:https?|ftp|file|smb|nfs|ssh|rdp|ldaps?)://([^\s/\\?#]+)", re.IGNORECASE
)
# Threshold above which a bare decimal host is treated as a packed IPv4 integer
# (e.g. ``http://2852039166/`` == 169.254.169.254) rather than a port/number.
# 2**24 keeps small integers (ports, counts) from being mangled into IPs.
_PACKED_IPV4_MIN = 1 << 24
# Non-canonical but resolver-valid dotted IPv4 forms that Python's ``ipaddress``
# rejects yet libc ``inet_aton`` (and thus curl/wget/nc on the engagement host)
# still routes to the same address: octal-padded (``0251.0376.0251.0376``),
# dotted-hex (``0xa9.0xfe.0xa9.0xfe``), and short-octet (``127.1``) encodings.
# Matched so ``_canon_host`` can normalize them to a dotted quad and a
# numeric-encoding trick can't dodge an IP deny rule. Requires >= 2 dot-separated
# numeric parts; the dotless single-integer form is handled separately above.
_LOOSE_DOTTED_IPV4_RE = re.compile(
    r"(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+)){1,3}", re.IGNORECASE
)
_HOSTNAME_AFTER_VERB_RE = re.compile(
    r"\b(?:curl|wget|httpx|nmap|masscan|rustscan|ssh|scp|sftp|rsync|"
    r"smbclient|smbmap|crackmapexec|nxc|netexec|nikto|sqlmap|hydra|ffuf|"
    r"gobuster|dirsearch|katana|nuclei|whatweb|wpscan|sslyze|testssl|"
    r"dig|nslookup|host|whois|amass|subfinder|dnsx|kerbrute|impacket-"
    r"[A-Za-z0-9_-]+|GetUserSPNs\.py|GetNPUsers\.py|secretsdump\.py|"
    r"psexec\.py|wmiexec\.py|smbexec\.py|atexec\.py)"
    r"\b[^\n]*?\s+"
    r"([A-Za-z0-9][A-Za-z0-9._:-]+[A-Za-z0-9])",
    re.IGNORECASE,
)


# Final labels that mark a token as a local-file argument, never a network
# target, so RoE ENFORCE mode does not refuse legitimate commands whose option
# values (``-i key.pem``, ``-oA scan.txt``) look hostname-shaped.
#
# SECURITY: an entry here is only safe if it is NOT also a delegated DNS TLD.
# Real TLDs (``.sh`` ``.md`` ``.py`` ``.pl`` ``.pub`` ``.zip`` …) were removed:
# leaving them in silently dropped genuine hosts such as ``evil.zip`` from RoE
# scope enforcement. Over-extracting a spurious target (operator-overridable)
# is safer than dropping a real one.
_NON_TARGET_EXTENSIONS: frozenset[str] = frozenset(
    {
        "pem",
        "key",
        "crt",
        "csr",
        "cer",
        "der",
        "p12",
        "pfx",
        "txt",
        "log",
        "json",
        "yaml",
        "yml",
        "conf",
        "cfg",
        "ini",
        "toml",
        "csv",
        "tsv",
        "xml",
        "html",
        "htm",
        "rst",
        "rb",
        "ps1",
        "bat",
        "pcap",
        "pcapng",
        "bin",
        "out",
        "tmp",
        "bak",
        "lst",
        "db",
        "sqlite",
        "sqlite3",
        "gz",
        "tar",
        "tgz",
        "7z",
        "rar",
    }
)


def _is_valid_target(token: str) -> bool:
    if not token or len(token) < 3 or len(token) > 253:
        return False
    if token.startswith("-") or token.startswith("/"):
        return False
    try:
        ipaddress.ip_network(token, strict=False)
        return True
    except ValueError:
        # Not a valid IP/CIDR literal - fall through to hostname validation
        # below. Bare strings like 'example.com' are legitimate targets.
        pass
    if "." not in token:
        return False
    if any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:"
        for ch in token
    ):
        return False
    if token.rsplit(".", 1)[-1].lower() in _NON_TARGET_EXTENSIONS:
        # A token whose last label is a common file extension is a local file
        # argument (e.g. ``-i key.pem``, ``-oA scan.txt``), not a network
        # target — exclude it so RoE ENFORCE mode does not refuse the command.
        return False
    return True


def _canon_host(token: str) -> str:
    """Canonicalize a host token so scope matching is encoding-independent.

    De-brackets IPv6 literals, normalizes packed integer/hex IPv4 encodings to
    dotted-quad, and compresses valid IP literals to their canonical string.
    Hostnames pass through lower-cased. This closes the IMDS/forbidden-dest
    bypass where ``http://2852039166/`` or ``http://0xa9fea9fe/`` reach
    169.254.169.254 without matching a dotted-quad deny rule. The same applies
    to the *dotted* non-canonical forms that ``ipaddress`` rejects but the
    platform resolver still accepts — octal-padded (``0251.0376.0251.0376``),
    dotted-hex (``0xa9.0xfe.0xa9.0xfe``), and short-octet (``127.1``).
    """
    raw = token.strip()
    bare = raw[1:-1] if raw.startswith("[") and raw.endswith("]") else raw
    if not bare:
        return raw.lower()
    if ":" not in bare and "." not in bare:
        try:
            as_int = int(bare, 16) if bare.lower().startswith("0x") else int(bare)
        except ValueError:
            return bare.lower()
        if bare.lower().startswith("0x") or as_int >= _PACKED_IPV4_MIN:
            try:
                return str(ipaddress.ip_address(as_int))
            except ValueError:
                return bare.lower()
        return bare.lower()
    try:
        return str(ipaddress.ip_address(bare))
    except ValueError:
        # ``ipaddress`` only accepts canonical dotted-decimal. Non-canonical
        # dotted encodings that the platform resolver still routes to the same
        # address (octal-padded, dotted-hex, short-octet) would otherwise pass
        # through verbatim and dodge an IP deny rule. Canonicalize them via the
        # same ``inet_aton`` the offensive tools use on the engagement host.
        if _LOOSE_DOTTED_IPV4_RE.fullmatch(bare):
            try:
                return socket.inet_ntoa(socket.inet_aton(bare))
            except OSError:
                pass
        return bare.lower()


def _host_from_authority(authority: str) -> str | None:
    """Return the real connect host from a URL authority, RFC-3986-correctly.

    Drops userinfo (everything through the last ``@``) and the port, and
    de-brackets IPv6 literals — so an ``in-scope@evil.com`` decoy can't mask
    the true host. Returns None when no host is present.
    """
    try:
        host = urlsplit("//" + authority).hostname
    except ValueError:
        return None
    return host or None


def _extract_generic(command: str) -> set[str]:
    found: set[str] = set()
    found.update(_IP_RE.findall(command))
    for cidr in _CIDR_RE.findall(command):
        found.add(cidr)
    for authority in _URL_AUTHORITY_RE.findall(command):
        host = _host_from_authority(authority)
        if host:
            found.add(host)
    for m in _HOSTNAME_AFTER_VERB_RE.finditer(command):
        candidate = m.group(1).rstrip(":,;\"'").lstrip("@")
        if candidate.startswith("http"):
            continue
        if ":" in candidate and not _looks_ipv6(candidate):
            # A compound option value (e.g. ``--resolve host:port:ip``) is
            # captured as one token; split on ``:`` so each piece is validated
            # independently instead of emitting a junk ``host:port:ip`` target.
            found.update(candidate.split(":"))
        else:
            found.add(candidate)
    return {c for t in found if (c := _canon_host(t)) and _is_valid_target(c)}


def _extract_nmap_targets(command: str) -> set[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return set()
    targets: set[str] = set()
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok in {"nmap", "masscan", "rustscan", "naabu", "sudo"}:
            continue
        if tok.startswith("-"):
            if tok in {"-iL", "--input-file", "-o", "-oA", "-oN", "-oG", "-oX", "-p", "--script"}:
                skip_next = True
            continue
        if _is_valid_target(tok):
            targets.add(tok)
    return targets


def _extract_ssh_targets(command: str) -> set[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return set()
    if not tokens or tokens[0] not in {"ssh", "scp", "sftp"}:
        return set()
    targets: set[str] = set()
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        if "@" in tok:
            tok = tok.split("@", 1)[1]
        if ":" in tok and not _looks_ipv6(tok):
            tok = tok.split(":", 1)[0]
        if _is_valid_target(tok):
            targets.add(tok)
    return targets


def _looks_ipv6(token: str) -> bool:
    try:
        ipaddress.IPv6Address(token.split("/", 1)[0])
        return True
    except ipaddress.AddressValueError:
        return False


def _is_ip_network(token: str) -> bool:
    try:
        ipaddress.ip_network(token, strict=False)
        return True
    except ValueError:
        return False


def _host_candidates(token: str) -> list[str]:
    """Split one shell token into the host-shaped pieces worth validating.

    Strips a trailing path (``evil.com/admin`` → ``evil.com``) while
    preserving CIDR literals (``10.0.0.0/24`` validates as a network, so
    it is left whole), and splits ``host:port`` / ``--resolve
    host:port:ip`` compounds on ``:`` so each piece is checked on its own
    rather than emitting a junk ``host:port`` target. IPv6 literals keep
    their colons.
    """
    candidates = [token]
    if "/" in token and not _is_ip_network(token):
        candidates.append(token.split("/", 1)[0])
    pieces: list[str] = []
    for cand in candidates:
        if ":" in cand and not _looks_ipv6(cand):
            pieces.extend(cand.split(":"))
        else:
            pieces.append(cand)
    return pieces


def _extract_token_hosts(command: str) -> set[str]:
    """Verb-agnostic, fail-closed scrape of host/IP/CIDR-shaped tokens.

    The legacy generic extractor only recognised a host argument when it
    followed ``scheme://`` or one of ~30 hardcoded verbs. Any network
    tool *not* on that list, invoked with a bare hostname (``ping
    evil.com``, ``nc evil.com 443``, ``./exploit evil.com``), extracted
    zero targets — so the RoE scope gate had nothing to evaluate and
    allowed the command by default. That is a fail-OPEN bypass of an
    allowlist enforcer.

    This fallback inverts the default: every shell token that validates
    as a host / IP / CIDR is a candidate target unless it is a known
    non-target (flag, absolute path, file-extension argument — all
    rejected by ``_is_valid_target``). It runs only when no precise
    tool-specific extractor matched, so the engineered option-value
    exclusions for nmap / ssh / impacket are preserved.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        # Malformed quoting still must not hide a host — fall back to a
        # whitespace split rather than returning nothing (fail-closed).
        tokens = command.split()
    found: set[str] = set()
    for tok in tokens:
        if not tok or tok.startswith("-"):
            continue
        if "@" in tok:  # strip userinfo: user@host / cred@host → host
            tok = tok.rsplit("@", 1)[1]
        for piece in _host_candidates(tok):
            canon = _canon_host(piece)
            if canon and _is_valid_target(canon):
                found.add(canon)
    return found


def _extract_impacket_targets(command: str) -> set[str]:
    targets: set[str] = set()
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return set()
    for tok in tokens:
        if "@" in tok:
            target = tok.split("@", 1)[1].split(":", 1)[0]
            if _is_valid_target(target):
                targets.add(target)
    targets.update(_IP_RE.findall(command))
    return targets


_TOOL_EXTRACTORS: tuple[tuple[re.Pattern[str], Callable[[str], set[str]]], ...] = (
    (
        re.compile(r"^\s*(?:sudo\s+)?(?:nmap|masscan|rustscan|naabu)\b", re.IGNORECASE),
        _extract_nmap_targets,
    ),
    (re.compile(r"^\s*(?:ssh|scp|sftp)\b", re.IGNORECASE), _extract_ssh_targets),
    (
        re.compile(
            r"^\s*(?:impacket-[A-Za-z0-9_-]+|GetUserSPNs|GetNPUsers|secretsdump|psexec|wmiexec)",
            re.IGNORECASE,
        ),
        _extract_impacket_targets,
    ),
)


def extract_targets(command: str) -> set[str]:
    """Return every host/IP/CIDR the command appears to target.

    The result is the UNION of:

      * the tool-specific extractor (if the command's leading token
        matches a known tool — nmap / ssh / impacket), which precisely
        skips option *values* (``-oA out.txt``, ``-i key.pem``);
      * the generic scrape (URLs, IP literals, CIDRs, hostnames after
        recognised verbs); and
      * a verb-agnostic token scrape (``_extract_token_hosts``) that
        runs ONLY when no tool-specific extractor matched — this is the
        fail-closed fallback that surfaces bare-hostname targets on
        tools the parser has never seen (``ping``/``nc``/``./exploit``).

    Returns an empty set when the command is empty or the parsers
    can't find anything (e.g. ``ls -la /tmp`` legitimately has no
    network targets).
    """
    if not command or not command.strip():
        return set()
    targets: set[str] = set()
    matched_tool = False
    for pattern, extractor in _TOOL_EXTRACTORS:
        if pattern.match(command):
            matched_tool = True
            try:
                targets.update(extractor(command))
            except Exception:
                # Tool-specific extractors fail soft. If e.g. impacket's
                # credentials-target parser hits a malformed input we fall
                # back to the generic IP/URL scraper below rather than
                # raising into the middleware hot path.
                pass
            break
    targets.update(_extract_generic(command))
    if not matched_tool:
        # No precise extractor claimed this command, so its option-value
        # exclusions don't apply — run the fail-closed token scan to
        # surface bare-hostname targets the generic verb list misses.
        targets.update(_extract_token_hosts(command))
    return targets
