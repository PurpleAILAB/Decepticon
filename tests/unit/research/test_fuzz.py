"""Unit tests for fuzzing orchestration helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.tools.research.fuzz import (
    Crash,
    Engine,
    classify_target,
    harness_for,
    parse_asan,
    record_crash,
)
from decepticon.tools.research.graph import KnowledgeGraph, NodeKind, Severity


class TestClassifyTarget:
    def test_python_project(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "main.py").write_text("def parse(data): pass\n")
        tp = classify_target(tmp_path)
        assert tp.language == "python"
        assert tp.engine == Engine.ATHERIS

    def test_rust_project(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
        tp = classify_target(tmp_path)
        assert tp.language == "rust"
        assert tp.engine == Engine.CARGO_FUZZ

    def test_go_project(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/x\n")
        tp = classify_target(tmp_path)
        assert tp.language == "go"
        assert tp.engine == Engine.GO_FUZZ

    def test_java_project(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project/>")
        tp = classify_target(tmp_path)
        assert tp.language == "java"
        assert tp.engine == Engine.JAZZER

    def test_c_fallback_when_only_makefile(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").write_text("all:\n")
        (tmp_path / "lib.c").write_text("int main(){return 0;}")
        tp = classify_target(tmp_path)
        assert tp.language == "c_cpp"
        assert tp.engine == Engine.LIBFUZZER

    def test_python_beats_makefile(self, tmp_path: Path) -> None:
        """Python project with Makefile should classify as python, not c_cpp."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "Makefile").write_text("all:\n")
        tp = classify_target(tmp_path)
        assert tp.language == "python"

    def test_entry_candidates_extracted(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "parser.py").write_text("")
        (tmp_path / "main.py").write_text("")
        (tmp_path / "helpers.py").write_text("")
        tp = classify_target(tmp_path)
        stems = {p.stem for p in tp.entry_candidates}
        assert "parser" in stems
        assert "main" in stems
        # "helpers" doesn't match the interesting regex
        assert "helpers" not in stems

    def test_missing_root_returns_empty_profile(self) -> None:
        tp = classify_target("/definitely/does/not/exist")
        assert tp.language is None
        assert tp.engine is None


class TestHarnessSynthesis:
    @pytest.mark.parametrize(
        "engine",
        [
            Engine.LIBFUZZER,
            Engine.ATHERIS,
            Engine.JAZZER,
            Engine.CARGO_FUZZ,
            Engine.GO_FUZZ,
            Engine.BOOFUZZ,
            Engine.AFLPP,
            Engine.HONGGFUZZ,
        ],
    )
    def test_harness_for_every_engine(self, engine: Engine) -> None:
        src = harness_for(engine, "parser", "parse_http")
        assert "parser" in src
        assert "parse_http" in src
        assert len(src) > 100  # non-trivial template

    def test_atheris_template_is_python(self) -> None:
        src = harness_for(Engine.ATHERIS, "target", "entry")
        assert "atheris" in src
        assert "TestOneInput" in src


class TestASanParser:
    def test_parses_heap_buffer_overflow(self) -> None:
        log = """==1234==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000010
READ of size 4 at 0x602000000010 thread T0
    #0 0x4f1234 in parse_http /src/parser.c:42:18
    #1 0x4f5678 in main /src/main.c:10:5
SUMMARY: AddressSanitizer: heap-buffer-overflow /src/parser.c:42:18 in parse_http"""
        crash = parse_asan(log)
        assert crash is not None
        assert crash.kind == "heap-buffer-overflow"
        assert crash.severity == Severity.CRITICAL
        assert crash.file == "/src/parser.c"
        assert crash.line == 42
        assert len(crash.stack) == 2

    def test_parses_use_after_free(self) -> None:
        log = """==1234==ERROR: AddressSanitizer: heap-use-after-free on 0x...
    #0 0x4f1234 in foo /src/foo.c:10:5
SUMMARY: AddressSanitizer: heap-use-after-free /src/foo.c:10:5"""
        crash = parse_asan(log)
        assert crash is not None
        assert crash.severity == Severity.CRITICAL

    def test_parses_ubsan(self) -> None:
        log = "/src/foo.c:42:18: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented"
        crash = parse_asan(log)
        assert crash is not None
        assert crash.sanitizer == "UBSan"
        assert crash.severity == Severity.MEDIUM
        assert crash.file == "/src/foo.c"

    def test_returns_none_on_clean_log(self) -> None:
        assert parse_asan("just some normal output") is None

    def test_unknown_kind_defaults_to_high(self) -> None:
        log = """==1==ERROR: AddressSanitizer: weird-thing
    #0 0x123 in foo /src/a.c:1
SUMMARY: AddressSanitizer: weird-thing /src/a.c:1"""
        crash = parse_asan(log)
        assert crash is not None
        assert crash.severity == Severity.HIGH


class TestRecordCrash:
    def test_persists_vulnerability_and_location(self) -> None:
        crash = Crash(
            sanitizer="ASan",
            kind="heap-buffer-overflow",
            summary="test overflow",
            severity=Severity.CRITICAL,
            stack=["frame1", "frame2"],
            file="/src/x.c",
            line=10,
        )
        g = KnowledgeGraph()
        vuln = record_crash(g, crash, engine=Engine.LIBFUZZER)
        assert vuln.kind == NodeKind.VULNERABILITY
        assert vuln.props["crash_kind"] == "heap-buffer-overflow"
        assert vuln.props["engine"] == "libfuzzer"
        # Code location node linked
        assert len(g.by_kind(NodeKind.CODE_LOCATION)) == 1

    def test_record_without_location(self) -> None:
        crash = Crash(
            sanitizer="ASan",
            kind="oom",
            summary="out of memory",
            severity=Severity.HIGH,
            stack=[],
            file=None,
            line=None,
        )
        g = KnowledgeGraph()
        record_crash(g, crash, engine=Engine.LIBFUZZER)
        assert len(g.by_kind(NodeKind.CODE_LOCATION)) == 0
