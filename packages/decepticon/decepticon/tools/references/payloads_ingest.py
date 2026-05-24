"""PayloadsAllTheThings ingestion.

Walks a cached clone of ``swisskyrepo/PayloadsAllTheThings`` and yields
``PayloadBundle`` rows derived from the ``Intruder/*.txt`` wordlists
and the top-level ``README.md`` of each vuln class.

The indexer is **lazy + optional**: if the cache is absent, it returns
an empty list. Callers merge the result on top of the committed
``BUNDLED_PAYLOADS`` set so the agent always has something to work with
even when the clone is missing.

Directory layout (upstream):

    PayloadsAllTheThings/
      SQL Injection/
        README.md
        Intruder/
          payloads.txt
          mysql-injection.txt
          ...
      SSRF/
        README.md
        Intruder/*.txt
      ...

The folder name is normalised into the Decepticon ``vuln_class`` slug
via ``_DIR_TO_CLASS``. Unknown folders are mapped to a lowercase-hyphen
slug so new classes surface automatically with a stable label.
"""

from __future__ import annotations

import re
from pathlib import Path

from decepticon.tools.references.fetch import cache_path
from decepticon.tools.references.payloads import BUNDLED_PAYLOADS, PayloadBundle

REPO_SLUG = "payloads-all-the-things"

# Canonical Decepticon vuln_class labels used by the rest of the
# codebase (research/cve.py, skills/analyst/*, etc.). Keep this map in
# sync with those labels.
_DIR_TO_CLASS: dict[str, str] = {
    "sql injection": "sqli",
    "nosql injection": "nosqli",
    "ldap injection": "ldapi",
    "server side request forgery": "ssrf",
    "ssrf": "ssrf",
    "xss injection": "xss",
    "xss": "xss",
    "xxe injection": "xxe",
    "xxe": "xxe",
    "server side template injection": "ssti",
    "ssti": "ssti",
    "command injection": "cmdi",
    "cmd injection": "cmdi",
    "code injection": "code-injection",
    "upload insecure files": "file-upload",
    "file inclusion": "lfi",
    "directory traversal": "lfi",
    "insecure direct object references": "idor",
    "insecure deserialization": "deser",
    "json web token": "jwt",
    "oauth": "oauth",
    "graphql injection": "graphql",
    "graphql": "graphql",
    "prototype pollution": "proto-pollution",
    "prompt injection": "prompt-injection",
    "open redirect": "open-redirect",
    "csrf injection": "csrf",
    "csrf": "csrf",
    "crlf injection": "crlf",
    "header injection": "header-injection",
    "race condition": "race",
    "request smuggling": "smuggling",
    "web cache deception": "cache-deception",
    "hidden parameters": "hidden-params",
    "cors misconfiguration": "cors",
    "account takeover": "ato",
    "2fa bypass": "2fa-bypass",
    "business logic errors": "biz-logic",
    "cvs injection": "csv-injection",
    "csv injection": "csv-injection",
    "dependency confusion": "dep-confusion",
    "ssl tls issues": "tls",
    "subdomain takeover": "subdomain-takeover",
    "type juggling": "type-juggling",
    "xpath injection": "xpath",
    "zip slip": "zip-slip",
    "mail injection": "smtp-injection",
    "saml injection": "saml",
    "regular expression": "redos",
    "denial of service": "dos",
}

# Folders that ship payloads but not as a single vuln class (tooling,
# methodology, etc.). We skip these entirely.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "methodology and resources",
        "api key leaks",
        "_template_vuln",
        ".github",
        ".git",
        "images",
        "files",
    }
)

_NON_PAYLOAD_LINE = re.compile(r"^\s*(#|//|<!--)")


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return s.strip("-")


def classify_dir(dir_name: str) -> str | None:
    """Map an upstream folder name to a Decepticon vuln_class slug.

    Returns ``None`` when the folder is explicitly skipped.
    """
    key = dir_name.lower().strip()
    if key in _SKIP_DIRS:
        return None
    if key in _DIR_TO_CLASS:
        return _DIR_TO_CLASS[key]
    # Fallback — slugify so downstream code still sees a stable label.
    return _slugify(key)


def _read_intruder_file(path: Path, vuln_class: str, limit: int) -> list[PayloadBundle]:
    """Read a single ``Intruder/<name>.txt`` file into PayloadBundle rows."""
    out: list[PayloadBundle] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    file_label = path.stem.replace("_", " ").replace("-", " ")
    for raw in lines:
        line = raw.strip()
        if not line or _NON_PAYLOAD_LINE.match(line):
            continue
        if len(line) > 400:
            # Huge lines are usually encoded blobs — skip
            continue
        out.append(
            PayloadBundle(
                vuln_class=vuln_class,
                title=f"{file_label} — {line[:60]}" if len(line) > 60 else f"{file_label}",
                payload=line,
                notes=f"Ingested from Intruder/{path.name}",
                source="PayloadsAllTheThings",
            )
        )
        if len(out) >= limit:
            break
    return out


def iter_ingested_payloads(
    *,
    root: Path | None = None,
    per_file_limit: int = 40,
    per_class_limit: int = 200,
) -> list[PayloadBundle]:
    """Walk the cached PayloadsAllTheThings repo and yield PayloadBundle rows.

    Returns an empty list when the cache is absent — callers must
    always fall back to ``BUNDLED_PAYLOADS``.
    """
    repo = cache_path(REPO_SLUG, root=root)
    if not repo.exists():
        return []
    rows: list[PayloadBundle] = []
    for child in sorted(repo.iterdir()):
        if not child.is_dir():
            continue
        vuln_class = classify_dir(child.name)
        if vuln_class is None:
            continue
        intruder = child / "Intruder"
        class_count = 0
        if intruder.is_dir():
            for txt in sorted(intruder.glob("*.txt")):
                new_rows = _read_intruder_file(txt, vuln_class, per_file_limit)
                take = min(len(new_rows), max(0, per_class_limit - class_count))
                rows.extend(new_rows[:take])
                class_count += take
                if class_count >= per_class_limit:
                    break
        readme = child / "README.md"
        if readme.is_file() and class_count < per_class_limit:
            # Single marker row pointing at the methodology README
            rows.append(
                PayloadBundle(
                    vuln_class=vuln_class,
                    title=f"{child.name} — methodology",
                    payload=str(readme.relative_to(repo)),
                    notes="See full README.md chapter in the cached repo",
                    source="PayloadsAllTheThings",
                )
            )
    return rows


def _compute_merged(root: Path | None) -> tuple[PayloadBundle, ...]:
    seen: set[tuple[str, str]] = set()
    out: list[PayloadBundle] = []
    for bundle in BUNDLED_PAYLOADS:
        key = (bundle.vuln_class, bundle.payload)
        if key in seen:
            continue
        seen.add(key)
        out.append(bundle)
    for bundle in iter_ingested_payloads(root=root):
        key = (bundle.vuln_class, bundle.payload)
        if key in seen:
            continue
        seen.add(key)
        out.append(bundle)
    return tuple(out)


# Process-level cache keyed by the resolved PayloadsAllTheThings cache
# path + directory mtime. Walking the repo on every call dominated
# ``payload_search`` latency on populated systems.
_merged_cache: dict[Path, tuple[float, tuple[PayloadBundle, ...]]] = {}


def merged_payloads(*, root: Path | None = None) -> tuple[PayloadBundle, ...]:
    """Return ``BUNDLED_PAYLOADS`` plus any ingested rows, deduplicated.

    The result is memoized per-process keyed by the cache root path
    and the PayloadsAllTheThings directory mtime. Re-hydrating the
    cache invalidates the memo via mtime change.
    """
    try:
        repo_path = cache_path(REPO_SLUG, root=root)
        mtime = repo_path.stat().st_mtime if repo_path.exists() else -1.0
    except OSError:
        repo_path = cache_path(REPO_SLUG, root=root)
        mtime = -1.0
    entry = _merged_cache.get(repo_path)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    payloads = _compute_merged(root)
    _merged_cache[repo_path] = (mtime, payloads)
    return payloads


def invalidate_merged_cache() -> None:
    """Drop the process-level merged_payloads cache."""
    _merged_cache.clear()


def search_merged(
    *,
    vuln_class: str | None = None,
    keyword: str | None = None,
    root: Path | None = None,
    limit: int = 200,
) -> list[PayloadBundle]:
    """Filter the merged payload set (bundled + ingested) by class/keyword."""
    results: list[PayloadBundle] = []
    needle = keyword.lower() if keyword else None
    for p in merged_payloads(root=root):
        if vuln_class and p.vuln_class.lower() != vuln_class.lower():
            continue
        if needle and needle not in (p.title + p.payload + p.notes).lower():
            continue
        results.append(p)
        if len(results) >= limit:
            break
    return results


__all__ = [
    "REPO_SLUG",
    "classify_dir",
    "iter_ingested_payloads",
    "merged_payloads",
    "search_merged",
]
