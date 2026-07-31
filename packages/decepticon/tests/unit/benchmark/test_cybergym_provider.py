"""Tests for benchmark.providers.cybergym.CyberGymProvider.

Covers spec parsing, challenge loading from a YAML spec, and the
server-verified ``evaluate`` scoring (crash reproduction via
``vul_exit_code``) with the HTTP layer faked. ``gen_task`` (setup) is not
exercised — it needs the upstream package and the ~240GB data tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.harness import _build_kickoff_prompt
from benchmark.providers import cybergym as cg
from benchmark.providers.cybergym import CyberGymProvider
from benchmark.schemas import Challenge, FilterConfig
from benchmark.state import BenchmarkRunState


def _write_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "cybergym.yaml"
    spec.write_text(
        "benchmark_id: t\n"
        "server: http://localhost:8666\n"
        f"data_dir: {tmp_path}/data\n"
        "difficulty: level1\n"
        "api_key: k\n"
        "task_ids:\n"
        "  - arvo:10400\n"
        "  - oss-fuzz:42535201\n"
    )
    return spec


class _FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise cg.httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]


class _FakeClient:
    """Context-manager stub for httpx.Client keyed by request path."""

    def __init__(self, routes: dict[str, _FakeResponse]) -> None:
        self._routes = routes

    def __call__(self, *args: object, **kwargs: object) -> "_FakeClient":
        return self

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        return self._routes[path]


def _install_routes(monkeypatch: pytest.MonkeyPatch, routes: dict[str, _FakeResponse]) -> None:
    monkeypatch.setattr(cg.httpx, "Client", _FakeClient(routes))


def test_poc_kickoff_uses_submission_workflow() -> None:
    prompt = _build_kickoff_prompt(
        Challenge(
            id="cybergym-arvo-10400",
            name="arvo:10400",
            description="Reproduce the crash.",
            level=1,
            tags=["vuln-repro"],
            win_condition="poc",
        )
    )

    assert "./submit.sh <poc-file>" in prompt
    assert "There is no flag" in prompt
    assert "/skills/benchmark/SKILL.md" not in prompt


class TestLoadChallenges:
    def test_loads_tasks_from_spec(self, tmp_path: Path) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        challenges = provider.load_challenges(FilterConfig())

        assert [c.cybergym_task_id for c in challenges] == ["arvo:10400", "oss-fuzz:42535201"]
        assert challenges[0].id == "cybergym-arvo-10400"
        assert challenges[0].level == 1
        assert "vuln-repro" in challenges[0].tags and "arvo" in challenges[0].tags

    def test_id_filter(self, tmp_path: Path) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        got = provider.load_challenges(FilterConfig(ids=["cybergym-oss-fuzz-42535201"]))
        assert len(got) == 1 and got[0].cybergym_task_id == "oss-fuzz:42535201"

    def test_level_filter(self, tmp_path: Path) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        assert len(provider.load_challenges(FilterConfig(levels=[1]))) == 2
        assert provider.load_challenges(FilterConfig(levels=[3])) == []


class TestEvaluate:
    def _challenge(self) -> Challenge:
        return Challenge(
            id="cybergym-arvo-10400",
            name="arvo:10400",
            description="d",
            level=1,
            tags=["vuln-repro", "arvo"],
            cybergym_task_id="arvo:10400",
        )

    def test_crash_reproduced_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        provider._agent_ids["cybergym-arvo-10400"] = "aid"
        _install_routes(
            monkeypatch,
            {
                "/verify-agent-pocs": _FakeResponse(200, {"message": "ok"}),
                # vul crashes (1), fix survives (0) -> reproduced + vuln-specific
                "/query-poc": _FakeResponse(200, [{"vul_exit_code": 1, "fix_exit_code": 0}]),
            },
        )
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is True
        assert result.bug_id == "arvo:10400"
        assert "vuln-specific" in (result.flag_captured or "")

    def test_no_crash_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        provider._agent_ids["cybergym-arvo-10400"] = "aid"
        _install_routes(
            monkeypatch,
            {
                "/verify-agent-pocs": _FakeResponse(200, {"message": "ok"}),
                # exit code 0 and sentinel 300 are both "did not crash"
                "/query-poc": _FakeResponse(200, [{"vul_exit_code": 0, "fix_exit_code": 0}]),
            },
        )
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is False

    def test_null_vul_exit_code_does_not_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A null/absent vul_exit_code (unverified record) must not false-pass."""
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        provider._agent_ids["cybergym-arvo-10400"] = "aid"
        _install_routes(
            monkeypatch,
            {
                "/verify-agent-pocs": _FakeResponse(200, {"message": "ok"}),
                "/query-poc": _FakeResponse(200, [{"fix_exit_code": 0}]),  # no vul_exit_code
            },
        )
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is False

    def test_non_list_response_surfaces_error_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unexpected JSON shape must not raise (evaluate contract)."""
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        provider._agent_ids["cybergym-arvo-10400"] = "aid"
        _install_routes(
            monkeypatch,
            {
                "/verify-agent-pocs": _FakeResponse(200, {"message": "ok"}),
                "/query-poc": _FakeResponse(200, {"records": []}),  # dict, not list
            },
        )
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is False
        assert "unexpected" in (result.error or "")

    def test_no_pocs_submitted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        provider._agent_ids["cybergym-arvo-10400"] = "aid"
        _install_routes(monkeypatch, {"/verify-agent-pocs": _FakeResponse(404)})
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is False
        assert result.error == "no PoCs submitted"

    def test_verification_error_does_not_query_or_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        provider._agent_ids["cybergym-arvo-10400"] = "aid"
        _install_routes(monkeypatch, {"/verify-agent-pocs": _FakeResponse(500)})
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is False
        assert "server error" in (result.error or "")

    def test_missing_agent_id(self, tmp_path: Path) -> None:
        provider = CyberGymProvider(spec_path=_write_spec(tmp_path))
        result = provider.evaluate(self._challenge(), BenchmarkRunState(), tmp_path)
        assert result.passed is False
        assert "no agent_id" in (result.error or "")
