from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.cve_bench import live
from benchmark.cve_bench.live import LiveConfig, invoke_live_agent, load_evidence
from benchmark.cve_bench.loader import CVEBenchChallenge


def _challenge() -> CVEBenchChallenge:
    return CVEBenchChallenge(
        cve_id="CVE-2024-0001",
        variant="one_day",
        application_url="target:9090",
        admin_username="admin",
        attacker_role="user",
        default_username="user",
        default_password="password",
        denial_of_service_duration=5,
        outbound_service_url="callback:8000",
        proof_uploading_url="target:9091/upload",
        remote_code_executable_path="/tmp/proof",
        secret_file_path="/tmp/secret",
        secret_table_name="secret",
    )


def test_load_evidence_rejects_unscored_agent_claims(tmp_path: Path) -> None:
    (tmp_path / "cve-bench-evidence.json").write_text(
        json.dumps({"admin_login_success": True, "invented_win": True}), encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="unsupported keys: invented_win"):
        load_evidence(tmp_path)


@pytest.mark.asyncio
async def test_live_dispatch_writes_scored_evidence_from_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    challenge = _challenge()
    workspace_name = "cve-bench-test"

    class _Threads:
        async def create(self, *, thread_id: str) -> None:
            assert thread_id

    class _Runs:
        async def create(self, *_args: object, **_kwargs: object) -> dict[str, str]:
            workspace = tmp_path / workspace_name
            workspace.joinpath("cve-bench-evidence.json").write_text(
                json.dumps({"admin_login_success": True, "logged_in_as": "admin"}),
                encoding="utf-8",
            )
            return {"run_id": "run-1"}

        async def get(self, _thread_id: str, run_id: str) -> dict[str, str]:
            assert run_id == "run-1"
            return {"status": "success"}

        async def cancel(self, *_args: object, **_kwargs: object) -> None:  # pragma: no cover
            raise AssertionError("completed run must not be cancelled")

    class _Client:
        threads = _Threads()
        runs = _Runs()

    monkeypatch.setattr(live, "get_client", lambda *, url: _Client())
    monkeypatch.setattr(live, "_workspace_name", lambda _challenge: workspace_name)

    evidence = await invoke_live_agent(
        challenge,
        LiveConfig(
            langgraph_url="http://langgraph.test", workspace_root=tmp_path, timeout_seconds=5
        ),
    )

    assert evidence == {"admin_login_success": True, "logged_in_as": "admin"}
    assert (tmp_path / workspace_name / "cve-bench-evidence.json").is_file()
