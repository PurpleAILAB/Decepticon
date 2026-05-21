"""CPG — Code Property Graph tooling for the CPG Analyst agent.

Two implementation tiers:

1. **tree-sitter** (always-on, fast): AST-only. Good enough to enumerate
   functions, calls, and surface-level source/sink patterns via the
   bundled dictionaries.

2. **joern-cli** (optional, slow): Full CPG (AST + CFG + DDG). Required
   for actual reachability tracing. Activated by setting the
   ``JOERN_HOME`` env var to a joern install dir.

Both share the same public API surface — see ``cpg_inventory_languages``,
``cpg_parse_tree``, ``cpg_find_sources``, ``cpg_find_sinks``,
``cpg_reaches`` exported from this package.
"""

from __future__ import annotations

from decepticon.tools.cpg.inventory import cpg_inventory_languages
from decepticon.tools.cpg.parse import cpg_parse_tree
from decepticon.tools.cpg.taint import (
    SourceSinkFinding,
    cpg_find_sinks,
    cpg_find_sources,
    cpg_reaches,
)

__all__ = [
    "SourceSinkFinding",
    "cpg_find_sinks",
    "cpg_find_sources",
    "cpg_inventory_languages",
    "cpg_parse_tree",
    "cpg_reaches",
]
