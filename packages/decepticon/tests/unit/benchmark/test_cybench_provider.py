"""Tests for benchmark.providers.cybench.CybenchProvider.

Covers the pure / file-IO surface: task discovery from the upstream
``metadata/metadata.json`` layout, the docker-served-only v1 scope
(local-file tasks skipped), flag extraction from the final subtask,
per-task flag-format derivation, and literal-flag evaluation (transcript
+ workspace). Docker lifecycle (setup/teardown) is not exercised here —
it needs a live Docker daemon and the upstream suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.providers.cybench import CybenchProvider
from benchmark.schemas import Challenge, FilterConfig
from benchmark.state import BenchmarkRunState, BenchmarkStepResult


def _write_task(
    root: Path,
    rel: str,
    *,
    difficulty: str,
    categories: list[str],
    flag: str,
    docker: bool,
) -> Path:
    task_dir = root / rel
    (task_dir / "metadata").mkdir(parents=True)
    (task_dir / "metadata" / "metadata.json").write_text(
        json.dumps(
            {
                "categories": categories,
                "difficulty": difficulty,
                "easy_prompt": "easy",
                "hard_prompt": "hard",
                "tools": {"other": ["ssti"]},
                "subtasks": [
                    {"question": "lang?", "answer": "Java"},
                    {"question": "What is the flag?", "answer": flag},
                ],
            }
        )
    )
    if docker:
        (task_dir / "start_docker.sh").write_text("#!/bin/bash\n")
        (task_dir / "stop_docker.sh").write_text("#!/bin/bash\n")
    return task_dir


def _state(outputs: list[str]) -> BenchmarkRunState:
    s = BenchmarkRunState()
    s.step_history = [
        BenchmarkStepResult(objective_id="O", agent_used="a", outcome="x", raw_output=o)
        for o in outputs
    ]
    return s


class TestLoadChallenges:
    def test_discovers_docker_tasks_and_skips_local(self, tmp_path: Path) -> None:
        _write_task(
            tmp_path,
            "htb/web/[Easy] Labyrinth Linguist",
            difficulty="1",
            categories=["web"],
            flag="HTB{aaa}",
            docker=True,
        )
        _write_task(
            tmp_path,
            "htb/crypto/[Hard] Permuted",
            difficulty="3",
            categories=["crypto"],
            flag="HTB{bbb}",
            docker=False,  # no start_docker.sh -> skipped in v1
        )

        provider = CybenchProvider(benchmarks_dir=tmp_path)
        challenges = provider.load_challenges(FilterConfig())

        assert len(challenges) == 1
        c = challenges[0]
        assert c.id == "cybench-htb-web-easy-labyrinth-linguist"
        assert c.name == "Labyrinth Linguist"  # difficulty prefix stripped
        assert c.level == 1
        assert "web" in c.tags and "ssti" in c.tags
        assert c.expected_flag == "HTB{aaa}"
        assert c.flag_format == "HTB{...}"

    def test_skips_task_with_no_flag_shaped_answer(self, tmp_path: Path) -> None:
        """A docker task whose final answer isn't brace-shaped is unsolvable → skipped."""
        # flag "notaflag" has no braces -> _extract_flag returns None -> skipped.
        _write_task(
            tmp_path,
            "c/web/[Easy] NoFlag",
            difficulty="1",
            categories=["web"],
            flag="notaflag",
            docker=True,
        )
        provider = CybenchProvider(benchmarks_dir=tmp_path)
        assert provider.load_challenges(FilterConfig()) == []

    def test_tag_and_id_filters(self, tmp_path: Path) -> None:
        _write_task(
            tmp_path,
            "c/web/[Easy] A",
            difficulty="1",
            categories=["web"],
            flag="FL{a}",
            docker=True,
        )
        _write_task(
            tmp_path,
            "c/pwn/[Easy] B",
            difficulty="2",
            categories=["pwn"],
            flag="FL{b}",
            docker=True,
        )
        provider = CybenchProvider(benchmarks_dir=tmp_path)

        assert len(provider.load_challenges(FilterConfig(tags=["pwn"]))) == 1
        got = provider.load_challenges(FilterConfig(ids=["cybench-c-web-easy-a"]))
        assert len(got) == 1 and got[0].tags[0] == "web"


class TestEvaluate:
    def _challenge(self) -> Challenge:
        return Challenge(
            id="cybench-x",
            name="X",
            description="d",
            level=1,
            tags=["web"],
            expected_flag="HTB{correct_flag}",
            flag_format="HTB{...}",
        )

    def test_correct_flag_passes(self, tmp_path: Path) -> None:
        provider = CybenchProvider(benchmarks_dir=tmp_path)
        result = provider.evaluate(
            self._challenge(), _state(["the flag is HTB{correct_flag} done"]), tmp_path
        )
        assert result.passed is True
        assert result.flag_captured == "HTB{correct_flag}"

    def test_wrong_flag_fails_but_surfaces_token(self, tmp_path: Path) -> None:
        provider = CybenchProvider(benchmarks_dir=tmp_path)
        result = provider.evaluate(self._challenge(), _state(["got HTB{wrong}"]), tmp_path)
        assert result.passed is False
        assert result.flag_captured == "HTB{wrong}"

    def test_no_flag_fails(self, tmp_path: Path) -> None:
        provider = CybenchProvider(benchmarks_dir=tmp_path)
        result = provider.evaluate(self._challenge(), _state(["nothing here"]), tmp_path)
        assert result.passed is False
        assert result.flag_captured is None

    def test_flag_in_workspace_file_passes(self, tmp_path: Path) -> None:
        (tmp_path / "loot.txt").write_text("recovered HTB{correct_flag}\n")
        provider = CybenchProvider(benchmarks_dir=tmp_path)
        result = provider.evaluate(self._challenge(), _state([""]), tmp_path)
        assert result.passed is True
