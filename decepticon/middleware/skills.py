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

This middleware replaces BOTH the old shared skill prompt fragment AND
the base middleware's generic `SKILLS_SYSTEM_PROMPT`. All skill instructions
are consolidated here.

Usage:
    from decepticon.middleware.skills import SkillsMiddleware

    middleware = SkillsMiddleware(
        backend=backend,
        sources=["/skills/standard/recon/", "/skills/shared/"],
    )
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import SkillsMiddleware as BaseSkillsMiddleware

from decepticon.tools.skills import build_load_skill_tool

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from deepagents.middleware.skills import SkillMetadata


# ── Decepticon skill system prompt template ──────────────────────────────────
# Replaces both the old shared skill prompt fragment and the base middleware's
# generic SKILLS_SYSTEM_PROMPT. Placeholders:
#   {skills_locations} — `**Decepticon Skills**: /skills/standard/recon/` style headers
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
  every /skills/* file. Returns the FULL body (no line limit) plus a base
  directory header and an index of references/* and sibling sub-skills in the
  same directory.
- `read_file("/skills/...")` and `bash(command="cat /skills/...")` — DO NOT
  use these for skill files. `/skills/` is served in-process by a local
  FilesystemBackend (not the sandbox); only `load_skill` resolves it.

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
        sources: List of skill source paths (e.g., ``['/skills/standard/recon/', '/skills/shared/']``).
    """

    def __init__(self, *, backend: Any, sources: list[str]) -> None:
        super().__init__(backend=backend, sources=sources)
        self.system_prompt_template = DECEPTICON_SKILLS_PROMPT
        self.tools = [build_load_skill_tool(backend, self.sources)]

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
        # Truthy-but-not-a-dict (e.g. a backend returning a raw string in
        # error paths) would crash on ``.get``; isinstance gate is the
        # explicit contract check.
        if not isinstance(data, dict):
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
        if not isinstance(data, dict):
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
        # The template can be edited at runtime by subclasses; missing or
        # extra placeholders should not raise from a hot model-call path.
        # On mismatch, log once and fall through to the original system
        # message rather than failing the whole agent step.
        try:
            skills_section = self.system_prompt_template.format(
                skills_locations=skills_locations,
                workflow=workflow_blob,
                skills_list=skills_list,
            )
        except (KeyError, IndexError) as e:
            log.warning(
                "skills system_prompt_template format failed (%s); "
                "skipping skills injection for this call",
                e,
            )
            return request
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


__all__ = ["SkillsMiddleware"]
