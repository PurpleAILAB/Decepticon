from __future__ import annotations

from langchain_core.tools import tool

from decepticon.tools.research import fuzz as fuzz_mod
from decepticon.tools.research._state import _json, _load, _save


# ── Fuzzing ─────────────────────────────────────────────────────────────


@tool
def fuzz_classify(root: str) -> str:
    """Classify a source tree and recommend a fuzzer engine.

    Returns the best-guess language, the default fuzz engine for it, and
    up to 20 candidate entry functions (files matching main/parse/decode/
    deserialize/handle/fuzz).

    Args:
        root: Absolute path to the source root (repo checkout or tarball
            extraction dir).
    """
    tp = fuzz_mod.classify_target(root)
    return _json(
        {
            "root": str(tp.root),
            "language": tp.language,
            "engine": tp.engine.value if tp.engine else None,
            "entry_candidates": [str(p) for p in tp.entry_candidates],
            "notes": tp.notes,
        }
    )


@tool
def fuzz_harness(engine: str, target: str, entry: str = "parse") -> str:
    """Emit a minimal starter harness for a target + engine pair.

    ENGINES: libfuzzer, afl++, honggfuzz, jazzer, atheris, cargo-fuzz,
    go-fuzz, boofuzz. Returns ready-to-compile/run source code.

    Args:
        engine: Fuzzer engine name.
        target: Module / library under test (used in template strings).
        entry: Entry function / symbol to attach the harness to.
    """
    try:
        eng = fuzz_mod.Engine(engine)
    except ValueError:
        return _json(
            {"error": f"unknown engine: {engine}", "valid": [e.value for e in fuzz_mod.Engine]}
        )
    try:
        src = fuzz_mod.harness_for(eng, target, entry)
    except ValueError as e:
        return _json({"error": str(e)})
    return _json({"engine": eng.value, "source": src})


@tool
def fuzz_record_crash(log: str, engine: str) -> str:
    """Parse an ASan/UBSan log, extract the crash, and persist it as a vuln.

    WHEN TO USE: Immediately after a fuzzer reports a crash. Paste the
    last ~1K lines of sanitizer output as ``log``. The parser extracts
    the crash kind (heap-buffer-overflow, double-free, etc.), severity,
    file:line, and the first 15 stack frames, then writes a Vulnerability
    + CodeLocation pair into the graph.

    Args:
        log: Raw sanitizer output from the fuzzer run.
        engine: Fuzzer engine that produced the crash.

    Returns:
        JSON record of the parsed crash or an error if no crash signature
        was recognised.
    """
    try:
        eng = fuzz_mod.Engine(engine)
    except ValueError:
        return _json({"error": f"unknown engine: {engine}"})
    crash = fuzz_mod.parse_asan(log)
    if crash is None:
        return _json({"error": "no ASan/UBSan signature found in log"})
    graph, path = _load()
    vuln = fuzz_mod.record_crash(graph, crash, engine=eng)
    _save(graph, path)
    return _json(
        {
            "vuln_id": vuln.id,
            "severity": crash.severity.value,
            "sanitizer": crash.sanitizer,
            "kind": crash.kind,
            "file": crash.file,
            "line": crash.line,
            "stack_depth": len(crash.stack),
        }
    )
