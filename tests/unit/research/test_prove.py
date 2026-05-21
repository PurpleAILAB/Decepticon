"""Unit tests for the prove stage (decepticon.tools.research.prove)."""

from __future__ import annotations

import pytest

from decepticon.tools.research.graph import (
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)
from decepticon.tools.research.prove import (
    ProofResult,
    ProofStrategy,
    prove_native,
    prove_web,
    route_proof_strategy,
    sanitizer_build_command,
)

_ASAN_LOG = """\
==1234==ERROR: AddressSanitizer: heap-buffer-overflow on address 0xdeadbeef
    #0 0x4011a2 in parse_header /src/app.c:42
    #1 0x401300 in main /src/app.c:88
SUMMARY: AddressSanitizer: heap-buffer-overflow /src/app.c:42 in parse_header
"""


class _ScriptedRunner:
    """A PoCRunner that returns queued (stdout, stderr, exit_code) tuples."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[str] = []

    async def __call__(self, command: str):
        self.calls.append(command)
        if not self.outputs:
            return ("", "", 0)
        return self.outputs.pop(0)


class TestRouting:
    def test_memory_corruption_routes_to_sanitizer(self):
        assert route_proof_strategy(cwes=["CWE-787"]) == ProofStrategy.SANITIZER

    def test_web_injection_routes_to_differential(self):
        assert route_proof_strategy(cwes=["CWE-89"]) == ProofStrategy.DIFFERENTIAL

    def test_authz_routes_to_recheck(self):
        assert route_proof_strategy(cwes=["CWE-287"]) == ProofStrategy.RECHECK

    def test_unknown_class_is_unprovable(self):
        assert route_proof_strategy(cwes=["CWE-1004"]) == ProofStrategy.UNPROVABLE

    def test_crash_kind_prop_forces_sanitizer(self):
        # A fuzzer-found bug with no CWE still routes to SANITIZER.
        assert route_proof_strategy(cwes=[], crash_kind="heap-use-after-free") == (
            ProofStrategy.SANITIZER
        )


class TestSanitizerBuildCommand:
    def test_injects_sanitizer_flags(self):
        cmd = sanitizer_build_command("make")
        assert "-fsanitize=address,undefined" in cmd
        assert cmd.endswith("make")
        assert "CFLAGS=" in cmd and "CXXFLAGS=" in cmd


@pytest.mark.asyncio
class TestProveNative:
    async def test_sanitizer_report_proves_finding(self):
        runner = _ScriptedRunner([(_ASAN_LOG, "", 1)])
        result = await prove_native(
            runner=runner, target_command="./fuzz_app crash.bin", instrumented_binary="./fuzz_app"
        )
        assert result.proven is True
        assert result.confidence == "proven"
        assert result.method == "asan-report"
        assert result.crash_kind == "heap-buffer-overflow"

    async def test_rebuilds_from_source_then_runs(self):
        runner = _ScriptedRunner([("build ok", "", 0), (_ASAN_LOG, "", 1)])
        result = await prove_native(
            runner=runner,
            target_command="./a.out crash.bin",
            source_dir="/workspace/target",
            build_command="make",
        )
        assert result.proven is True
        assert len(runner.calls) == 2
        assert "-fsanitize=address,undefined" in runner.calls[0]

    async def test_clean_instrumented_run_is_not_proven(self):
        runner = _ScriptedRunner([("all good, exit 0", "", 0)])
        result = await prove_native(
            runner=runner, target_command="./fuzz_app input.bin", instrumented_binary="./fuzz_app"
        )
        assert result.proven is False

    async def test_gdb_fallback_detects_crash(self):
        runner = _ScriptedRunner(
            [("Program received signal SIGSEGV, Segmentation fault.", "", 139)]
        )
        result = await prove_native(runner=runner, target_command="./vuln input.bin")
        assert result.proven is True
        assert result.method == "gdb-crash"
        assert result.confidence == "verified"  # weaker than a sanitizer report

    async def test_gdb_fallback_clean_is_not_proven(self):
        runner = _ScriptedRunner([("[Inferior 1 exited normally]", "", 0)])
        result = await prove_native(runner=runner, target_command="./vuln input.bin")
        assert result.proven is False


@pytest.mark.asyncio
class TestProveWeb:
    async def test_sentinel_only_in_payload_run_proves(self):
        runner = _ScriptedRunner([("response: DEADBEEF leaked", "", 0), ("normal results", "", 0)])
        result = await prove_web(
            runner=runner,
            poc_command="curl 'http://t/?q=payload'",
            success_patterns=["DEADBEEF"],
            negative_command="curl 'http://t/?q=normal'",
        )
        assert result.proven is True
        assert result.confidence == "proven"

    async def test_signal_in_negative_control_fails_proof(self):
        runner = _ScriptedRunner([("DEADBEEF", "", 0), ("DEADBEEF appears here too", "", 0)])
        result = await prove_web(
            runner=runner,
            poc_command="curl payload",
            success_patterns=["DEADBEEF"],
            negative_command="curl normal",
        )
        assert result.proven is False


class TestProofArtifact:
    def test_round_trips_through_finding(self):
        from decepticon.core.schemas import Finding, FindingConfidence, ProofArtifact

        f = Finding(
            id="FIND-001",
            title="[heap overflow] in parse_header",
            severity="critical",
            affected_target="app",
            description="oob write",
            confidence=FindingConfidence.PROVEN,
            proof=ProofArtifact(
                strategy="sanitizer",
                method="asan-report",
                proven=True,
                sanitizer="ASan",
                crash_kind="heap-buffer-overflow",
            ),
        )
        restored = Finding.model_validate(f.model_dump(mode="json"))
        assert restored.confidence == FindingConfidence.PROVEN
        assert restored.proof is not None
        assert restored.proof.crash_kind == "heap-buffer-overflow"


class TestPersistProof:
    def test_persist_proof_creates_node_and_edges(self):
        from decepticon.tools.research.tools import _persist_proof

        graph = KnowledgeGraph()
        vuln = Node.make(
            NodeKind.VULNERABILITY, "heap overflow", key="v1", severity=Severity.CRITICAL.value
        )
        graph.upsert_node(vuln)
        finding = Node.make(
            NodeKind.FINDING,
            "validated: heap overflow",
            key="finding::h1",
            validated=True,
            vuln_id=vuln.id,
        )
        graph.upsert_node(finding)

        result = ProofResult(
            proven=True,
            proof_admitted=True,
            strategy="sanitizer",
            method="asan-report",
            confidence="proven",
            proof_hash="ph1",
        )
        _persist_proof(graph, vuln.id, result)

        proofs = [n for n in graph.nodes.values() if n.kind == NodeKind.PROOF]
        assert len(proofs) == 1
        edges = [e for e in graph.edges.values() if e.kind == EdgeKind.PROVEN_BY]
        assert len(edges) == 2  # vuln→proof and finding→proof
        assert graph.nodes[finding.id].props["confidence"] == "proven"
        assert graph.nodes[vuln.id].props["proven"] is True
