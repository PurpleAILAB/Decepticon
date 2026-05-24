"""PEP 562 compat shim identity preservation.

Closes the test coverage gap flagged in the design review (Nit #4 of
the critic findings on PR #276). The six shims at
``packages/decepticon/src/decepticon/{core/schemas,llm/models,...}.py``
use ``__getattr__`` to delegate to the canonical
``decepticon_core.*`` modules. Identity is a structural property of
the shim — these tests prove it.
"""

from __future__ import annotations

import warnings


def test_schemas_identity_preservation() -> None:
    """``RoE`` from the legacy and canonical paths must be the SAME class."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from decepticon.core.schemas import RoE as RoE_legacy
        from decepticon_core.types.engagement import RoE as RoE_canonical

    assert RoE_legacy is RoE_canonical, (
        "shim must hand back the canonical class object, not a wrapper"
    )


def test_llm_models_identity_preservation() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from decepticon.llm.models import ModelProfile as MP_legacy
        from decepticon_core.types.llm import ModelProfile as MP_canonical

    assert MP_legacy is MP_canonical


def test_plugin_loader_identity_preservation() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from decepticon.plugin_loader import PluginBundle as PB_legacy
        from decepticon_core.plugin_loader import PluginBundle as PB_canonical

    assert PB_legacy is PB_canonical


def test_research_graph_identity_preservation() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from decepticon.tools.research.graph import Node as N_legacy
        from decepticon_core.types.kg import Node as N_canonical

    assert N_legacy is N_canonical


def test_dunder_lookup_does_not_warn() -> None:
    """Python's ``__path__`` probe during ``from X import Y`` must NOT
    emit a DeprecationWarning — the shim's ``__getattr__`` filters
    underscore-prefixed names.
    """
    with warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter("always")
        # Trigger a __path__ probe by importing from the shim module.
        import decepticon.core.schemas as _shim

        # Access a dunder explicitly through the module.
        try:
            _shim.__path__  # noqa: B018
        except AttributeError:
            # shim explicitly raises AttributeError on _-prefixed names; that's the contract
            pass

    dunder_warnings = [
        w for w in ws if issubclass(w.category, DeprecationWarning) and "__" in str(w.message)
    ]
    assert dunder_warnings == [], (
        f"shim must not emit DeprecationWarning for dunder lookups; "
        f"got {[str(w.message) for w in dunder_warnings]}"
    )


def test_explicit_warning_on_legacy_attribute() -> None:
    """Confirm the per-attribute DeprecationWarning fires exactly once."""
    # Reset the shim's _seen cache to test the first-access behavior.
    import decepticon.core.schemas as schemas_shim

    schemas_shim._seen.clear()

    with warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter("always")
        _ = schemas_shim.RoE
        _ = schemas_shim.RoE  # second access -> no new warning

    matching = [
        w for w in ws if issubclass(w.category, DeprecationWarning) and "RoE" in str(w.message)
    ]
    assert len(matching) == 1, (
        f"shim must warn exactly once per attribute on first access; got {len(matching)}"
    )
