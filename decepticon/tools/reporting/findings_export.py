"""Strix-style findings export pack.

Writes one self-contained directory per finding under
``<engagement_root>/findings/<vuln-slug>/`` containing:

::

    findings/<vuln-slug>/
      ├── README.md          — title + severity + summary (top of triage)
      ├── repro.md           — step-by-step reproduction
      ├── poc.sh             — executable proof-of-concept (or .py / .txt)
      ├── manifest.json      — metadata: id, severity, cvss, MITRE, refs
      └── evidence/          — request/response captures, screenshots, logs

The pack is portable: the receiving team can rerun the PoC locally
without needing access to the engagement's Neo4j store. This mirrors
Strix's ``strix_runs/<run-name>`` artifact directory but slotted into
Decepticon's existing ``engagements/<id>/`` layout.

Pure stdlib + Pydantic — no Neo4j or backend dependency. The thin
LangChain ``@tool`` wrapper in :mod:`decepticon.tools.reporting.tools`
loads the finding from the graph and hands its dict shape here.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LEN = 60


def slugify(text: str) -> str:
    """Filesystem-safe slug for a finding title.

    Lowercases, collapses non-alphanumerics to hyphens, trims runs and
    caps at 60 chars. Empty input yields ``"unnamed-finding"`` so the
    pack always has a writable directory name.
    """
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    if not s:
        s = "unnamed-finding"
    if len(s) > _MAX_SLUG_LEN:
        s = s[:_MAX_SLUG_LEN].rstrip("-")
    return s or "unnamed-finding"


def _stable_id_suffix(props: dict[str, Any]) -> str:
    """Short deterministic suffix derived from a finding's URL/target/title.

    Two findings with the same slug but different URLs end up in
    distinct directories without overwriting each other.
    """
    seed = "::".join(str(props.get(k, "")) for k in ("url", "target", "endpoint", "title", "label"))
    if not seed.strip(":"):
        return ""
    return hashlib.sha1(seed.encode()).hexdigest()[:8]


@dataclass
class FindingPack:
    """Materialised pack on disk, returned by :func:`write_finding_pack`."""

    root: Path
    files_written: list[Path] = field(default_factory=list)
    evidence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "files_written": [str(p) for p in self.files_written],
            "evidence_count": self.evidence_count,
        }


def _normalise_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Coerce arbitrary finding-shaped dicts to the export schema.

    Accepts both the raw ``Node.model_dump()`` shape (``props`` nested) and
    a flat dict so the LangChain tool layer can hand whichever it has.
    """
    if not isinstance(finding, dict):
        raise TypeError("finding must be a dict")
    flat: dict[str, Any] = {}
    flat.update(finding.get("props") or {})
    # Top-level keys win — intentionally — so a caller wanting to override
    # a value from props can do so without mutating the nested dict.
    for k, v in finding.items():
        if k == "props":
            continue
        if v is not None:
            flat[k] = v
    flat.setdefault("title", flat.get("label") or "Unnamed finding")
    flat.setdefault("severity", "unknown")
    return flat


def _select_poc_filename(language: str | None) -> str:
    """Map a self-declared PoC language to a script filename."""
    lang = (language or "").lower()
    return {
        "python": "poc.py",
        "py": "poc.py",
        "ruby": "poc.rb",
        "rb": "poc.rb",
        "javascript": "poc.js",
        "js": "poc.js",
        "typescript": "poc.ts",
        "ts": "poc.ts",
        "shell": "poc.sh",
        "sh": "poc.sh",
        "bash": "poc.sh",
        "http": "poc.http",
        "raw": "poc.txt",
        "": "poc.sh",
    }.get(lang, "poc.txt")


def _render_readme(meta: dict[str, Any]) -> str:
    title = meta.get("title", "Unnamed finding")
    sev = (meta.get("severity") or "unknown").upper()
    cvss = meta.get("cvss_score")
    cvss_vec = meta.get("cvss_vector", "")
    summary = meta.get("summary") or meta.get("description") or "_(no summary recorded)_"
    target = meta.get("target") or meta.get("url") or ""
    mitre = meta.get("mitre") or meta.get("mitre_id") or ""
    parts = [
        f"# {title}",
        "",
        f"- **Severity:** {sev}",
    ]
    if cvss is not None:
        parts.append(f"- **CVSS:** {cvss} `{cvss_vec}`")
    if target:
        parts.append(f"- **Target:** `{target}`")
    if mitre:
        parts.append(f"- **MITRE ATT&CK:** {mitre}")
    parts.extend(
        [
            "",
            "## Summary",
            summary,
            "",
            "## Files",
            "- `repro.md` — step-by-step reproduction",
            "- `poc.<ext>` — runnable proof-of-concept",
            "- `evidence/` — captured requests/responses/screenshots",
            "- `manifest.json` — machine-readable metadata",
            "",
        ]
    )
    return "\n".join(parts).rstrip() + "\n"


def _render_repro(meta: dict[str, Any]) -> str:
    steps = meta.get("steps") or meta.get("repro_steps") or []
    if isinstance(steps, str):
        # Allow newline-delimited string from the LLM.
        steps = [s.strip() for s in steps.splitlines() if s.strip()]
    out: list[str] = ["# Reproduction Steps", ""]
    if not steps:
        out.append("_(no steps recorded — populate this file before triage)_")
    else:
        for i, step in enumerate(steps, 1):
            out.append(f"{i}. {step}")
    out.append("")
    if meta.get("notes"):
        out.append("## Notes")
        out.append(str(meta["notes"]))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _render_manifest(meta: dict[str, Any], finding_id: str) -> str:
    payload = {
        "schema_version": "1",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "finding_id": finding_id,
        "title": meta.get("title", ""),
        "severity": meta.get("severity", "unknown"),
        "cvss_score": meta.get("cvss_score"),
        "cvss_vector": meta.get("cvss_vector"),
        "target": meta.get("target") or meta.get("url"),
        "mitre": meta.get("mitre") or meta.get("mitre_id"),
        "references": meta.get("references") or [],
        "tags": meta.get("tags") or [],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_finding_pack(
    finding: dict[str, Any],
    *,
    output_root: str | Path,
    finding_id: str | None = None,
    evidence: Iterable[tuple[str, bytes | str]] | None = None,
    overwrite: bool = False,
) -> FindingPack:
    """Materialise a finding pack on disk.

    Args:
        finding: A finding-shaped dict. Accepts either the nested
            ``Node.model_dump()`` shape or a flat dict.
        output_root: Engagement root (e.g. ``/workspace/findings``). The
            pack is written to ``<output_root>/<slug>[-<digest>]/``.
        finding_id: Stable ID used in ``manifest.json``. When omitted a
            digest is derived from the finding's title/url/target.
        evidence: Optional iterable of ``(filename, contents)`` pairs
            written under ``evidence/``. Bytes pass through; strings are
            UTF-8 encoded.
        overwrite: When True, an existing pack directory is replaced; when
            False, files inside an existing pack directory are overwritten
            individually but the directory is reused.

    Returns:
        A :class:`FindingPack` describing the resulting pack on disk.
    """
    meta = _normalise_finding(finding)
    title = meta.get("title", "Unnamed finding")
    slug = slugify(title)
    suffix = _stable_id_suffix(meta)
    dir_name = f"{slug}-{suffix}" if suffix else slug
    root = Path(output_root) / dir_name
    if root.exists() and overwrite:
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()
    root.mkdir(parents=True, exist_ok=True)
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(exist_ok=True)

    files: list[Path] = []

    readme_path = root / "README.md"
    readme_path.write_text(_render_readme(meta), encoding="utf-8")
    files.append(readme_path)

    repro_path = root / "repro.md"
    repro_path.write_text(_render_repro(meta), encoding="utf-8")
    files.append(repro_path)

    poc_filename = _select_poc_filename(meta.get("poc_language"))
    poc_body = meta.get("poc") or meta.get("poc_body") or ""
    if not poc_body:
        poc_body = (
            "#!/usr/bin/env bash\n"
            "# TODO: replace with the executable proof-of-concept that triggers this finding.\n"
        )
    poc_path = root / poc_filename
    poc_path.write_text(poc_body if poc_body.endswith("\n") else poc_body + "\n", encoding="utf-8")
    if poc_filename.endswith(".sh") or poc_filename.endswith(".py"):
        try:
            poc_path.chmod(0o755)
        except OSError:
            # Non-POSIX filesystems (eg. mounted from host on Windows) ignore chmod
            # — the file is still readable, the consumer can chmod themselves.
            pass
    files.append(poc_path)

    fid = finding_id or meta.get("id") or _stable_id_suffix(meta) or slug
    manifest_path = root / "manifest.json"
    manifest_path.write_text(_render_manifest(meta, fid), encoding="utf-8")
    files.append(manifest_path)

    evidence_count = 0
    if evidence:
        for name, data in evidence:
            stem, _, ext = name.rpartition(".")
            if stem and ext and ext.isalnum() and len(ext) <= 8:
                # Preserve extension when the caller named the artefact like
                # ``request.http`` — keeps mime sniffing useful for triage.
                safe_name = f"{slugify(stem) or 'evidence'}.{ext.lower()}"
            else:
                safe_name = slugify(name) or "evidence"
            target = evidence_dir / safe_name
            payload = data.encode("utf-8") if isinstance(data, str) else data
            target.write_bytes(payload)
            files.append(target)
            evidence_count += 1

    return FindingPack(root=root, files_written=files, evidence_count=evidence_count)


def write_findings_index(packs: Iterable[FindingPack], *, output_root: str | Path) -> Path:
    """Write a summary ``findings/INDEX.md`` listing every materialised pack.

    The index is regenerated each call (idempotent rewrite) so the file
    always reflects the current state of ``output_root``.
    """
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "INDEX.md"
    rows: list[str] = ["# Findings Index", "", "| Pack | Severity | Title |", "| --- | --- | --- |"]
    for pack in packs:
        manifest = pack.root / "manifest.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        rows.append(
            f"| `{pack.root.name}` | {payload.get('severity', '?').upper()} | "
            f"{payload.get('title', '?')} |"
        )
    index_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return index_path


__all__ = [
    "FindingPack",
    "slugify",
    "write_finding_pack",
    "write_findings_index",
]
