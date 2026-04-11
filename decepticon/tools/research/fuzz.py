"""Fuzzing orchestration — harness synthesis + campaign launching.

Decepticon treats fuzzing as first-class for 0-day discovery. This module:

1. Classifies a target (C/C++, Rust, Go, Java, JS, Python) from source
   layout hints so the agent picks the right fuzzer.
2. Emits harness skeletons for the biggest families: libFuzzer, AFL++,
   Jazzer (Java), boofuzz (network protocols), atheris (Python).
3. Parses crash output (ASan, UBSan, Jazzer stack, boofuzz monitor log)
   into structured :class:`Crash` records that can be pushed into the
   knowledge graph as VULNERABILITY + CODE_LOCATION nodes.

The module never runs a fuzzer itself — that's the agent's job via bash.
We stay a pure-Python library so the tests run without a C toolchain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)


class Engine(StrEnum):
    LIBFUZZER = "libfuzzer"
    AFLPP = "afl++"
    HONGGFUZZ = "honggfuzz"
    JAZZER = "jazzer"
    ATHERIS = "atheris"
    CARGO_FUZZ = "cargo-fuzz"
    GO_FUZZ = "go-fuzz"
    BOOFUZZ = "boofuzz"


# ── Target classification ───────────────────────────────────────────────


# Evaluated in order — the first match wins. Specific manifests come
# before generic build files because a Python project can also have a
# Makefile, but a Cargo.toml is almost always Rust.
_LANG_HINTS: list[tuple[str, set[str]]] = [
    ("rust", {"Cargo.toml"}),
    ("go", {"go.mod"}),
    ("java", {"pom.xml", "build.gradle", "build.gradle.kts"}),
    ("python", {"pyproject.toml", "setup.py", "requirements.txt"}),
    ("javascript", {"package.json"}),
    ("c_cpp", {"CMakeLists.txt", "Makefile", "configure", "meson.build"}),
]

_LANG_EXTENSIONS = {
    "c_cpp": {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"},
    "rust": {".rs"},
    "go": {".go"},
    "java": {".java"},
    "python": {".py"},
    "javascript": {".js", ".ts", ".mjs"},
}


_DEFAULT_ENGINE: dict[str, Engine] = {
    "c_cpp": Engine.LIBFUZZER,
    "rust": Engine.CARGO_FUZZ,
    "go": Engine.GO_FUZZ,
    "java": Engine.JAZZER,
    "python": Engine.ATHERIS,
    "javascript": Engine.JAZZER,  # Jazzer.js
}


@dataclass
class TargetProfile:
    """What we learned about a fuzz target from its source layout."""

    root: Path
    language: str | None
    engine: Engine | None
    entry_candidates: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def classify_target(root: str | Path, *, max_files: int = 2_000) -> TargetProfile:
    """Pick the best-guess language and fuzz engine for a repo root.

    Walks up to ``max_files`` files to avoid exhausting the filesystem on
    giant monorepos. Entry candidates are files whose name contains "main",
    "parse", "decode", "deserialize", or "fuzz" — usually the best harness
    attach points.
    """
    root_path = Path(root).resolve()
    if not root_path.exists():
        return TargetProfile(root=root_path, language=None, engine=None)

    # Fast path: look for build files at the root
    root_names = {p.name for p in root_path.iterdir() if p.is_file()}
    lang: str | None = None
    for candidate, markers in _LANG_HINTS:
        if root_names & markers:
            lang = candidate
            break

    # Walk a small sample of source files to corroborate + find entry candidates
    interesting = re.compile(r"(main|parse|decode|deserialize|handle|fuzz)", re.IGNORECASE)
    entries: list[Path] = []
    counts: dict[str, int] = {}
    for i, path in enumerate(root_path.rglob("*")):
        if i >= max_files:
            break
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        for name, exts in _LANG_EXTENSIONS.items():
            if suffix in exts:
                counts[name] = counts.get(name, 0) + 1
        if interesting.search(path.stem):
            entries.append(path)

    if lang is None and counts:
        lang = max(counts, key=lambda k: counts[k])

    engine = _DEFAULT_ENGINE.get(lang) if lang else None
    return TargetProfile(
        root=root_path,
        language=lang,
        engine=engine,
        entry_candidates=sorted(entries)[:20],
        notes=[f"source counts: {counts}"] if counts else [],
    )


# ── Harness synthesis ───────────────────────────────────────────────────


_LIBFUZZER_TEMPLATE = """\
// Minimal libFuzzer harness for {target}
// Build: clang -g -fsanitize=fuzzer,address,undefined -o fuzz_{target} fuzz_{target}.c {target}.c
#include <stdint.h>
#include <stddef.h>

extern int {entry}(const uint8_t *data, size_t size);

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {{
    if (size == 0) return 0;
    {entry}(data, size);
    return 0;
}}
"""

_ATHERIS_TEMPLATE = """\
# Atheris harness for {target}.{entry}
# Run: python fuzz_{target}.py -max_total_time=60 -atheris_runs=10000
import atheris, sys
with atheris.instrument_imports():
    import {target}

def TestOneInput(data: bytes) -> None:
    try:
        {target}.{entry}(data)
    except (ValueError, TypeError):
        return  # expected input validation
    # Any other exception is interesting — let Atheris record a crash

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
"""

_JAZZER_TEMPLATE = """\
// Jazzer harness for {target}.{entry}
// Run: jazzer --cp=target.jar --target_class={target}Fuzz --instrumentation_includes={target}.**
import com.code_intelligence.jazzer.api.FuzzedDataProvider;

public class {target}Fuzz {{
    public static void fuzzerTestOneInput(FuzzedDataProvider data) {{
        try {{
            {target}.{entry}(data.consumeRemainingAsBytes());
        }} catch (IllegalArgumentException ignored) {{
        }}
    }}
}}
"""

_CARGO_FUZZ_TEMPLATE = """\
// cargo-fuzz harness for {target}::{entry}
// Create with: cargo fuzz init && cargo fuzz add {entry}
// Run with:    cargo fuzz run {entry} -- -max_total_time=60
#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {{
    let _ = {target}::{entry}(data);
}});
"""

_GO_FUZZ_TEMPLATE = """\
// Go 1.18+ native fuzzing harness for {target}.{entry}
// Run: go test -fuzz=Fuzz{entry} -fuzztime=60s
package {target}

import "testing"

func Fuzz{entry}(f *testing.F) {{
    f.Add([]byte("seed"))
    f.Fuzz(func(t *testing.T, data []byte) {{
        _, _ = {entry}(data)
    }})
}}
"""

_BOOFUZZ_TEMPLATE = """\
# boofuzz harness for {target} ({entry} protocol)
# Run: python fuzz_{target}.py
from boofuzz import *

session = Session(target=Target(connection=SocketConnection("TARGET_IP", 9999, proto="tcp")))

s_initialize("{entry}_packet")
s_string("USER", fuzzable=True)
s_delim(" ")
s_string("GUEST", fuzzable=True)
s_static("\\r\\n")

session.connect(s_get("{entry}_packet"))
session.fuzz()
"""

_TEMPLATES: dict[Engine, str] = {
    Engine.LIBFUZZER: _LIBFUZZER_TEMPLATE,
    Engine.ATHERIS: _ATHERIS_TEMPLATE,
    Engine.JAZZER: _JAZZER_TEMPLATE,
    Engine.CARGO_FUZZ: _CARGO_FUZZ_TEMPLATE,
    Engine.GO_FUZZ: _GO_FUZZ_TEMPLATE,
    Engine.BOOFUZZ: _BOOFUZZ_TEMPLATE,
    Engine.AFLPP: _LIBFUZZER_TEMPLATE,  # same harness, different driver
    Engine.HONGGFUZZ: _LIBFUZZER_TEMPLATE,
}


def harness_for(engine: Engine, target: str, entry: str = "parse") -> str:
    """Return a starter harness for ``engine`` against ``target.entry``."""
    tmpl = _TEMPLATES.get(engine)
    if tmpl is None:
        raise ValueError(f"no harness template for engine {engine.value}")
    return tmpl.format(target=target, entry=entry)


# ── Crash parsing ───────────────────────────────────────────────────────


@dataclass
class Crash:
    """A parsed sanitizer crash report."""

    sanitizer: str
    kind: str
    summary: str
    severity: Severity
    stack: list[str]
    file: str | None = None
    line: int | None = None
    raw: str = ""


_ASAN_SUMMARY = re.compile(
    r"AddressSanitizer:\s+(?P<kind>[\w\-]+).*?\n(?P<summary>SUMMARY:.*)", re.DOTALL
)
_UBSAN_LINE = re.compile(r"runtime error:\s+(?P<summary>.+)")
_STACK_FRAME = re.compile(r"#\d+\s+0x[0-9a-fA-F]+\s+in\s+(?P<frame>[^\n]+)")
_LOC_HINT = re.compile(
    r"(?P<file>[/A-Za-z0-9_.\-]+\.(?:c|cc|cpp|h|hpp|rs|go|java|py)):(?P<line>\d+)"
)

_KIND_SEVERITY = {
    "heap-buffer-overflow": Severity.CRITICAL,
    "stack-buffer-overflow": Severity.CRITICAL,
    "heap-use-after-free": Severity.CRITICAL,
    "double-free": Severity.HIGH,
    "negative-size-param": Severity.HIGH,
    "undefined-behaviour": Severity.MEDIUM,
    "signed-integer-overflow": Severity.MEDIUM,
    "null-pointer-dereference": Severity.MEDIUM,
}


def parse_asan(log: str) -> Crash | None:
    """Parse an AddressSanitizer / UBSan crash log."""
    m = _ASAN_SUMMARY.search(log)
    if m:
        kind = m.group("kind").lower()
        summary = m.group("summary").strip().splitlines()[0]
        stack = [mm.group("frame").strip() for mm in _STACK_FRAME.finditer(log)][:15]
        sev = _KIND_SEVERITY.get(kind, Severity.HIGH)
        loc = _LOC_HINT.search(log)
        return Crash(
            sanitizer="ASan",
            kind=kind,
            summary=summary,
            severity=sev,
            stack=stack,
            file=loc.group("file") if loc else None,
            line=int(loc.group("line")) if loc else None,
            raw=log[:4000],
        )
    m = _UBSAN_LINE.search(log)
    if m:
        stack = [mm.group("frame").strip() for mm in _STACK_FRAME.finditer(log)][:15]
        loc = _LOC_HINT.search(log)
        return Crash(
            sanitizer="UBSan",
            kind="undefined-behaviour",
            summary=m.group("summary"),
            severity=Severity.MEDIUM,
            stack=stack,
            file=loc.group("file") if loc else None,
            line=int(loc.group("line")) if loc else None,
            raw=log[:4000],
        )
    return None


def record_crash(graph: KnowledgeGraph, crash: Crash, *, engine: Engine) -> Node:
    """Persist a crash as a Vulnerability + CodeLocation pair in the graph."""
    label = f"[{crash.sanitizer}:{crash.kind}] {crash.summary[:80]}"
    # NOTE: ``Node.make`` binds ``kind`` positionally, so the crash "kind"
    # field is stored under ``crash_kind`` to avoid the keyword collision.
    vuln = Node.make(
        NodeKind.VULNERABILITY,
        label,
        key=f"crash::{engine.value}::{crash.file}::{crash.line}::{crash.kind}",
        severity=crash.severity.value,
        sanitizer=crash.sanitizer,
        crash_kind=crash.kind,
        summary=crash.summary,
        stack=crash.stack,
        engine=engine.value,
        source="fuzzer",
    )
    graph.upsert_node(vuln)
    if crash.file:
        loc = Node.make(
            NodeKind.CODE_LOCATION,
            f"{crash.file}:{crash.line}" if crash.line else crash.file,
            key=f"{crash.file}::{crash.line}",
            file=crash.file,
            start_line=crash.line,
        )
        graph.upsert_node(loc)
        graph.upsert_edge(Edge.make(vuln.id, loc.id, EdgeKind.DEFINED_IN))
    return vuln
