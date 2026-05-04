"""SkillsMiddleware — red-team-aware skill system.

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
    from decepticon.middleware.skills import SkillsMiddleware

    middleware = SkillsMiddleware(
        backend=backend,
        sources=["/skills/recon/", "/skills/shared/"],
    )
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import SkillsMiddleware as BaseSkillsMiddleware
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
loaded; sub-skills are loaded on demand via `load_skill()` when their triggers
match your current objective.

### How It Works
1. **Workflow above** — Always loaded. Defines the agent's loop, scope rules,
   discipline, and handoff format. Read it before any tool call this turn.
2. **Catalog below** — Each sub-skill shows: description, trigger keywords,
   MITRE ATT&CK IDs, and a `load_skill()` path. This tells you WHAT expertise
   is available and WHEN it applies.
3. **On-demand sub-skill loading** — When your task matches a trigger,
   `load_skill()` the full SKILL.md before acting on the technique.
4. **Reference files** — Some skills have a `references/` subdirectory with
   cheat sheets, templates, or quickstart guides. Access them via `load_skill()`.

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
- `load_skill("/skills/<category>/<skill-name>/SKILL.md")` — **REQUIRED** for
  every /skills/* file. Routes through the same sandbox backend as `read_file`,
  returns the FULL body (no line limit) plus a base directory header and an
  index of references/* and sibling sub-skills in the same directory.
- `read_file("/skills/...")` and `bash(command="cat /skills/...")` — DO NOT
  use these for skill files. The langgraph container does not host /skills/;
  only `load_skill` reaches the sandbox where /skills/ is baked in.

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


class SkillsMiddleware(BaseSkillsMiddleware):
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
        self.tools = [_build_load_skill_tool(backend)]

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
    backend abstraction is what gives ``load_skill`` access to the sandbox
    container's filesystem (where ``/skills/`` is baked into the image) instead
    of the langgraph container's local fs (where ``/skills/`` does not exist).
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


def _build_load_skill_tool(backend: Any):  # type: ignore[no-untyped-def]
    """Construct the ``load_skill`` LangChain tool.

    Returns a closure-bound ``@tool``-decorated function that reads a skill
    markdown file via the deepagents backend (same path used by ``read_file``,
    so it sees the sandbox container's ``/skills/`` mount instead of the
    langgraph container's local fs). Path is restricted to ``/skills/*`` to
    keep this tool's intent distinct from the general ``read_file``.
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


__all__ = ["SkillsMiddleware"]
