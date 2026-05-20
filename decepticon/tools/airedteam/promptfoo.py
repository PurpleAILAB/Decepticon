"""promptfoo wrapper — LLM red-team eval framework.

Thin shell wrapper for promptfoo (https://github.com/promptfoo/promptfoo).
Two operations LLM-redteam agents need:

1. ``promptfoo_redteam_init`` — generate a redteam.yaml config tuned to
   the target's surface profile (model, tools, RAG, memory). Calls
   ``promptfoo redteam init --interactive=false``-equivalent.

2. ``promptfoo_eval`` — run an eval suite and parse the JSON results.
   Returns per-test pass/fail + AATMF-classification hints from
   promptfoo's plugin metadata.

Both operations assume promptfoo is installed in the sandbox via
``npx -y promptfoo@latest`` or ``npm i -g promptfoo``. The wrapper
shells out via subprocess directly — no FastMCP layer needed since
the LLM-redteam agent loads this as a regular Python helper.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PromptfooEvalResult:
    """Result of one promptfoo eval run."""

    success: bool
    config_path: str
    results_path: str | None
    total_tests: int
    passed: int
    failed: int
    findings: list[dict]  # raw promptfoo result items where assertion failed
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "success": self.success,
            "config_path": self.config_path,
            "results_path": self.results_path,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "findings": self.findings,
            "error": self.error,
        }


def _promptfoo_binary() -> list[str]:
    """Locate promptfoo (binary or npx fallback)."""
    if shutil.which("promptfoo"):
        return ["promptfoo"]
    if shutil.which("npx"):
        return ["npx", "-y", "promptfoo@latest"]
    raise RuntimeError(
        "promptfoo not installed. Run `npm install -g promptfoo` "
        "or ensure `npx` is on PATH."
    )


def promptfoo_redteam_init(
    target_url: str,
    *,
    output_dir: Path,
    purpose: str = "Web application LLM assistant",
    plugins: list[str] | None = None,
    strategies: list[str] | None = None,
    num_tests: int = 5,
) -> dict:
    """Generate a redteam.yaml for the given target.

    promptfoo's redteam-init writes config that defines:
    - the target endpoint (LLM API or HTTP wrapper)
    - the purpose of the system (for context-aware prompts)
    - plugins (vuln-class probes: harmful, jailbreak, pii, system-prompt-override, hijacking, ...)
    - strategies (delivery mechanisms: basic, jailbreak, multilingual, base64, etc)

    Args:
        target_url: HTTP endpoint exposing the LLM (e.g.
            "https://target.com/api/chat").
        output_dir: Directory where redteam.yaml + auxiliary files land.
        purpose: One-line description of what the LLM does. Drives
            promptfoo's context-aware probe generation.
        plugins: List of plugin names. None → reasonable default.
        strategies: Delivery strategies. None → reasonable default.
        num_tests: Tests per plugin.

    Returns:
        dict w/ {success, config_path, error}.
    """
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    plugins = plugins or [
        "harmful",  # toxic / harmful output generation
        "jailbreak",  # bypass safety guardrails
        "pii",  # PII leak (training data + user-provided)
        "system-prompt-override",  # T10 system prompt extraction
        "hijacking",  # T11 agentic / tool-call hijack
        "indirect-prompt-injection",  # T1 indirect injection via RAG/inputs
        "competitors",  # info-leak about competitor products
        "imitation",  # T8 persona impersonation
        "overreliance",  # epistemic-trust attack vector
        "ascii-smuggling",  # T1 ASCII smuggling
        "policy",  # custom policy violation
    ]
    strategies = strategies or [
        "basic",
        "jailbreak",
        "jailbreak:tree",
        "multilingual",
        "base64",
        "rot13",
        "leetspeak",
        "best-of-n",
        "math-prompt",
    ]

    config = {
        "description": f"Decepticon LLM red-team: {purpose}",
        "targets": [{"id": f"http:{target_url}", "label": "target"}],
        "redteam": {
            "purpose": purpose,
            "plugins": [{"id": p, "numTests": num_tests} for p in plugins],
            "strategies": strategies,
        },
    }
    import yaml
    config_path = output_dir / "redteam.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    return {
        "success": True,
        "config_path": str(config_path),
        "plugins": plugins,
        "strategies": strategies,
    }


def promptfoo_eval(
    config_path: str,
    *,
    output_path: str | None = None,
    timeout_s: int = 1800,
) -> PromptfooEvalResult:
    """Run a promptfoo eval suite and parse results.

    Args:
        config_path: Path to the redteam.yaml / promptfoo.yaml.
        output_path: Where to write JSON results. Default
            ``<config_dir>/results.json``.
        timeout_s: Subprocess timeout. Default 30 min — large suites
            take time.

    Returns:
        PromptfooEvalResult with per-test pass/fail and the raw
        failure list (the LLM-redteam agent's "findings" candidate
        set, pending AATMF classification + verifier gate).
    """
    config_abs = Path(config_path).resolve()
    output_abs = (
        Path(output_path).resolve()
        if output_path
        else config_abs.parent / "results.json"
    )

    cmd = _promptfoo_binary() + [
        "eval",
        "-c", str(config_abs),
        "--output", str(output_abs),
    ]

    try:
        proc = subprocess.run(cmd, timeout=timeout_s, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return PromptfooEvalResult(
            success=False,
            config_path=str(config_abs),
            results_path=None,
            total_tests=0,
            passed=0,
            failed=0,
            findings=[],
            error=f"promptfoo eval exceeded {timeout_s}s timeout",
        )
    except FileNotFoundError as e:
        return PromptfooEvalResult(
            success=False,
            config_path=str(config_abs),
            results_path=None,
            total_tests=0,
            passed=0,
            failed=0,
            findings=[],
            error=str(e),
        )

    if not output_abs.exists():
        return PromptfooEvalResult(
            success=False,
            config_path=str(config_abs),
            results_path=None,
            total_tests=0,
            passed=0,
            failed=0,
            findings=[],
            error=f"promptfoo exited {proc.returncode}; no results file at {output_abs}. stderr: {proc.stderr[:500]}",
        )

    try:
        data = json.loads(output_abs.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return PromptfooEvalResult(
            success=False,
            config_path=str(config_abs),
            results_path=str(output_abs),
            total_tests=0,
            passed=0,
            failed=0,
            findings=[],
            error=f"failed to parse results: {e}",
        )

    # promptfoo JSON shape: { "results": { "results": [...], "stats": {...} } }
    results_obj = data.get("results", {}) if isinstance(data, dict) else {}
    inner = results_obj.get("results", [])
    stats = results_obj.get("stats", {})

    passed = int(stats.get("successes", 0))
    failed = int(stats.get("failures", 0))
    total = passed + failed if (passed + failed) else len(inner)

    # "findings" = test items where the assertion failed (model output
    # broke the safety/security contract). Promote these to the
    # LLM-redteam agent's finding pipeline.
    findings = [
        {
            "id": item.get("id"),
            "prompt": item.get("prompt", {}).get("raw"),
            "response": item.get("response", {}).get("output"),
            "test_name": (item.get("testCase") or {}).get("description"),
            "assertion": (item.get("gradingResult") or {}).get("reason"),
            "plugin": (item.get("testCase") or {}).get("metadata", {}).get("pluginId"),
            "strategy": (item.get("testCase") or {}).get("metadata", {}).get("strategyId"),
            "score": (item.get("gradingResult") or {}).get("score"),
        }
        for item in inner
        if (item.get("success") is False) or ((item.get("gradingResult") or {}).get("pass") is False)
    ]

    return PromptfooEvalResult(
        success=True,
        config_path=str(config_abs),
        results_path=str(output_abs),
        total_tests=total,
        passed=passed,
        failed=failed,
        findings=findings,
        error=None,
    )


__all__ = ["PromptfooEvalResult", "promptfoo_eval", "promptfoo_redteam_init"]
