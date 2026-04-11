"""Finding export + report generation.

- ``hackerone``   — HackerOne markdown template renderer
- ``bugcrowd``    — Bugcrowd submission CSV writer
- ``executive``   — Engagement-level executive summary composer
- ``timeline``    — Chronological event timeline extractor

Renderers operate on ``KnowledgeGraph`` state so the same graph can
feed a bounty submission, an engagement executive summary, and a
JSON bundle for further automation.
"""

from __future__ import annotations

from decepticon.tools.reporting.bugcrowd import render_bugcrowd_csv
from decepticon.tools.reporting.executive import render_executive_summary
from decepticon.tools.reporting.hackerone import HackerOneReport, render_hackerone_markdown
from decepticon.tools.reporting.timeline import extract_timeline

__all__ = [
    "HackerOneReport",
    "extract_timeline",
    "render_bugcrowd_csv",
    "render_executive_summary",
    "render_hackerone_markdown",
]
