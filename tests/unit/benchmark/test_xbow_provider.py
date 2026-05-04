"""Tests for benchmark.providers.xbow.XBOWProvider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmark.providers.xbow import XBOWProvider
from benchmark.schemas import Challenge, FilterConfig
from benchmark.state import BenchmarkRunState, BenchmarkStepResult


def _create_mock_benchmarks(tmp_path: Path) -> Path:
    """Create a mock benchmarks directory with 3 challenges."""
    benchmarks_dir = tmp_path / "benchmarks"
    for i, (level, tags) in enumerate(
        [
            (1, ["xss"]),
            (2, ["sqli", "idor"]),
            (3, ["ssti"]),
        ],
        start=1,
    ):
        challenge_dir = benchmarks_dir / f"XBEN-{i:03d}-24"
        challenge_dir.mkdir(parents=True)
        (challenge_dir / "benchmark.json").write_text(
            json.dumps(
                {
                    "name": f"XBEN-{i:03d}-24 Test Challenge {i}",
                    "description": f"Test challenge {i}",
                    "level": str(level),
                    "tags": tags,
                    "win_condition": "flag",
                }
            )
        )
    return benchmarks_dir


def _mock_state(raw_outputs: list[str]) -> BenchmarkRunState:
    """Create a mock benchmark state with iteration results."""
    state = BenchmarkRunState()
    state.step_history = [
        BenchmarkStepResult(
            objective_id="OBJ-001",
            agent_used="test-agent",
            outcome="PASSED",
            raw_output=output,
        )
        for output in raw_outputs
    ]
    return state


class TestLoadChallenges:
    def test_load_challenges_parses_benchmark_json(self, tmp_path: Path) -> None:
        """Load challenges from mock benchmark.json files and verify parsing."""
        benchmarks_dir = _create_mock_benchmarks(tmp_path)
        provider = XBOWProvider(benchmarks_dir=benchmarks_dir)

        challenges = provider.load_challenges(FilterConfig())

        assert len(challenges) == 3
        assert challenges[0].id == "XBEN-001-24"
        assert challenges[0].level == 1
        assert challenges[0].tags == ["xss"]
        assert challenges[1].id == "XBEN-002-24"
        assert challenges[1].level == 2
        assert challenges[1].tags == ["sqli", "idor"]
        assert challenges[2].id == "XBEN-003-24"
        assert challenges[2].level == 3

    def test_load_challenges_level_filter(self, tmp_path: Path) -> None:
        """Verify level filtering works."""
        benchmarks_dir = _create_mock_benchmarks(tmp_path)
        provider = XBOWProvider(benchmarks_dir=benchmarks_dir)

        challenges = provider.load_challenges(FilterConfig(levels=[1, 3]))

        assert len(challenges) == 2
        assert challenges[0].level == 1
        assert challenges[1].level == 3

    def test_load_challenges_tag_filter(self, tmp_path: Path) -> None:
        """Verify tag filtering (ANY match)."""
        benchmarks_dir = _create_mock_benchmarks(tmp_path)
        provider = XBOWProvider(benchmarks_dir=benchmarks_dir)

        challenges = provider.load_challenges(FilterConfig(tags=["idor"]))

        assert len(challenges) == 1
        assert challenges[0].id == "XBEN-002-24"
        assert "idor" in challenges[0].tags

    def test_load_challenges_range_filter(self, tmp_path: Path) -> None:
        """Verify range-based subsetting (1-based)."""
        benchmarks_dir = _create_mock_benchmarks(tmp_path)
        provider = XBOWProvider(benchmarks_dir=benchmarks_dir)

        # range_start=2, range_end=3 should return challenges 2 and 3 (1-based)
        challenges = provider.load_challenges(FilterConfig(range_start=2, range_end=3))

        assert len(challenges) == 2
        assert challenges[0].id == "XBEN-002-24"
        assert challenges[1].id == "XBEN-003-24"


class TestFlagHash:
    def test_flag_hash_deterministic(self) -> None:
        """Verify SHA256(BENCHMARK_NAME.upper()) produces consistent flag."""
        challenge_id = "XBEN-001-24"
        expected_hash = hashlib.sha256(challenge_id.upper().encode()).hexdigest()
        expected_flag = f"FLAG{{{expected_hash}}}"

        # Compute twice to verify determinism
        hash1 = hashlib.sha256(challenge_id.upper().encode()).hexdigest()
        hash2 = hashlib.sha256(challenge_id.upper().encode()).hexdigest()

        assert hash1 == hash2
        assert f"FLAG{{{hash1}}}" == expected_flag


class TestEvaluate:
    def _challenge(self, tmp_path: Path) -> Challenge:
        return Challenge(
            id="XBEN-001-24",
            name="Test Challenge",
            description="Test",
            level=1,
            tags=["xss"],
            compose_dir=tmp_path,
        )

    def test_evaluate_flag_found(self, tmp_path: Path) -> None:
        """raw_output containing correct flag -> passed=True."""
        challenge = self._challenge(tmp_path)
        flag_value = hashlib.sha256(challenge.id.upper().encode()).hexdigest()
        correct_flag = f"FLAG{{{flag_value}}}"

        state = _mock_state([f"Found the flag: {correct_flag}"])
        provider = XBOWProvider(benchmarks_dir=tmp_path)

        result = provider.evaluate(challenge, state, tmp_path)

        assert result.passed is True
        assert result.flag_captured == correct_flag

    def test_evaluate_flag_not_found(self, tmp_path: Path) -> None:
        """raw_output without flag -> passed=False."""
        challenge = self._challenge(tmp_path)

        state = _mock_state(["No flags found in this output"])
        provider = XBOWProvider(benchmarks_dir=tmp_path)

        result = provider.evaluate(challenge, state, tmp_path)

        assert result.passed is False
        assert result.flag_captured is None

    def test_evaluate_wrong_flag(self, tmp_path: Path) -> None:
        """raw_output with wrong FLAG{} -> passed=False."""
        challenge = self._challenge(tmp_path)
        wrong_flag = "FLAG{0000000000000000000000000000000000000000000000000000000000000000}"

        state = _mock_state([f"Got flag: {wrong_flag}"])
        provider = XBOWProvider(benchmarks_dir=tmp_path)

        result = provider.evaluate(challenge, state, tmp_path)

        assert result.passed is False
        assert result.flag_captured == wrong_flag
