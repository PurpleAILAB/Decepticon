"""Agent system prompt assembly pipeline.

Re-export shim. The implementation lives in two sibling modules:

- :mod:`decepticon.agents.prompts.builder` — the prompt-assembly engine:
  fragment readers, :class:`PromptBuilder`, :func:`load_prompt`, the
  cross-cutting pattern constants, and the cache-boundary constant.
- :mod:`decepticon.agents.prompts.registry` — language / locale data and
  policy: the country→language and language-name maps, and
  :func:`build_language_policy`.

``builder`` depends on ``registry`` (one-directional — no cycle). Every name
previously defined at the top level of this module is re-exported here so
``from decepticon.agents.prompts import X`` keeps working unchanged. The
redundant ``X as X`` import aliases mark these as intentional re-exports; the
original module defined no ``__all__``, so none is added here and ``import *``
behaviour is preserved.

See :mod:`decepticon.agents.prompts.builder` for the assembly design notes
(static/dynamic section separation, tool-prompt co-location, cross-cutting
patterns, section registry) and the :func:`load_prompt` / :class:`PromptBuilder`
usage examples.
"""

from __future__ import annotations

from decepticon.agents.prompts.builder import (
    _ANALYST_MINDSET as _ANALYST_MINDSET,
)
from decepticon.agents.prompts.builder import (
    _FAITHFUL_REPORTING as _FAITHFUL_REPORTING,
)
from decepticon.agents.prompts.builder import (
    _FINDING_PROTOCOL_POINTER as _FINDING_PROTOCOL_POINTER,
)
from decepticon.agents.prompts.builder import (
    _OPERATIONAL_ROLES as _OPERATIONAL_ROLES,
)
from decepticon.agents.prompts.builder import (
    _OUTPUT_DISCIPLINE as _OUTPUT_DISCIPLINE,
)
from decepticon.agents.prompts.builder import (
    _PROMPT_SEARCH_PATHS as _PROMPT_SEARCH_PATHS,
)
from decepticon.agents.prompts.builder import (
    _PROMPTS_DIR as _PROMPTS_DIR,
)
from decepticon.agents.prompts.builder import (
    _VERIFICATION_GATE as _VERIFICATION_GATE,
)
from decepticon.agents.prompts.builder import (
    CACHE_BOUNDARY as CACHE_BOUNDARY,
)
from decepticon.agents.prompts.builder import (
    PromptBuilder as PromptBuilder,
)
from decepticon.agents.prompts.builder import (
    _get_tool_prompt as _get_tool_prompt,
)
from decepticon.agents.prompts.builder import (
    _read_fragment as _read_fragment,
)
from decepticon.agents.prompts.builder import (
    load_prompt as load_prompt,
)
from decepticon.agents.prompts.builder import (
    log as log,
)
from decepticon.agents.prompts.registry import (
    _COUNTRY_TO_LANG as _COUNTRY_TO_LANG,
)
from decepticon.agents.prompts.registry import (
    _LANG_NAMES as _LANG_NAMES,
)
from decepticon.agents.prompts.registry import (
    build_language_policy as build_language_policy,
)
