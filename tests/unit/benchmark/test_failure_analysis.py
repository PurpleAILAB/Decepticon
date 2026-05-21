"""Unit tests for the benchmark failure-analysis feedback loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from benchmark.failure_analysis import (
    FailureCategory,
    FailureTaxonomy,
    _LLMFailureClassification,
    analyze_batch,
    classify_failure,
)
from benchmark.schemas import BenchmarkReport, ChallengeResult


def _result(cid: str, *, passed: bool, **kw) -> ChallengeResult:
    return ChallengeResult(
        challenge_id=cid,
        challenge_name=f"name-{cid}",
        level=kw.pop("level", 2),
        tags=kw.pop("tags", ["web"]),
        passed=passed,
        **kw,
    )


def _report(results: list[ChallengeResult]) -> BenchmarkReport:
    passed = sum(1 for r in results if r.passed)
    now = datetime.now(timezone.utc)
    return BenchmarkReport(
        provider_name="xbow",
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        pass_rate=passed / len(results) if results else 0.0,
        by_level={},
        by_tag={},
        results=results,
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
    )


class _FakeStructured:
    def __init__(self, obj):
        self._obj = obj

    def invoke(self, prompt):
        return self._obj


class _FakeLLM:
    def __init__(self, obj):
        self._obj = obj

    def with_structured_output(self, schema):
        return _FakeStructured(self._obj)


class TestDeterministicClassification:
    def test_timeout_error(self):
        rec = classify_failure(_result("c1", passed=False, error="run timed out after 1800s"))
        assert rec.category == FailureCategory.TIMEOUT_BUDGET_EXHAUSTED
        assert rec.confidence == 1.0

    def test_container_restart_is_infra(self):
        rec = classify_failure(_result("c2", passed=False, cancel_outcome="container_restart"))
        assert rec.category == FailureCategory.SANDBOX_INFRA_FAILURE

    def test_connection_refused_is_infra(self):
        rec = classify_failure(
            _result("c3", passed=False, error="LLM proxy unreachable: connection refused")
        )
        assert rec.category == FailureCategory.SANDBOX_INFRA_FAILURE

    def test_rate_limit_is_tool_error(self):
        rec = classify_failure(_result("c4", passed=False, error="provider rate limit (429)"))
        assert rec.category == FailureCategory.TOOL_EXECUTION_ERROR

    def test_flag_captured_but_failed_is_format_mismatch(self):
        rec = classify_failure(_result("c5", passed=False, flag_captured="flag{wrongcase}"))
        assert rec.category == FailureCategory.FLAG_FORMAT_MISMATCH

    def test_residual_without_llm_is_unknown(self):
        rec = classify_failure(
            _result("c6", passed=False, agent_summary="agent could not find an entry point")
        )
        assert rec.category == FailureCategory.UNKNOWN
        assert rec.confidence == 0.0


class TestLLMClassification:
    def test_llm_classifies_residual(self):
        llm = _FakeLLM(
            _LLMFailureClassification(
                category="recon_incomplete",
                evidence="never enumerated the host",
                suggested_fix="strengthen recon skill",
                confidence=0.8,
            )
        )
        rec = classify_failure(_result("c7", passed=False, agent_summary="gave up early"), llm=llm)
        assert rec.category == FailureCategory.RECON_INCOMPLETE
        assert rec.confidence == 0.8

    def test_llm_bad_category_coerced_to_unknown(self):
        llm = _FakeLLM(_LLMFailureClassification(category="nonsense-category", confidence=0.5))
        rec = classify_failure(_result("c8", passed=False, agent_summary="x"), llm=llm)
        assert rec.category == FailureCategory.UNKNOWN


class TestAnalyzeBatch:
    def test_aggregates_and_excludes_passed(self):
        report = _report(
            [
                _result("p1", passed=True),
                _result("f1", passed=False, error="timed out"),
                _result("f2", passed=False, error="timed out"),
                _result("f3", passed=False, cancel_outcome="container_restart"),
            ]
        )
        taxonomy = analyze_batch(report)
        assert taxonomy.total_failures == 3
        assert taxonomy.by_category["timeout_budget_exhausted"] == 2
        assert taxonomy.by_category["sandbox_infra_failure"] == 1
        assert taxonomy.percentages["timeout_budget_exhausted"] == round(200 / 3, 1)
        # Passed challenges never appear in records.
        assert all(r.challenge_id != "p1" for r in taxonomy.records)

    def test_top_remediations_ordered_by_frequency(self):
        report = _report(
            [
                _result("f1", passed=False, error="timed out"),
                _result("f2", passed=False, error="timed out"),
                _result("f3", passed=False, cancel_outcome="container_restart"),
            ]
        )
        taxonomy = analyze_batch(report)
        assert taxonomy.top_remediations[0].startswith("[timeout_budget_exhausted ×2]")

    def test_all_passed_yields_empty_taxonomy(self):
        report = _report([_result("p1", passed=True), _result("p2", passed=True)])
        taxonomy = analyze_batch(report)
        assert taxonomy.total_failures == 0
        assert taxonomy.records == []


def test_taxonomy_round_trips_through_json():
    report = _report([_result("f1", passed=False, error="timed out")])
    taxonomy = analyze_batch(report)
    restored = FailureTaxonomy.model_validate(
        json.loads(json.dumps(taxonomy.model_dump(mode="json")))
    )
    assert restored.total_failures == 1
    assert restored.records[0].category == FailureCategory.TIMEOUT_BUDGET_EXHAUSTED
