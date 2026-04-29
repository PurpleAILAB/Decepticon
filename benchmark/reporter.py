from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from benchmark.schemas import BenchmarkReport, ChallengeResult


class Reporter:
    """Writes benchmark reports to disk in JSON and Markdown formats."""

    def __init__(self, results_dir: Path) -> None:
        self.results_dir = results_dir
        self.evidence_dir = results_dir / "evidence"

    def _stem(self, report: BenchmarkReport) -> str:
        """Return the filename stem for this report.

        Format:
          - single challenge: ``<challenge_id>_<UTC-timestamp>``
          - multi-challenge batch: ``batch-<UTC-timestamp>``

        The timestamp suffix preserves history across repeat runs of the same
        challenge (self-improvement loop reruns the same id many times) while
        still keeping each file scannable by challenge name.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if len(report.results) == 1:
            return f"{report.results[0].challenge_id}_{ts}"
        return f"batch-{ts}"

    def write_json(self, report: BenchmarkReport) -> Path:
        """Write the report as a JSON file and return its path."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / f"{self._stem(report)}.json"
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_markdown(self, report: BenchmarkReport) -> Path:
        """Write the report as a Markdown file and return its path."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / f"{self._stem(report)}.md"

        lines: list[str] = []
        lines.append(f"# Benchmark Report — {report.provider_name}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total | {report.total} |")
        lines.append(f"| Passed | {report.passed} |")
        lines.append(f"| Failed | {report.failed} |")
        lines.append(f"| Pass Rate | {report.pass_rate:.1%} |")
        lines.append(f"| Duration | {report.duration_seconds:.1f}s |")
        lines.append("")
        lines.append("## Results by Level")
        lines.append("")
        lines.append("| Level | Total | Passed | Pass Rate |")
        lines.append("|-------|-------|--------|-----------|")
        for level in sorted(report.by_level):
            entry = report.by_level[level]
            lines.append(
                f"| {level} | {entry['total']} | {entry['passed']} | {entry['pass_rate']:.1%} |"
            )
        lines.append("")
        lines.append("## Results by Tag")
        lines.append("")
        lines.append("| Tag | Total | Passed | Pass Rate |")
        lines.append("|-----|-------|--------|-----------|")
        for tag in sorted(report.by_tag):
            entry = report.by_tag[tag]
            lines.append(
                f"| {tag} | {entry['total']} | {entry['passed']} | {entry['pass_rate']:.1%} |"
            )
        lines.append("")
        lines.append("## Individual Results")
        lines.append("")
        lines.append("| ID | Name | Level | Result | Duration | Error |")
        lines.append("|----|------|-------|--------|----------|-------|")
        for r in report.results:
            result_str = "PASS" if r.passed else "FAIL"
            error_str = r.error or ""
            lines.append(
                f"| {r.challenge_id} | {r.challenge_name} | {r.level} "
                f"| {result_str} | {r.duration_seconds:.1f}s | {error_str} |"
            )
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def write_evidence(self, report: BenchmarkReport) -> Path:
        """Write per-challenge solve evidence files for public reporting."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        run_dir = self.evidence_dir / self._stem(report)
        run_dir.mkdir(parents=True, exist_ok=True)

        for result in report.results:
            self._write_challenge_evidence(run_dir, result)

        # Write summary index
        index = {
            "provider": report.provider_name,
            "stem": self._stem(report),
            "total": report.total,
            "passed": report.passed,
            "pass_rate": report.pass_rate,
            "challenges": [
                {
                    "id": r.challenge_id,
                    "name": r.challenge_name,
                    "level": r.level,
                    "passed": r.passed,
                    "duration_seconds": r.duration_seconds,
                    "thread_id": r.thread_id,
                }
                for r in report.results
            ],
        }
        index_path = run_dir / "index.json"
        index_path.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")
        return run_dir

    def _write_challenge_evidence(self, run_dir: Path, result: ChallengeResult) -> None:
        """Write JSON and Markdown evidence for a single challenge."""
        evidence = {
            "challenge_id": result.challenge_id,
            "challenge_name": result.challenge_name,
            "level": result.level,
            "tags": result.tags,
            "passed": result.passed,
            "flag_captured": result.flag_captured,
            "duration_seconds": result.duration_seconds,
            "thread_id": result.thread_id,
            "token_count": result.token_count,
            "error": result.error,
        }
        json_path = run_dir / f"{result.challenge_id}.json"
        json_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")

        lines = [
            f"# {result.challenge_id}: {result.challenge_name}",
            "",
            f"**Result:** {'PASS' if result.passed else 'FAIL'}",
            f"**Level:** {result.level}",
            f"**Tags:** {', '.join(result.tags)}",
            f"**Duration:** {result.duration_seconds:.1f}s",
        ]
        if result.flag_captured:
            lines.append(f"**Flag:** `{result.flag_captured}`")
        if result.thread_id:
            lines.append(f"**Thread ID:** `{result.thread_id}`")
        if result.token_count:
            lines.append(f"**Tokens:** {result.token_count:,}")
        if result.error:
            lines.append(f"**Error:** {result.error}")
        if result.agent_summary:
            lines.extend(["", "## Agent Summary", "", result.agent_summary])
        lines.append("")

        md_path = run_dir / f"{result.challenge_id}.md"
        md_path.write_text("\n".join(lines), encoding="utf-8")
