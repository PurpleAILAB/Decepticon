"""Skill loading tools for Decepticon agents."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

# ── load_skill tool ──────────────────────────────────────────────────────────
# A Decepticon-specific replacement for `load_skill("/skills/...")` that
# returns the full skill body without the deepagents 100-line limit, plus a
# base-directory header and an index of references/* in the same directory.

_SKILL_PATH_PREFIX = "/skills/"


def _strip_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """Strip a leading YAML frontmatter block (``---\\n...\\n---``) from text.

    Returns ``(body, frontmatter_dict)``. Only flat ``key: value`` pairs are
    parsed — nested YAML is ignored. If no frontmatter is present the original
    text is returned with an empty dict.
    """
    if not text.startswith("---\n"):
        return text, {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return text, {}
    fm_text = text[4:end]
    body = text[end + 5 :]
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return body, fm


def _read_via_backend(backend: Any, skill_path: str) -> tuple[str | None, str | None]:
    """Read a file via the deepagents backend protocol.

    Returns ``(content, error)``: exactly one of the two is non-None. The
    backend abstraction routes ``/skills/`` reads to a local
    ``FilesystemBackend`` (the package's ``decepticon/skills`` tree, read
    in-process), while other paths go to the sandbox transport.
    """
    try:
        res = backend.read(skill_path)
    except Exception as exc:
        return None, f"backend read failed: {exc}"
    if getattr(res, "error", None):
        return None, str(res.error)
    data = getattr(res, "file_data", None)
    if not data:
        return None, "empty backend response"
    content = data.get("content", "")
    if isinstance(content, list):  # legacy v1 (line-split) format
        content = "\n".join(content)
    if not isinstance(content, str):
        return None, "backend returned non-string content"
    return content, None


def _list_dir_via_backend(backend: Any, dir_path: str) -> list[str]:
    """List ``.md`` files under ``dir_path`` via backend, sorted.

    Best-effort: returns an empty list on any backend failure rather than
    raising, so the references/siblings index degrades gracefully when a
    skill directory has none.
    """
    try:
        res = backend.ls(dir_path)
    except Exception:
        return []
    if getattr(res, "error", None):
        return []
    names: list[str] = []
    for attr in ("entries", "files", "items"):
        candidate = getattr(res, attr, None)
        if isinstance(candidate, list):
            names = [str(n) for n in candidate]
            break
    if not names:
        data = getattr(res, "file_data", None)
        if isinstance(data, dict):
            names = [str(n) for n in data.get("entries", [])]
    return sorted(n for n in names if n.endswith(".md"))


def build_load_skill_tool(backend: Any, sources: list[str]):  # type: ignore[no-untyped-def]
    """Construct the ``load_skill`` LangChain tool.

    Returns a closure-bound ``@tool``-decorated function that reads a skill
    markdown file via the deepagents backend (same protocol as ``read_file``).
    Path is restricted to ``/skills/*`` to keep this tool's intent distinct
    from the general ``read_file``.

    Backend routing for ``/skills/`` is handled by ``CompositeBackend``
    (see ``decepticon/backends/__init__.py:make_agent_backend``), which
    sends these paths to a local ``FilesystemBackend`` inside the
    langgraph container. No manual unwrapping needed.
    """

    @tool
    def load_skill(skill_path: str, include_siblings: bool = False) -> str:
        """Load a Decepticon skill file (full body, no line-limit truncation).

        Use this for ANY ``/skills/*.md`` file instead of ``read_file``. It
        returns the entire skill body (frontmatter stripped) prepended with a
        base directory header, followed by an index of any ``references/`` files
        in the same directory so you know what additional templates / cheat
        sheets exist for this skill.

        Args:
            skill_path: Absolute path under ``/skills/``, e.g.
                ``/skills/standard/exploit/web/crypto.md``.
            include_siblings: If True, also list sibling ``.md`` files in the
                same directory (useful when the skill is a category index).
                Default False to avoid duplicating the catalog already in the
                system prompt.

        Returns:
            The skill body with a header + references index. Errors are
            returned as ``[load_skill error] ...`` strings (never raised).
        """
        if not isinstance(skill_path, str) or not skill_path:
            return "[load_skill error] skill_path must be a non-empty string."
        if not skill_path.startswith(_SKILL_PATH_PREFIX):
            return (
                "[load_skill error] Path must start with /skills/. "
                "For non-skill files use read_file. "
                f"Got: {skill_path!r}"
            )
        if not skill_path.endswith(".md"):
            return f"[load_skill error] Skill files must be markdown (.md). Got: {skill_path!r}"
        # Reject path traversal — disallow ".." segments
        if ".." in skill_path.split("/"):
            return f"[load_skill error] Path traversal not allowed: {skill_path!r}"
        # Enforce agent's skill source allowlist
        if sources and not any(skill_path.startswith(src.rstrip("/")) for src in sources):
            allowed = ", ".join(sources)
            return (
                f"[load_skill error] This agent may only load skills from: {allowed}. "
                f"Got: {skill_path!r}"
            )

        raw, err = _read_via_backend(backend, skill_path)
        if raw is None:
            return f"[load_skill error] Skill not found: {skill_path} ({err})"

        body, frontmatter = _strip_frontmatter(raw)

        path_parts = skill_path.rsplit("/", 1)
        base_dir = path_parts[0] if len(path_parts) == 2 else "/"
        stem = path_parts[-1].rsplit(".", 1)[0]
        header_lines = [f"Base directory for this skill: {base_dir}"]
        name = frontmatter.get("name") or stem
        description = frontmatter.get("description", "").strip()
        header_lines.append(f"Skill: {name}" + (f" — {description}" if description else ""))
        header = "\n".join(header_lines)

        sections: list[str] = [header, "", body.rstrip(), ""]

        refs_dir = base_dir.rstrip("/") + "/references"
        refs = _list_dir_via_backend(backend, refs_dir)
        if refs:
            sections.append("---")
            sections.append("References (load with `load_skill` or `read_file`):")
            sections.extend(f"- {refs_dir}/{r}" for r in refs)
            sections.append("")

        if include_siblings:
            sibs = [s for s in _list_dir_via_backend(backend, base_dir) if s != path_parts[-1]]
            if sibs:
                sections.append("---")
                sections.append("Related sub-skills in this directory (load with `load_skill`):")
                sections.extend(f"- {base_dir.rstrip('/')}/{s}" for s in sibs)
                sections.append("")

        return "\n".join(sections).rstrip() + "\n"

    return load_skill


__all__ = ["build_load_skill_tool"]
