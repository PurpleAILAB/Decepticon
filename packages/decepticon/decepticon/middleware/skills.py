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

Workflow.md loading is **no longer** a middleware responsibility. As of
Skillogy Amendment v0.2.2, the per-role ``workflow.md`` files were renamed
``<role>.md`` and moved to ``decepticon/agents/prompts/workflows/``;
``PromptBuilder`` concatenates them into the cacheable static prefix at
agent factory time. See ``decepticon/agents/prompts/builder.py``.

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
#   {skills_list}      — catalog of sub-skills grouped by subdomain

DECEPTICON_SKILLS_PROMPT = """
<SKILLS>
## Red Team Knowledge Base — Progressive Disclosure

You have access to a curated library of red team skills — domain-specific knowledge
covering techniques, tools, and OPSEC guidance for each phase of the kill chain.

{skills_locations}

### Sub-Skills (Progressive Disclosure)

The catalog below lists per-technique sub-skills. Your phase workflow is
loaded separately into your system prompt; sub-skills are loaded on demand
via `load_skill()` when their triggers match your current objective.

### How It Works
1. **Catalog below** — Each sub-skill shows: description, trigger keywords,
   MITRE ATT&CK IDs, and a `load_skill()` path. This tells you WHAT expertise
   is available and WHEN it applies.
2. **On-demand sub-skill loading** — When your task matches a trigger,
   `load_skill()` the full SKILL.md before acting on the technique.
3. **Reference files** — Some skills have a `references/` subdirectory with
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
- `load_skill("<slug-or-path>")` — **REQUIRED** for every /skills/* file.
  Accepts an exact `/skills/.../*.md` path, a relative `standard/.../SKILL.md`
  path, or a unique slug such as `sql-injection`. Returns the FULL body (no
  line limit) plus a base directory header and an index of references/* and
  sibling sub-skills in the same directory. If a slug is ambiguous, use one of
  the exact paths returned in the error.
- `read_file("/skills/...")` and `bash(command="cat /skills/...", description="...")` — DO NOT
  use these for skill files. `/skills/` is served in-process by a local
  FilesystemBackend (not the sandbox); only `load_skill` resolves it.

### SKILL-FIRST RULE (CRITICAL)
The catalog below overrides your general knowledge. When a task matches a
sub-skill trigger, load the skill BEFORE acting on memory. Operating from
memory when a specialized skill exists is a critical failure.

### When to Load (Sub-Skills)
- **Before each new technique**: Read the relevant skill FIRST, then execute.
- **Before unfamiliar tools**: Skills contain environment-specific instructions
  (paths, configs, container setup) that override generic tool knowledge.
- **When an objective maps to triggers**: Match objective keywords → triggers.

### Available Sub-Skills

{skills_list}
</SKILLS>"""


class SkillsMiddleware(BaseSkillsMiddleware):
    """Red-team-aware skill middleware with phase grouping and MITRE ATT&CK tags.

    Subclasses the base SkillsMiddleware to provide:
    - Decepticon-specific system prompt template
    - Skills grouped by subdomain (kill chain phase)
    - MITRE ATT&CK technique IDs shown inline
    - Compact display format for context efficiency

    Per-role workflow content is **not** loaded here — see
    ``decepticon/agents/prompts/builder.py`` for the
    ``prompts/workflows/<role>.md`` inline mechanism.

    Args:
        backend: Backend instance for file operations.
        sources: List of skill source paths (e.g., ``['/skills/standard/recon/', '/skills/shared/']``).
    """

    def __init__(self, *, backend: Any, sources: list[str]) -> None:
        super().__init__(backend=backend, sources=sources)
        self.system_prompt_template = DECEPTICON_SKILLS_PROMPT
        self.tools = [build_load_skill_tool(backend, self.sources)]

    # ── modify_request: render the skills catalog ─────────────────────────────

    def modify_request(self, request):  # type: ignore[no-untyped-def]
        skills_metadata = request.state.get("skills_metadata", [])
        skills_locations = self._format_skills_locations()
        skills_list = self._format_skills_list(skills_metadata)
        # The template can be edited at runtime by subclasses; missing or
        # extra placeholders should not raise from a hot model-call path.
        # On mismatch, log once and fall through to the original system
        # message rather than failing the whole agent step.
        try:
            skills_section = self.system_prompt_template.format(
                skills_locations=skills_locations,
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
