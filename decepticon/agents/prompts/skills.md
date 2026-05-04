<!-- THIS FILE IS NO LONGER LOADED AS A SHARED PROMPT FRAGMENT.

Skill system instructions are now injected dynamically by SkillsMiddleware
(decepticon/middleware/skills.py) via the wrap_model_call() hook. The middleware
provides:

  - Red-team-specific system prompt template
  - Skills grouped by subdomain (kill chain phase)
  - MITRE ATT&CK technique IDs shown inline
  - Progressive disclosure instructions and bash access warnings

Previously this file was included via:
    load_prompt("recon", shared=["bash", "skills"])

Now agents use:
    load_prompt("recon", shared=["bash"])

And the middleware handles skill catalog injection on every LLM call.

See: decepticon/middleware/skills.py :: DECEPTICON_SKILLS_PROMPT
-->
