"""Tests for @tool wrappers in contracts/tools.py, evidence/tools.py, cloud/tools.py.

Focuses on the JSON output shapes and error paths that are NOT covered by the
existing helper tests (test_cloud.py, test_patterns_slither.py, test_evidence.py).
All external IO is mocked so the suite runs fully offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

# ── contracts/tools.py wrappers ────────────────────────────────────────────


class TestSolidityScantool:
    """solidity_scan @tool — JSON output shape."""

    def test_happy_path_returns_json_list(self) -> None:
        from decepticon.tools.contracts.tools import solidity_scan

        result = solidity_scan.invoke(
            {"source": "function auth() public { require(tx.origin == owner); }"}
        )
        data = json.loads(result)
        assert isinstance(data, list)
        # at least one finding (tx.origin rule)
        assert len(data) >= 1
        first = data[0]
        assert "id" in first
        assert "rule" in first
        assert "severity" in first
        assert "line" in first
        assert "snippet" in first

    def test_clean_source_returns_empty_list(self) -> None:
        from decepticon.tools.contracts.tools import solidity_scan

        result = solidity_scan.invoke({"source": "// solidity comment only"})
        data = json.loads(result)
        assert data == []

    def test_multiple_findings_ordered_by_line(self) -> None:
        from decepticon.tools.contracts.tools import solidity_scan

        src = (
            "// line 1\n"
            "function a() public { require(tx.origin == owner); }\n"
            "function b() public { address s = ecrecover(h, v, r, x); }\n"
        )
        result = solidity_scan.invoke({"source": src})
        findings = json.loads(result)
        lines = [f["line"] for f in findings]
        assert lines == sorted(lines)


class TestSolidityScantoolFile:
    """solidity_scan_file @tool — reads file and returns JSON dict with 'findings' key."""

    def test_reads_file_and_returns_findings(self, tmp_path: Path) -> None:
        from decepticon.tools.contracts.tools import solidity_scan_file

        sol = tmp_path / "contract.sol"
        sol.write_text("function f() public { require(tx.origin == owner); }", encoding="utf-8")
        result = solidity_scan_file.invoke({"path": str(sol)})
        data = json.loads(result)
        assert data["file"] == str(sol)
        assert isinstance(data["count"], int)
        assert isinstance(data["findings"], list)
        assert data["count"] == len(data["findings"])
        assert data["count"] >= 1

    def test_missing_file_returns_error_key(self, tmp_path: Path) -> None:
        from decepticon.tools.contracts.tools import solidity_scan_file

        result = solidity_scan_file.invoke({"path": str(tmp_path / "nonexistent.sol")})
        data = json.loads(result)
        assert "error" in data

    def test_clean_sol_file_count_zero(self, tmp_path: Path) -> None:
        from decepticon.tools.contracts.tools import solidity_scan_file

        sol = tmp_path / "clean.sol"
        sol.write_text("// pragma solidity ^0.8.0;\n", encoding="utf-8")
        result = solidity_scan_file.invoke({"path": str(sol)})
        data = json.loads(result)
        assert data["count"] == 0
        assert data["findings"] == []


class TestSlitherIngestTool:
    """slither_ingest @tool — reads file and ingests into KG."""

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        from decepticon.tools.contracts.tools import slither_ingest

        result = slither_ingest.invoke({"path": str(tmp_path / "missing.json")})
        data = json.loads(result)
        assert "error" in data

    def test_valid_slither_json_returns_ingested_and_stats(self, tmp_path: Path) -> None:
        from decepticon.tools.contracts.tools import slither_ingest

        payload = {
            "results": {
                "detectors": [
                    {
                        "check": "reentrancy-eth",
                        "impact": "High",
                        "confidence": "High",
                        "description": "Reentrancy in Vault.withdraw",
                        "elements": [
                            {
                                "source_mapping": {
                                    "filename_relative": "src/Vault.sol",
                                    "lines": [42],
                                }
                            }
                        ],
                    }
                ]
            }
        }
        slither_file = tmp_path / "out.json"
        slither_file.write_text(json.dumps(payload), encoding="utf-8")

        # Patch _load/_save so we don't need a real KG on disk
        from decepticon_core.types.kg import KnowledgeGraph

        fake_kg = KnowledgeGraph()
        kg_path = tmp_path / "kg.json"

        with (
            patch("decepticon.tools.contracts.tools._load", return_value=(fake_kg, kg_path)),
            patch("decepticon.tools.contracts.tools._save") as mock_save,
        ):
            result = slither_ingest.invoke({"path": str(slither_file)})

        data = json.loads(result)
        assert data["ingested"] == 1
        assert "stats" in data
        mock_save.assert_called_once()

    def test_empty_detectors_returns_zero(self, tmp_path: Path) -> None:
        from decepticon.tools.contracts.tools import slither_ingest

        payload = {"results": {"detectors": []}}
        slither_file = tmp_path / "empty.json"
        slither_file.write_text(json.dumps(payload), encoding="utf-8")

        from decepticon_core.types.kg import KnowledgeGraph

        fake_kg = KnowledgeGraph()
        kg_path = tmp_path / "kg.json"

        with (
            patch("decepticon.tools.contracts.tools._load", return_value=(fake_kg, kg_path)),
            patch("decepticon.tools.contracts.tools._save"),
        ):
            result = slither_ingest.invoke({"path": str(slither_file)})

        data = json.loads(result)
        assert data["ingested"] == 0


class TestFoundryToolWrappers:
    """foundry_reentrancy_test, foundry_access_test, foundry_flashloan_test."""

    def test_reentrancy_tool_returns_path_and_source(self) -> None:
        from decepticon.tools.contracts.tools import foundry_reentrancy_test

        result = foundry_reentrancy_test.invoke(
            {"target": "Vault", "function": "withdraw", "target_path": "src/Vault.sol"}
        )
        data = json.loads(result)
        assert "path" in data
        assert "source" in data
        assert data["path"].endswith(".t.sol")
        assert "withdraw" in data["source"]

    def test_access_test_tool_returns_path_and_source(self) -> None:
        from decepticon.tools.contracts.tools import foundry_access_test

        result = foundry_access_test.invoke({"target": "Token", "function": "mint"})
        data = json.loads(result)
        assert "path" in data
        assert "source" in data
        assert "mint" in data["source"]

    def test_flashloan_test_tool_returns_path_and_source(self) -> None:
        from decepticon.tools.contracts.tools import foundry_flashloan_test

        result = foundry_flashloan_test.invoke({"target": "Pool"})
        data = json.loads(result)
        assert "path" in data
        assert "source" in data
        assert "executeOperation" in data["source"]

    def test_contract_tools_list_has_six_items(self) -> None:
        from decepticon.tools.contracts.tools import CONTRACT_TOOLS

        assert len(CONTRACT_TOOLS) == 6


# ── evidence/tools.py wrappers ─────────────────────────────────────────────


class TestExportSessionAsciicastTool:
    """export_session_asciicast @tool output shapes."""

    def test_successful_export_returns_status_exported(self, tmp_path: Path) -> None:
        from decepticon.tools.evidence.tools import export_session_asciicast

        log = tmp_path / ".tmux-logs" / "mysession.log"
        log.parent.mkdir(parents=True)
        log.write_text("cmd output\n", encoding="utf-8")

        evidence_dir = tmp_path / "evidence" / "recordings"
        evidence_dir.mkdir(parents=True)

        with patch("decepticon.tools.evidence.tools._workspace", return_value=tmp_path):
            result = export_session_asciicast.invoke(
                {
                    "session_name": "mysession",
                    "pipe_pane_log_path": "",
                    "title": "Test Session",
                }
            )

        data = json.loads(result)
        assert data["status"] == "exported"
        assert "session_name" in data

    def test_explicit_log_path_used_when_provided(self, tmp_path: Path) -> None:
        from decepticon.tools.evidence.tools import export_session_asciicast

        log = tmp_path / "custom.log"
        log.write_text("output line\n", encoding="utf-8")
        evidence_dir = tmp_path / "evidence" / "recordings"
        evidence_dir.mkdir(parents=True)

        with patch("decepticon.tools.evidence.tools._workspace", return_value=tmp_path):
            result = export_session_asciicast.invoke(
                {
                    "session_name": "s1",
                    "pipe_pane_log_path": str(log),
                    "title": "",
                }
            )

        data = json.loads(result)
        assert data["status"] == "exported"

    def test_missing_log_returns_error_key(self, tmp_path: Path) -> None:
        from decepticon.tools.evidence.tools import export_session_asciicast

        evidence_dir = tmp_path / "evidence" / "recordings"
        evidence_dir.mkdir(parents=True)

        with patch("decepticon.tools.evidence.tools._workspace", return_value=tmp_path):
            result = export_session_asciicast.invoke(
                {
                    "session_name": "nope",
                    "pipe_pane_log_path": str(tmp_path / "nonexistent.log"),
                    "title": "",
                }
            )

        data = json.loads(result)
        assert "error" in data


class TestListSessionRecordingsTool:
    """list_session_recordings @tool output shapes."""

    def test_empty_dir_returns_count_zero(self, tmp_path: Path) -> None:
        from decepticon.tools.evidence.tools import list_session_recordings

        recordings_dir = tmp_path / "evidence" / "recordings"
        recordings_dir.mkdir(parents=True)

        with patch("decepticon.tools.evidence.tools._workspace", return_value=tmp_path):
            result = list_session_recordings.invoke({})

        data = json.loads(result)
        assert data["count"] == 0
        assert data["recordings"] == []

    def test_lists_manifests_correctly(self, tmp_path: Path) -> None:
        from decepticon.tools.evidence.tools import list_session_recordings

        recordings_dir = tmp_path / "evidence" / "recordings"
        recordings_dir.mkdir(parents=True)
        (recordings_dir / "a.cast.manifest.json").write_text(
            json.dumps({"session_name": "a", "duration_seconds": 1.5}),
            encoding="utf-8",
        )
        (recordings_dir / "b.cast.manifest.json").write_text(
            json.dumps({"session_name": "b", "duration_seconds": 2.0}),
            encoding="utf-8",
        )

        with patch("decepticon.tools.evidence.tools._workspace", return_value=tmp_path):
            result = list_session_recordings.invoke({})

        data = json.loads(result)
        assert data["count"] == 2
        names = sorted(m["session_name"] for m in data["recordings"])
        assert names == ["a", "b"]

    def test_evidence_tools_list_has_four_items(self) -> None:
        from decepticon.tools.evidence.tools import EVIDENCE_TOOLS

        assert len(EVIDENCE_TOOLS) == 4


# ── cloud/tools.py wrappers ────────────────────────────────────────────────


class TestIAMPolicyAuditTool:
    """iam_policy_audit @tool — JSON output shape."""

    def test_wildcard_returns_json_list_with_critical(self) -> None:
        from decepticon.tools.cloud.tools import iam_policy_audit

        policy = json.dumps({"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]})
        result = iam_policy_audit.invoke({"policy_json": policy})
        data = json.loads(result)
        assert isinstance(data, list)
        assert any(f["severity"] == "critical" for f in data)
        # Each finding must have required keys
        for f in data:
            assert "id" in f
            assert "title" in f
            assert "severity" in f

    def test_clean_policy_returns_empty_list(self) -> None:
        from decepticon.tools.cloud.tools import iam_policy_audit

        policy = json.dumps(
            {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "s3:GetObject",
                        "Resource": "arn:aws:s3:::my-bucket/*",
                    }
                ]
            }
        )
        result = iam_policy_audit.invoke({"policy_json": policy})
        data = json.loads(result)
        assert isinstance(data, list)
        # No privesc primitives in GetObject on a specific resource
        assert len(data) == 0

    def test_invalid_json_policy_returns_parse_error(self) -> None:
        from decepticon.tools.cloud.tools import iam_policy_audit

        result = iam_policy_audit.invoke({"policy_json": "{not json"})
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["id"] == "iam.parse-error"


class TestS3BucketsFromTextTool:
    """s3_buckets_from_text @tool — JSON output shape."""

    def test_extracts_s3_scheme_bucket(self) -> None:
        from decepticon.tools.cloud.tools import s3_buckets_from_text

        result = s3_buckets_from_text.invoke({"text": "Copy from s3://my-data-bucket/key.csv"})
        data = json.loads(result)
        assert "count" in data
        assert "buckets" in data
        assert "my-data-bucket" in data["buckets"]
        assert data["count"] == len(data["buckets"])

    def test_no_buckets_returns_empty_list(self) -> None:
        from decepticon.tools.cloud.tools import s3_buckets_from_text

        result = s3_buckets_from_text.invoke({"text": "echo hello world"})
        data = json.loads(result)
        assert data["count"] == 0
        assert data["buckets"] == []

    def test_multiple_bucket_references(self) -> None:
        from decepticon.tools.cloud.tools import s3_buckets_from_text

        text = "s3://bucket-a/x and prod-data.s3.amazonaws.com/y"
        result = s3_buckets_from_text.invoke({"text": text})
        data = json.loads(result)
        assert data["count"] >= 2


class TestUserDataSecretsTool:
    """user_data_secrets @tool — JSON output shape."""

    def test_aws_key_in_output(self) -> None:
        from decepticon.tools.cloud.tools import user_data_secrets

        text = "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = user_data_secrets.invoke({"text": text})
        data = json.loads(result)
        assert "count" in data
        assert "hits" in data
        assert data["count"] >= 1
        hit = data["hits"][0]
        assert "kind" in hit
        assert "snippet" in hit

    def test_clean_userdata_returns_empty(self) -> None:
        from decepticon.tools.cloud.tools import user_data_secrets

        result = user_data_secrets.invoke({"text": "#!/bin/bash\napt-get update\n"})
        data = json.loads(result)
        assert data["count"] == 0
        assert data["hits"] == []


class TestK8sAuditTool:
    """k8s_audit @tool — JSON output shape."""

    def test_privileged_pod_returns_critical(self) -> None:
        from decepticon.tools.cloud.tools import k8s_audit

        manifest = json.dumps(
            {
                "kind": "Pod",
                "metadata": {"name": "evil"},
                "spec": {"containers": [{"name": "c", "securityContext": {"privileged": True}}]},
            }
        )
        result = k8s_audit.invoke({"manifest_json": manifest})
        data = json.loads(result)
        assert isinstance(data, list)
        assert any(f["severity"] == "critical" for f in data)
        for f in data:
            assert "id" in f
            assert "kind" in f
            assert "name" in f
            assert "title" in f

    def test_clean_manifest_returns_empty(self) -> None:
        from decepticon.tools.cloud.tools import k8s_audit

        manifest = json.dumps(
            {
                "kind": "Pod",
                "metadata": {"name": "safe"},
                "spec": {"containers": [{"name": "c", "image": "nginx"}]},
            }
        )
        result = k8s_audit.invoke({"manifest_json": manifest})
        data = json.loads(result)
        assert isinstance(data, list)
        # no dangerous flags set
        assert len(data) == 0

    def test_invalid_json_returns_parse_error(self) -> None:
        from decepticon.tools.cloud.tools import k8s_audit

        result = k8s_audit.invoke({"manifest_json": "not json"})
        data = json.loads(result)
        assert data[0]["id"] == "k8s.parse-error"


class TestTfstateAuditTool:
    """tfstate_audit @tool — JSON output shape."""

    def test_sensitive_output_flagged(self) -> None:
        from decepticon.tools.cloud.tools import tfstate_audit

        tfstate = json.dumps(
            {
                "version": 4,
                "terraform_version": "1.5.0",
                "outputs": {"db_pass": {"value": "secret123", "sensitive": True}},
                "resources": [],
            }
        )
        result = tfstate_audit.invoke({"tfstate_json": tfstate})
        data = json.loads(result)
        assert "sensitive_outputs" in data
        assert "db_pass" in data["sensitive_outputs"]
        assert data["version"] == 4
        assert "findings" in data

    def test_bad_json_returns_parse_error_in_findings(self) -> None:
        from decepticon.tools.cloud.tools import tfstate_audit

        result = tfstate_audit.invoke({"tfstate_json": "not json"})
        data = json.loads(result)
        assert any(f["kind"] == "parse-error" for f in data["findings"])

    def test_resource_with_plaintext_password(self) -> None:
        from decepticon.tools.cloud.tools import tfstate_audit

        tfstate = json.dumps(
            {
                "version": 4,
                "resources": [
                    {
                        "mode": "managed",
                        "type": "aws_db_instance",
                        "name": "db",
                        "provider": "registry.terraform.io/hashicorp/aws",
                        "instances": [{"attributes": {"password": "hunter2"}}],
                    }
                ],
            }
        )
        result = tfstate_audit.invoke({"tfstate_json": tfstate})
        data = json.loads(result)
        assert any(f["kind"] == "plaintext_secret" for f in data["findings"])


class TestMetadataEndpointsTool:
    """metadata_endpoints @tool — JSON output shape."""

    def test_no_filter_returns_all(self) -> None:
        from decepticon.tools.cloud.tools import metadata_endpoints

        result = metadata_endpoints.invoke({"provider": ""})
        data = json.loads(result)
        assert "count" in data
        assert "endpoints" in data
        assert data["count"] > 5
        assert data["count"] == len(data["endpoints"])
        ep = data["endpoints"][0]
        assert "provider" in ep
        assert "url" in ep
        assert "method" in ep

    def test_aws_filter_narrows_results(self) -> None:
        from decepticon.tools.cloud.tools import metadata_endpoints

        result = metadata_endpoints.invoke({"provider": "aws"})
        data = json.loads(result)
        assert data["count"] >= 1
        assert all(ep["provider"] == "aws" for ep in data["endpoints"])

    def test_unknown_provider_returns_empty(self) -> None:
        from decepticon.tools.cloud.tools import metadata_endpoints

        result = metadata_endpoints.invoke({"provider": "nonexistent_cloud"})
        data = json.loads(result)
        assert data["count"] == 0
        assert data["endpoints"] == []

    def test_cloud_tools_list_has_six_items(self) -> None:
        from decepticon.tools.cloud.tools import CLOUD_TOOLS

        assert len(CLOUD_TOOLS) == 6
