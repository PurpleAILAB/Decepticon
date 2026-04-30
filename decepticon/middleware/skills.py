"""Decepticon Skills Middleware — red-team-aware skill system.

Subclasses the Deep Agents SkillsMiddleware to provide:

1. **Decepticon-specific system prompt** — Replaces the generic "Skills System"
   template with red team context, bash access limitation warnings, and
   domain-specific framing.

2. **Phase-aware skill grouping** — Skills grouped by subdomain (reconnaissance,
   credential-access, lateral-movement, etc.) instead of a flat list.

3. **MITRE ATT&CK surface** — Displays technique IDs from skill frontmatter
   metadata, making the agent ATT&CK-aware at the skill catalog level.

4. **Compact display with trigger keywords** — Clean descriptions with separate
   ``when_to_use`` trigger keywords for objective matching, MITRE tags inline.

5. **Root workflow auto-load** — Each configured ``source`` directory is
   probed for a ``workflow.md`` file; if present, its full body is injected
   into the system prompt before the catalog. This forces the agent to start
   every session with the agent-level workflow (phases, scope rules, handoff
   format) loaded — no relying on the model to issue ``read_file`` first.

This middleware replaces BOTH the old `skills.md` shared prompt fragment AND
the base middleware's generic `SKILLS_SYSTEM_PROMPT`. All skill instructions
are consolidated here.

Usage:
    from decepticon.middleware.skills import DecepticonSkillsMiddleware

    middleware = DecepticonSkillsMiddleware(
        backend=backend,
        sources=["/skills/recon/", "/skills/shared/"],
    )
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import SkillsMiddleware
from langchain_core.tools import tool

if TYPE_CHECKING:
    from deepagents.middleware.skills import SkillMetadata


# ── Decepticon skill system prompt template ──────────────────────────────────
# Replaces both the shared `skills.md` fragment and the base middleware's
# generic SKILLS_SYSTEM_PROMPT. Placeholders:
#   {skills_locations} — `**Decepticon Skills**: /skills/recon/` style headers
#   {workflow}         — full body of <source>/workflow.md files (auto-loaded)
#   {skills_list}      — catalog of sub-skills grouped by subdomain

DECEPTICON_SKILLS_PROMPT = """
<SKILLS>
## Red Team Knowledge Base — Progressive Disclosure

You have access to a curated library of red team skills — domain-specific knowledge
covering techniques, tools, OPSEC guidance, and structured workflows for each phase
of the kill chain.

{skills_locations}

{workflow}

### Sub-Skills (Progressive Disclosure)

The catalog below lists per-technique sub-skills. The workflow above is always
loaded; sub-skills are loaded on demand via `read_file()` when their triggers
match your current objective.

### How It Works
1. **Workflow above** — Always loaded. Defines the agent's loop, scope rules,
   discipline, and handoff format. Read it before any tool call this turn.
2. **Catalog below** — Each sub-skill shows: description, trigger keywords,
   MITRE ATT&CK IDs, and a `read_file()` path. This tells you WHAT expertise
   is available and WHEN it applies.
3. **On-demand sub-skill loading** — When your task matches a trigger,
   `read_file()` the full SKILL.md before acting on the technique.
4. **Reference files** — Some skills have a `references/` subdirectory with
   cheat sheets, templates, or quickstart guides. Access them via `read_file()`.

### Catalog Format
```
- **skill-name**: What the skill covers. [MITRE IDs]
  triggers: keywords that indicate when to load this skill
  `load_skill("/skills/category/skill-name/SKILL.md")`
```

### Skill Selection
Match the current objective against **triggers** — load the most specific match.

- "nmap port scan" → triggers match **active-recon** → load it
- "kerberoast" → triggers match **ad-exploitation** → load it
- Multiple matches → load the most specific skill first

### Access Rules
- `load_skill("/skills/<category>/<skill-name>/SKILL.md")` — **CORRECT** for
  /skills/* paths. Returns the FULL body (no line limit) plus a base directory
  header and an index of references/* and sibling sub-skills in the same dir.
- `read_file("/skills/...")` — works but is line-limited (default 100 lines)
  and may truncate. Prefer `load_skill` for skill files.
- `bash(command="cat /skills/...")` — WILL FAIL if /skills/ is not mounted
  in the bash sandbox of the current agent.
- Skills are routed through the agent's filesystem backend.

### SKILL-FIRST RULE (CRITICAL)
The workflow above and the catalog below override your general knowledge.
When a task matches a workflow phase or a sub-skill trigger, follow the
workflow / load the skill BEFORE acting on memory. Operating from memory
when a specialized skill exists is a critical failure.

### When to Load (Sub-Skills)
- **Before each new technique**: Read the relevant skill FIRST, then execute.
- **Before unfamiliar tools**: Skills contain environment-specific instructions
  (paths, configs, container setup) that override generic tool knowledge.
- **When an objective maps to triggers**: Match objective keywords → triggers.

### Available Sub-Skills

{skills_list}
</SKILLS>"""


_WORKFLOW_FILENAME = "workflow.md"


class DecepticonSkillsMiddleware(SkillsMiddleware):
    """Red-team-aware skill middleware with phase grouping and MITRE ATT&CK tags.

    Subclasses the base SkillsMiddleware to provide:
    - Decepticon-specific system prompt template
    - Skills grouped by subdomain (kill chain phase)
    - MITRE ATT&CK technique IDs shown inline
    - Compact display format for context efficiency
    - Auto-load of ``<source>/workflow.md`` (full body, prepended to catalog)

    Args:
        backend: Backend instance for file operations.
        sources: List of skill source paths (e.g., ``['/skills/recon/', '/skills/shared/']``).
    """

    def __init__(self, *, backend: Any, sources: list[str]) -> None:
        super().__init__(backend=backend, sources=sources)
        self.system_prompt_template = DECEPTICON_SKILLS_PROMPT
        self.tools = [_build_load_skill_tool()]

    # ── workflow.md auto-load ────────────────────────────────────────────────

    def _read_workflow_for_source(self, backend: Any, source: str) -> str | None:
        """Load <source>/workflow.md from the backend. Returns content or None."""
        path = source.rstrip("/") + "/" + _WORKFLOW_FILENAME
        try:
            res = backend.read(path)
        except Exception:
            return None
        if getattr(res, "error", None):
            return None
        data = getattr(res, "file_data", None)
        if not data:
            return None
        content = data.get("content", "")
        if isinstance(content, list):  # legacy v1 (line-split) format
            content = "\n".join(content)
        return content if isinstance(content, str) and content.strip() else None

    async def _aread_workflow_for_source(self, backend: Any, source: str) -> str | None:
        """Async sibling of ``_read_workflow_for_source``."""
        path = source.rstrip("/") + "/" + _WORKFLOW_FILENAME
        try:
            res = await backend.aread(path)
        except Exception:
            return None
        if getattr(res, "error", None):
            return None
        data = getattr(res, "file_data", None)
        if not data:
            return None
        content = data.get("content", "")
        if isinstance(content, list):
            content = "\n".join(content)
        return content if isinstance(content, str) and content.strip() else None

    def _format_workflow_section(self, parts: list[tuple[str, str]]) -> str:
        """Wrap each loaded workflow.md body with a header naming its source."""
        if not parts:
            return ""
        blocks: list[str] = ["### Always-Loaded Workflows", ""]
        for source, body in parts:
            label = source.rstrip("/").split("/")[-1].replace("-", " ").title()
            path = source.rstrip("/") + "/" + _WORKFLOW_FILENAME
            blocks.append(f"#### {label} Workflow — `{path}`")
            blocks.append("")
            blocks.append(body.strip())
            blocks.append("")
        return "\n".join(blocks).rstrip() + "\n"

    # ── before_agent: parent loads catalog, we add workflow blob to state ───

    def before_agent(self, state, runtime, config):  # type: ignore[no-untyped-def]
        base_update = super().before_agent(state, runtime, config)
        if "workflow_content" in state:
            return base_update
        backend = self._get_backend(state, runtime, config)
        parts: list[tuple[str, str]] = []
        for source in self.sources:
            body = self._read_workflow_for_source(backend, source)
            if body:
                parts.append((source, body))
        workflow_blob = self._format_workflow_section(parts)
        merged = dict(base_update) if base_update else {}
        merged["workflow_content"] = workflow_blob
        return merged

    async def abefore_agent(self, state, runtime, config):  # type: ignore[no-untyped-def]
        base_update = await super().abefore_agent(state, runtime, config)
        if "workflow_content" in state:
            return base_update
        backend = self._get_backend(state, runtime, config)
        parts: list[tuple[str, str]] = []
        for source in self.sources:
            body = await self._aread_workflow_for_source(backend, source)
            if body:
                parts.append((source, body))
        workflow_blob = self._format_workflow_section(parts)
        merged = dict(base_update) if base_update else {}
        merged["workflow_content"] = workflow_blob
        return merged

    # ── modify_request: include {workflow} placeholder ───────────────────────

    def modify_request(self, request):  # type: ignore[no-untyped-def]
        skills_metadata = request.state.get("skills_metadata", [])
        workflow_blob = request.state.get("workflow_content", "")
        skills_locations = self._format_skills_locations()
        skills_list = self._format_skills_list(skills_metadata)
        skills_section = self.system_prompt_template.format(
            skills_locations=skills_locations,
            workflow=workflow_blob,
            skills_list=skills_list,
        )
        new_system_message = append_to_system_message(request.system_message, skills_section)
        return request.override(system_message=new_system_message)

    # ── catalog formatter (unchanged from previous version) ──────────────────

    def _format_skills_list(self, skills: list[SkillMetadata]) -> str:
        """Format skills grouped by subdomain with MITRE ATT&CK tags.

        Overrides the base class flat listing to provide:
        - Grouping by ``metadata.subdomain`` (e.g., reconnaissance, credential-access)
        - MITRE ATT&CK technique IDs shown inline
        - Separate ``when_to_use`` triggers for agent objective matching
        - Compact format: description + triggers + path
        """
        if not skills:
            paths = [f"`{p}`" for p in self.sources]
            return f"(No skills loaded. Skill sources: {', '.join(paths)})"

        # Group skills by subdomain
        groups: dict[str, list[SkillMetadata]] = defaultdict(list)
        for skill in skills:
            metadata = skill.get("metadata", {})
            subdomain = metadata.get("subdomain", "general")
            groups[subdomain].append(skill)

        # Render grouped listing
        lines: list[str] = []
        for subdomain, group_skills in sorted(groups.items()):
            # Section header — capitalize and format subdomain
            header = subdomain.replace("-", " ").title()
            lines.append(f"#### {header}")

            for skill in sorted(group_skills, key=lambda s: s["name"]):
                # Extract extended metadata
                metadata = skill.get("metadata", {})
                mitre_raw = metadata.get("mitre_attack", "")
                when_to_use = metadata.get("when_to_use", "")

                # Build MITRE tag string
                mitre_tags = _parse_comma_field(mitre_raw)
                mitre_str = f" [{', '.join(mitre_tags)}]" if mitre_tags else ""

                # Skill entry: description + MITRE tags
                lines.append(f"- **{skill['name']}**: {skill['description']}{mitre_str}")

                # Trigger keywords for objective matching
                if when_to_use:
                    lines.append(f"  triggers: {when_to_use}")

                lines.append(f'  `load_skill("{skill["path"]}")`')

            lines.append("")  # blank line between groups

        return "\n".join(lines)


def _parse_comma_field(value: str | list | None) -> list[str]:
    """Parse a comma/space-separated field into a clean list of strings."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [t.strip() for t in str(value).replace(",", " ").split() if t.strip()]


# ── load_skill tool ──────────────────────────────────────────────────────────
# A Decepticon-specific replacement for `read_file("/skills/...")` that
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


def _list_references(skill_dir: Path) -> list[Path]:
    """Return sorted reference files under ``skill_dir/references/`` (one level)."""
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        return []
    return sorted(p for p in refs_dir.iterdir() if p.is_file())


def _list_sibling_skills(skill_path: Path) -> list[Path]:
    """Return sibling ``.md`` files in the same directory (excluding self)."""
    parent = skill_path.parent
    if not parent.is_dir():
        return []
    return sorted(
        p for p in parent.iterdir() if p.is_file() and p.suffix == ".md" and p != skill_path
    )


def _build_load_skill_tool():  # type: ignore[no-untyped-def]
    """Construct the ``load_skill`` LangChain tool.

    Returns a closure-bound ``@tool``-decorated function that reads a skill
    markdown file and renders it with a base-directory header + reference
    index. Path is restricted to ``/skills/*`` to keep this tool's intent
    distinct from the general ``read_file``.
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
                ``/skills/exploit/web/crypto.md``.
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

        path = Path(skill_path)
        try:
            if not path.exists():
                return f"[load_skill error] Skill not found: {skill_path}"
            if not path.is_file():
                return f"[load_skill error] Not a file: {skill_path}"
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"[load_skill error] Read failed for {skill_path}: {exc}"

        body, frontmatter = _strip_frontmatter(raw)

        base_dir = path.parent.as_posix()
        header_lines = [f"Base directory for this skill: {base_dir}"]
        name = frontmatter.get("name") or path.stem
        description = frontmatter.get("description", "").strip()
        header_lines.append(f"Skill: {name}" + (f" — {description}" if description else ""))
        header = "\n".join(header_lines)

        sections: list[str] = [header, "", body.rstrip(), ""]

        refs = _list_references(path.parent)
        if refs:
            sections.append("---")
            sections.append("References (load with `load_skill` or `read_file`):")
            sections.extend(f"- {r.as_posix()}" for r in refs)
            sections.append("")

        if include_siblings:
            siblings = _list_sibling_skills(path)
            if siblings:
                sections.append("---")
                sections.append("Related sub-skills in this directory (load with `load_skill`):")
                sections.extend(f"- {s.as_posix()}" for s in siblings)
                sections.append("")

        return "\n".join(sections).rstrip() + "\n"

    return load_skill


__all__ = ["DecepticonSkillsMiddleware"]
