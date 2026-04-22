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
from typing import TYPE_CHECKING

from deepagents.middleware.skills import SkillsMiddleware

if TYPE_CHECKING:
    from deepagents.middleware.skills import SkillMetadata

# ── Decepticon skill system prompt template ──────────────────────────────────
# Replaces both the shared `skills.md` fragment and the base middleware's
# generic SKILLS_SYSTEM_PROMPT. Uses {skills_locations} and {skills_list}
# placeholders that the base class populates.

DECEPTICON_SKILLS_PROMPT = """
<SKILLS>
## Red Team Knowledge Base — Progressive Disclosure

You have access to a curated library of red team skills — domain-specific knowledge
covering techniques, tools, OPSEC guidance, and structured workflows for each phase
of the kill chain.

{skills_locations}

### How It Works
1. **Catalog below** — Each skill shows: description, trigger keywords, MITRE ATT&CK
   IDs, and a `read_file()` path. This tells you WHAT expertise is available and
   WHEN each skill applies.
2. **On-demand loading** — The catalog is NOT enough to execute. Before using any
   technique, you MUST `read_file()` the full SKILL.md using the path shown.
3. **Reference files** — Some skills have a `references/` subdirectory with
   cheat sheets, templates, or quickstart guides. Access them via `read_file()`.

### Catalog Format
```
- **skill-name**: What the skill covers. [MITRE IDs]
  triggers: keywords that indicate when to load this skill
  `read_file("/skills/category/skill-name/SKILL.md")`
```

### Skill Selection
To decide which skill to load, match your current objective against the **triggers**
line. If the objective mentions any trigger keyword, load that skill before proceeding.

- Objective says "nmap port scan" → triggers match **active-recon** → load it
- Objective says "kerberoast" → triggers match **ad-exploitation** → load it
- Multiple matches → load the most specific skill first

### Access Rules
- `read_file("/skills/<category>/<skill-name>/SKILL.md")` — CORRECT
- `bash(command="cat /skills/...")` — WILL FAIL (sandbox does not mount `/skills/`)
- Skills are on the host filesystem, routed through a virtual backend.

### SKILL-FIRST RULE (CRITICAL)
Memorize the skill catalog below. When a task matches an available skill, you MUST
load and follow that skill BEFORE acting on your own knowledge. Skills contain
domain-specific checklists, templates, and procedures that are more precise and
current than general knowledge. Operating from memory when a specialized skill
exists is a critical failure — load the skill, follow its procedure.

### When to Load
- **Before each new technique**: Read the relevant skill FIRST, then execute.
- **Before using unfamiliar tools**: Even if you know the tool generically, skills
  contain environment-specific instructions (paths, configs, container setup).
- **When an objective maps to triggers**: Match objective keywords → skill triggers.

### Available Skills

{skills_list}
</SKILLS>"""


class DecepticonSkillsMiddleware(SkillsMiddleware):
    """Red-team-aware skill middleware with phase grouping and MITRE ATT&CK tags.

    Subclasses the base SkillsMiddleware to provide:
    - Decepticon-specific system prompt template
    - Skills grouped by subdomain (kill chain phase)
    - MITRE ATT&CK technique IDs shown inline
    - Compact display format for context efficiency

    Args:
        backend: Backend instance for file operations.
        sources: List of skill source paths (e.g., ``['/skills/recon/', '/skills/shared/']``).
    """

    def __init__(self, *, backend, sources: list[str]) -> None:
        super().__init__(backend=backend, sources=sources)
        self.system_prompt_template = DECEPTICON_SKILLS_PROMPT

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

                lines.append(f'  `read_file("{skill["path"]}")`')

            lines.append("")  # blank line between groups

        return "\n".join(lines)


def _parse_comma_field(value: str | list | None) -> list[str]:
    """Parse a comma/space-separated field into a clean list of strings."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [t.strip() for t in str(value).replace(",", " ").split() if t.strip()]


__all__ = ["DecepticonSkillsMiddleware"]
