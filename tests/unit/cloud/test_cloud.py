"""Tests for cloud exploitation package (AWS, k8s, terraform, metadata)."""

from __future__ import annotations

from decepticon.tools.cloud.aws import (
    analyze_iam_policy,
    scan_bucket_names,
    scan_user_data,
)
from decepticon.tools.cloud.k8s import analyze_k8s_manifest
from decepticon.tools.cloud.metadata import METADATA_ENDPOINTS
from decepticon.tools.cloud.terraform import analyze_tfstate


class TestIAMPolicy:
    def test_wildcard_action_resource(self) -> None:
        policy = {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}
        findings = analyze_iam_policy(policy)
        assert any("Wildcard Action" in f.title for f in findings)
        assert any(f.severity == "critical" for f in findings)

    def test_privesc_create_access_key(self) -> None:
        policy = {
            "Statement": [{"Effect": "Allow", "Action": "iam:CreateAccessKey", "Resource": "*"}]
        }
        findings = analyze_iam_policy(policy)
        assert any("CreateAccessKey" in f.title for f in findings)

    def test_deny_statements_ignored(self) -> None:
        policy = {
            "Statement": [{"Effect": "Deny", "Action": "iam:CreateAccessKey", "Resource": "*"}]
        }
        assert len(analyze_iam_policy(policy)) == 0

    def test_parse_error_returns_finding(self) -> None:
        findings = analyze_iam_policy("{not json")
        assert len(findings) == 1
        assert findings[0].id == "iam.parse-error"

    def test_s3_wildcard_flagged(self) -> None:
        policy = {"Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}]}
        findings = analyze_iam_policy(policy)
        assert any("Wildcard s3:*" in f.title for f in findings)


class TestBucketScan:
    def test_s3_scheme(self) -> None:
        assert "my-bucket" in scan_bucket_names("see s3://my-bucket/key.txt")

    def test_virtual_hosted(self) -> None:
        assert "prod-data" in scan_bucket_names("url: https://prod-data.s3.amazonaws.com/foo")

    def test_path_style(self) -> None:
        assert "path-bucket" in scan_bucket_names("https://s3.amazonaws.com/path-bucket/x")

    def test_does_not_match_generic_paths(self) -> None:
        # "file" should not become a bucket from a non-s3 host
        buckets = scan_bucket_names("https://example.com/file")
        assert "file" not in buckets


class TestUserDataScan:
    def test_aws_key(self) -> None:
        hits = scan_user_data("export AWS_KEY=AKIAIOSFODNN7EXAMPLE")
        assert any(kind == "aws_access_key" for kind, _ in hits)

    def test_private_key(self) -> None:
        hits = scan_user_data("-----BEGIN RSA PRIVATE KEY-----")
        assert any(kind == "ssh_private_key" for kind, _ in hits)

    def test_password_literal(self) -> None:
        hits = scan_user_data("PASSWORD=supersecret123")
        assert any(kind == "password_literal" for kind, _ in hits)


class TestKubernetes:
    def test_privileged_container(self) -> None:
        m = {
            "kind": "Pod",
            "metadata": {"name": "p"},
            "spec": {"containers": [{"name": "c", "securityContext": {"privileged": True}}]},
        }
        findings = analyze_k8s_manifest(m)
        assert any("privileged" in f.title for f in findings)
        assert any(f.severity == "critical" for f in findings)

    def test_host_path_docker_sock(self) -> None:
        m = {
            "kind": "Pod",
            "metadata": {"name": "p"},
            "spec": {
                "volumes": [{"hostPath": {"path": "/var/run/docker.sock"}}],
                "containers": [{"name": "c"}],
            },
        }
        findings = analyze_k8s_manifest(m)
        assert any("docker.sock" in f.title for f in findings)

    def test_wildcard_rbac(self) -> None:
        m = {
            "kind": "ClusterRole",
            "metadata": {"name": "r"},
            "rules": [{"verbs": ["*"], "resources": ["*"], "apiGroups": ["*"]}],
        }
        findings = analyze_k8s_manifest(m)
        assert any("Wildcard RBAC" in f.title for f in findings)

    def test_dangerous_capability(self) -> None:
        m = {
            "kind": "Deployment",
            "metadata": {"name": "d"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "c",
                                "securityContext": {"capabilities": {"add": ["SYS_ADMIN"]}},
                            }
                        ]
                    }
                }
            },
        }
        findings = analyze_k8s_manifest(m)
        assert any("SYS_ADMIN" in f.title for f in findings)

    def test_plain_env_secret(self) -> None:
        m = {
            "kind": "Pod",
            "metadata": {"name": "p"},
            "spec": {
                "containers": [
                    {
                        "name": "c",
                        "env": [{"name": "DB_PASSWORD", "value": "hunter2"}],
                    }
                ]
            },
        }
        findings = analyze_k8s_manifest(m)
        assert any("DB_PASSWORD" in f.title for f in findings)


class TestTerraform:
    def test_sensitive_output(self) -> None:
        tf = {
            "version": 4,
            "terraform_version": "1.0.0",
            "outputs": {"db_pw": {"value": "x", "sensitive": True}},
            "resources": [],
        }
        r = analyze_tfstate(tf)
        assert "db_pw" in r.sensitive_outputs
        assert any(f.kind == "sensitive_output" for f in r.findings)

    def test_plaintext_secret_in_resource(self) -> None:
        tf = {
            "version": 4,
            "resources": [
                {
                    "mode": "managed",
                    "type": "aws_instance",
                    "name": "web",
                    "provider": "aws",
                    "instances": [{"attributes": {"password": "plaintext123", "ami": "ami-xxx"}}],
                }
            ],
        }
        r = analyze_tfstate(tf)
        assert any(f.kind == "plaintext_secret" for f in r.findings)
        assert "aws" in r.providers

    def test_bad_json(self) -> None:
        r = analyze_tfstate("not json")
        assert any(f.kind == "parse-error" for f in r.findings)


class TestMetadataCatalogue:
    def test_catalog_nonempty(self) -> None:
        assert len(METADATA_ENDPOINTS) > 5

    def test_aws_imds_present(self) -> None:
        urls = [e.url for e in METADATA_ENDPOINTS]
        assert any("169.254.169.254" in u for u in urls)

    def test_gcp_header_present(self) -> None:
        gcp = [e for e in METADATA_ENDPOINTS if e.provider == "gcp"]
        assert any(e.headers and "Metadata-Flavor" in e.headers for e in gcp)
