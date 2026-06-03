"""ReportTemplate — converts ReportDraft into platform-native markdown.

Decoupled from PlatformAdapter so multiple platforms with similar
conventions can share a template (e.g. ``bounty-classic-v1`` for both
HackerOne and Bugcrowd). Templates register via the
``decepticon.report_templates`` entry-point group.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from decepticon_core.types.bounty import ReportDraft

__all__ = ["ReportTemplate"]


@runtime_checkable
class ReportTemplate(Protocol):
    """Renderer from ReportDraft → platform-ready markdown body."""

    template_id: str
    """Registry key, e.g. ``"hackerone-v1"``."""

    def render(self, draft: ReportDraft, *, locale: str = "en") -> str:
        """Return the markdown body the adapter will submit.

        ``locale`` is a 2-letter ISO 639-1 code. Templates that don't
        support a locale fall back to ``"en"`` silently rather than
        raising — that's the orchestrator's contract with multilingual
        programs.
        """
        ...
