"""Utility modules for the Decepticon contract layer.

Pure stdlib + pydantic helpers — config loaders, logging setup. Imported
by the framework (``decepticon_core.utils.config``, ``decepticon_core.utils.logging``
shims) and freely usable by plugin authors.
"""

from __future__ import annotations

from decepticon_core.utils import config, logging

__all__ = ["config", "logging"]
