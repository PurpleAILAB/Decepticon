"""LLM red-team tools — promptfoo, garak, PyRIT wrappers.

The LLM-redteam agent calls these tools via the standard bash tool +
this package's helpers. Each tool here wraps a CLI invocation that the
sandbox can exec.
"""

from __future__ import annotations

from decepticon.tools.airedteam.promptfoo import (
    promptfoo_eval,
    promptfoo_redteam_init,
)

__all__ = ["promptfoo_eval", "promptfoo_redteam_init"]
