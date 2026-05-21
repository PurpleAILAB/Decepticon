"""Failure-analysis feedback loop for benchmark runs.

MDASH categorized its CyberGym misses (82% from vague descriptions, 13%
harness-format mismatches) and fed that taxonomy back into the system.
Decepticon's harness already captures rich postmortem evidence per
challenge (``error``, ``agent_summary``, ``cancel_outcome``,
``terminal_status_at_teardown``) — but nothing consumes the *failures*.

This module turns a ``BenchmarkReport`` into a categorized failure
taxonomy with actionable remediation pointers. A deterministic pre-pass
classifies the unambiguous infrastructure/timeout failures; an optional
LLM classifies the rest from the agent summary. The output is a
human-readable report a maintainer reads to fix the flagged skills and
prompts — auto-rewriting prompts is deliberately out of scope.
"""

from __future__ import annotations

import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from benchmark.schemas import BenchmarkReport, ChallengeResult
from decepticon.core.logging import get_logger

log = get_logger("benchmark.failure_analysis")


class FailureCategory(StrEnum):
    """Taxonomy of why a benchmark challenge failed."""

    RECON_INCOMPLETE = "recon_incomplete"
    EXPLOIT_TECHNIQUE_GAP = "exploit_technique_gap"
    SKILL_COVERAGE_GAP = "skill_coverage_gap"
    WRONG_SKILL_ROUTED = "wrong_skill_routed"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    SANDBOX_INFRA_FAILURE = "sandbox_infra_failure"
    TIMEOUT_BUDGET_EXHAUSTED = "timeout_budget_exhausted"
    MODEL_REFUSAL_OR_LOOP = "model_refusal_or_loop"
    FLAG_FORMAT_MISMATCH = "flag_format_mismatch"
    OBJECTIVE_AMBIGUITY = "objective_ambiguity"
    HARNESS_SCORING_ERROR = "harness_scoring_error"
    UNKNOWN = "unknown"


# Default remediation pointer per category — where a maintainer should look.
REMEDIATION: dict[FailureCategory, str] = {
    FailureCategory.RECON_INCOMPLETE: (
        "Strengthen recon skills/prompt — the agent never mapped the attack surface."
    ),
    FailureCategory.EXPLOIT_TECHNIQUE_GAP: (
        "Found the surface but failed exploitation — review the exploit agent's skills."
    ),
    FailureCategory.SKILL_COVERAGE_GAP: (
        "No skill covers the technique needed — author a new skill under skills/."
    ),
    FailureCategory.WRONG_SKILL_ROUTED: (
        "Skill knowledge graph routed to irrelevant skills — check MITRE mappings."
    ),
    FailureCategory.TOOL_EXECUTION_ERROR: (
        "A tool/bash call failed — investigate the tool surface or sandbox image."
    ),
    FailureCategory.SANDBOX_INFRA_FAILURE: (
        "Container/network failure — a harness/infra issue, not an agent capability gap."
    ),
    FailureCategory.TIMEOUT_BUDGET_EXHAUSTED: (
        "Ran out of time — raise --timeout or tighten the agent's operating loop."
    ),
    FailureCategory.MODEL_REFUSAL_OR_LOOP: (
        "Model refused or looped — review the system prompt and recursion limit."
    ),
    FailureCategory.FLAG_FORMAT_MISMATCH: (
        "Flag captured but in the wrong format — clarify the flag-format brief."
    ),
    FailureCategory.OBJECTIVE_AMBIGUITY: (
        "OPPLAN objective too vague — add file/function identifiers to objectives."
    ),
    FailureCategory.HARNESS_SCORING_ERROR: (
        "Possible false negative in scoring — verify the provider's evaluate()."
    ),
    FailureCategory.UNKNOWN: "Unclassified — inspect the trace manually.",
}


class FailureRecord(BaseModel):
    """One classified challenge failure."""

    challenge_id: str
    category: FailureCategory
    evidence: str = Field(default="", description="What in the postmortem drove the classification")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suggested_fix: str = Field(default="", description="Which skill / prompt / file to improve")


class FailureTaxonomy(BaseModel):
    """Aggregated failure taxonomy for a benchmark batch."""

    total_failures: int
    by_category: dict[str, int] = Field(default_factory=dict)
    percentages: dict[str, float] = Field(default_factory=dict)
    records: list[FailureRecord] = Field(default_factory=list)
    top_remediations: list[str] = Field(default_factory=list)


class _LLMFailureClassification(BaseModel):
    """Structured-output target for LLM-based failure classification."""

    category: str = Field(description="One FailureCategory value")
    evidence: str = Field(default="", description="The postmortem signal that drove the verdict")
    suggested_fix: str = Field(default="", description="Which skill / prompt / file to improve")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_CLASSIFY_PROMPT = """You are triaging why an autonomous red-team agent failed a \
security benchmark challenge. Classify the failure into exactly one category.

Categories: {categories}

CHALLENGE: {challenge_id} — {challenge_name}
TAGS: {tags}
ERROR: {error}
CANCEL OUTCOME: {cancel_outcome}
TERMINAL STATUS: {terminal_status}
AGENT SUMMARY:
{agent_summary}

Pick the single best category, cite the specific evidence, and suggest which \
skill, prompt, or file a maintainer should improve."""


def _deterministic_category(result: ChallengeResult) -> FailureCategory | None:
    """Classify the unambiguous infra/timeout failures without an LLM."""
    error = (result.error or "").lower()
    if result.cancel_outcome == "container_restart":
        return FailureCategory.SANDBOX_INFRA_FAILURE
    if "timeout" in error or "timed out" in error:
        return FailureCategory.TIMEOUT_BUDGET_EXHAUSTED
    if any(s in error for s in ("connection refused", "unreachable", "proxy", "docker")):
        return FailureCategory.SANDBOX_INFRA_FAILURE
    if any(s in error for s in ("rate limit", "429", "401", "invalid_api_key")):
        return FailureCategory.TOOL_EXECUTION_ERROR
    if result.flag_captured and not result.passed:
        return FailureCategory.FLAG_FORMAT_MISMATCH
    return None


def _coerce_category(value: str) -> FailureCategory:
    try:
        return FailureCategory(str(value).strip().lower())
    except ValueError:
        return FailureCategory.UNKNOWN


def classify_failure(result: ChallengeResult, *, llm: Any = None) -> FailureRecord:
    """Classify a single failed challenge.

    A deterministic pre-pass handles infra/timeout/flag-format failures.
    When ``llm`` is provided, the residual is classified from the agent
    summary; otherwise it is recorded as ``UNKNOWN``.
    """
    deterministic = _deterministic_category(result)
    if deterministic is not None:
        return FailureRecord(
            challenge_id=result.challenge_id,
            category=deterministic,
            evidence=(result.error or result.cancel_outcome or "")[:300],
            confidence=1.0,
            suggested_fix=REMEDIATION[deterministic],
        )

    if llm is None:
        return FailureRecord(
            challenge_id=result.challenge_id,
            category=FailureCategory.UNKNOWN,
            evidence=(result.agent_summary or result.error or "")[:300],
            confidence=0.0,
            suggested_fix=REMEDIATION[FailureCategory.UNKNOWN],
        )

    prompt = _CLASSIFY_PROMPT.format(
        categories=", ".join(c.value for c in FailureCategory),
        challenge_id=result.challenge_id,
        challenge_name=result.challenge_name,
        tags=", ".join(result.tags),
        error=result.error or "(none)",
        cancel_outcome=result.cancel_outcome or "(none)",
        terminal_status=result.terminal_status_at_teardown or "(none)",
        agent_summary=result.agent_summary or "(no summary captured)",
    )
    try:
        raw: _LLMFailureClassification = llm.with_structured_output(
            _LLMFailureClassification
        ).invoke(prompt)
    except Exception as exc:  # noqa: BLE001 — classification must never crash the report
        log.warning("LLM failure classification failed for %s: %s", result.challenge_id, exc)
        return FailureRecord(
            challenge_id=result.challenge_id,
            category=FailureCategory.UNKNOWN,
            evidence=f"LLM classification error: {exc}",
            confidence=0.0,
        )
    category = _coerce_category(raw.category)
    return FailureRecord(
        challenge_id=result.challenge_id,
        category=category,
        evidence=raw.evidence[:300],
        confidence=raw.confidence,
        suggested_fix=raw.suggested_fix or REMEDIATION[category],
    )


def _load_report(source: BenchmarkReport | str | Path) -> BenchmarkReport:
    if isinstance(source, BenchmarkReport):
        return source
    path = Path(source)
    if path.is_dir():
        path = path / "report.json"
    return BenchmarkReport.model_validate(json.loads(path.read_text(encoding="utf-8")))


def analyze_batch(source: BenchmarkReport | str | Path, *, llm: Any = None) -> FailureTaxonomy:
    """Classify every failed challenge in a batch into a taxonomy."""
    report = _load_report(source)
    failures = [r for r in report.results if not r.passed]
    records = [classify_failure(r, llm=llm) for r in failures]

    counts = Counter(r.category.value for r in records)
    total = len(records)
    percentages = {cat: round(100.0 * n / total, 1) for cat, n in counts.items()} if total else {}

    top_remediations: list[str] = []
    for cat_value, n in counts.most_common():
        category = FailureCategory(cat_value)
        top_remediations.append(f"[{cat_value} ×{n}] {REMEDIATION[category]}")

    return FailureTaxonomy(
        total_failures=total,
        by_category=dict(counts),
        percentages=percentages,
        records=records,
        top_remediations=top_remediations,
    )


def render_taxonomy_markdown(taxonomy: FailureTaxonomy) -> str:
    """Render a failure taxonomy as a human-readable Markdown report."""
    lines = ["# Benchmark Failure Analysis", ""]
    lines.append(f"**Total failures classified:** {taxonomy.total_failures}")
    lines.append("")
    if taxonomy.total_failures == 0:
        lines.append("No failures — every challenge passed.")
        return "\n".join(lines) + "\n"

    lines.append("## Failures by category")
    lines.append("")
    lines.append("| Category | Count | Share |")
    lines.append("|----------|-------|-------|")
    for cat, count in sorted(taxonomy.by_category.items(), key=lambda kv: -kv[1]):
        pct = taxonomy.percentages.get(cat, 0.0)
        lines.append(f"| {cat} | {count} | {pct}% |")
    lines.append("")

    lines.append("## Top remediations")
    lines.append("")
    for item in taxonomy.top_remediations:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Per-challenge")
    lines.append("")
    lines.append("| Challenge | Category | Confidence | Evidence |")
    lines.append("|-----------|----------|------------|----------|")
    for rec in taxonomy.records:
        evidence = rec.evidence.replace("\n", " ").replace("|", "/")[:120]
        lines.append(
            f"| {rec.challenge_id} | {rec.category.value} | {rec.confidence:.2f} | {evidence} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_failure_analysis(taxonomy: FailureTaxonomy, batch_dir: str | Path) -> tuple[Path, Path]:
    """Write ``failure-analysis.{json,md}`` into a batch directory."""
    out_dir = Path(batch_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "failure-analysis.json"
    md_path = out_dir / "failure-analysis.md"
    json_path.write_text(json.dumps(taxonomy.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(render_taxonomy_markdown(taxonomy), encoding="utf-8")
    return json_path, md_path
