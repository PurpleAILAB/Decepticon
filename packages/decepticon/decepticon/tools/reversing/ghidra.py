"""Ghidra headless integration for deep binary analysis.

Drives ``analyzeHeadless`` and the Ghidra MCP bridge to give the
reverser agent real decompilation, cross-references, and function
listings without leaving the sandbox.

Two backends:
  1. **Headless** — ``analyzeHeadless`` + a postScript that dumps JSON.
     Works everywhere Ghidra is installed.  Env: ``GHIDRA_INSTALL_DIR``.
  2. **MCP bridge** — HTTP calls to a running ghidra-mcp server.
     Env: ``GHIDRA_MCP_URL`` (default ``http://127.0.0.1:8089``).

The tools auto-select: MCP when reachable, headless otherwise.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GHIDRA_INSTALL_DIR: str = os.environ.get("GHIDRA_INSTALL_DIR", "/opt/ghidra")
GHIDRA_MCP_URL: str = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")
_HEADLESS_TIMEOUT: int = int(os.environ.get("GHIDRA_HEADLESS_TIMEOUT", "300"))

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class GhidraFunction:
    name: str
    address: str
    size: int = 0
    calling_convention: str = ""
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


_GHIDRA_FUNC_KEYS: frozenset[str] = frozenset(f.name for f in dataclasses.fields(GhidraFunction))


@dataclass
class GhidraDecompilation:
    function_name: str
    address: str
    source: str
    return_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class GhidraAnalysis:
    program_name: str
    language: str
    image_base: str
    function_count: int
    functions: list[GhidraFunction] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    strings_count: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "program_name": self.program_name,
            "language": self.language,
            "image_base": self.image_base,
            "function_count": self.function_count,
        }
        if self.functions:
            d["functions"] = [f.to_dict() for f in self.functions]
        if self.imports:
            d["imports"] = self.imports
        if self.exports:
            d["exports"] = self.exports
        if self.strings_count:
            d["strings_count"] = self.strings_count
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class GhidraXref:
    from_address: str
    to_address: str
    ref_type: str
    from_function: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


# ---------------------------------------------------------------------------
# MCP bridge helpers
# ---------------------------------------------------------------------------


def _mcp_available() -> bool:
    """Check if the Ghidra MCP server is reachable."""
    try:
        req = Request(f"{GHIDRA_MCP_URL}/mcp/health", method="GET")  # noqa: S310 # nosec B310 -- hardcoded http URL, not user input
        with urlopen(req, timeout=3) as resp:  # noqa: S310 # nosec B310
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        return False


def _mcp_post(endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST to the Ghidra MCP bridge and return parsed JSON."""
    url = f"{GHIDRA_MCP_URL}{endpoint}"
    body = json.dumps(payload or {}).encode()
    req = Request(url, data=body, method="POST")  # noqa: S310 # nosec B310 -- hardcoded http URL, not user input
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=60) as resp:  # noqa: S310 # nosec B310
        return json.loads(resp.read())


def _mcp_get(endpoint: str) -> dict[str, Any]:
    """GET from the Ghidra MCP bridge."""
    url = f"{GHIDRA_MCP_URL}{endpoint}"
    req = Request(url, method="GET")  # noqa: S310 # nosec B310 -- hardcoded http URL, not user input
    with urlopen(req, timeout=60) as resp:  # noqa: S310 # nosec B310
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Headless scripts that dump structured JSON
# ---------------------------------------------------------------------------
#
# The scripts write their result to a path supplied via the ``DCP_GHIDRA_OUT``
# environment variable. We use a file rather than stdout-with-markers because:
#   1. Ghidra's logger interleaves with stdout under contention — marker-based
#      extraction was fragile and broke on long analyses.
#   2. A binary containing the marker string in its data would otherwise
#      corrupt the parse.
# The decompile script reads its target argument via ``getScriptArgs()``, which
# Ghidra populates from the positional args after ``-postScript script.py``.
# This eliminates the format-substitution attack surface that the previous
# version exposed (a function name containing ``"`` or newline could escape
# the Python string literal and execute arbitrary code in the Ghidra Jython
# interpreter).

_HEADLESS_ANALYSIS_SCRIPT = '''\
"""Ghidra postScript: dump analysis results as JSON to DCP_GHIDRA_OUT."""
import json
import os

OUT_PATH = os.environ.get("DCP_GHIDRA_OUT", "dcp_out.json")

program = currentProgram  # noqa: F821 - injected by Ghidra
fm = program.getFunctionManager()
st = program.getSymbolTable()

functions = []
for f in fm.getFunctions(True):
    functions.append({
        "name": f.getName(),
        "address": str(f.getEntryPoint()),
        "size": int(f.getBody().getNumAddresses()),
        "calling_convention": str(f.getCallingConventionName() or ""),
        "signature": str(f.getPrototypeString(False, False)),
    })

imports = [str(sym.getName()) for sym in st.getExternalSymbols()]

exports = []
for sym in st.getAllSymbols(True):
    if sym.isExternalEntryPoint():
        exports.append(str(sym.getName()))

result = {
    "program_name": str(program.getName()),
    "language": str(program.getLanguageID()),
    "image_base": "0x{:x}".format(program.getImageBase().getOffset()),
    "function_count": int(fm.getFunctionCount()),
    "functions": functions[:500],
    "imports": imports[:500],
    "exports": exports[:200],
}

with open(OUT_PATH, "w") as out:
    json.dump(result, out)
'''

_HEADLESS_DECOMPILE_SCRIPT = '''\
"""Ghidra postScript: decompile a function (target passed as script arg)."""
import json
import os

OUT_PATH = os.environ.get("DCP_GHIDRA_OUT", "dcp_out.json")

# getScriptArgs() is the Ghidra-supported way to receive arguments — Ghidra
# splits the postScript line into [script_path, *argv] and exposes argv here.
# This is the surface that replaces the previous .format()-based injection.
args = getScriptArgs()  # noqa: F821 - injected by Ghidra
target = args[0] if args else ""

from ghidra.app.decompiler import DecompInterface  # noqa: F821

program = currentProgram  # noqa: F821
fm = program.getFunctionManager()

decomp = DecompInterface()
decomp.openProgram(program)

func = None
# Try by name first
for f in fm.getFunctions(True):
    if f.getName() == target:
        func = f
        break

# Try by address
if func is None:
    try:
        addr = program.getAddressFactory().getAddress(target)
        if addr is not None:
            func = fm.getFunctionContaining(addr)
    except Exception:
        pass

if func is None:
    payload = {"error": "function not found: " + target}
else:
    res = decomp.decompileFunction(func, 60, monitor)  # noqa: F821
    source = str(res.getDecompiledFunction().getC()) if res.decompileCompleted() else ""
    payload = {
        "function_name": func.getName(),
        "address": str(func.getEntryPoint()),
        "return_type": str(func.getReturnType()),
        "source": source,
    }

with open(OUT_PATH, "w") as out:
    json.dump(payload, out)
'''

# ---------------------------------------------------------------------------
# Headless execution
# ---------------------------------------------------------------------------


def _find_analyze_headless() -> str | None:
    """Locate the analyzeHeadless script."""
    candidates = [
        Path(GHIDRA_INSTALL_DIR) / "support" / "analyzeHeadless",
        Path(GHIDRA_INSTALL_DIR) / "support" / "analyzeHeadless.bat",
        Path(GHIDRA_INSTALL_DIR) / "analyzeHeadless",
        Path(GHIDRA_INSTALL_DIR) / "analyzeHeadless.bat",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("analyzeHeadless")


def _run_headless(binary: str, script_body: str, *script_args: str) -> dict[str, Any]:
    """Run a Ghidra headless analysis with a postScript and parse JSON output.

    ``script_args`` is forwarded as positional arguments after the
    ``-postScript script.py`` token. The script reads them via Ghidra's
    ``getScriptArgs()`` — this is the safe replacement for the previous
    ``str.format()``-based injection point.

    Auto-analysis is always run. Both scripts depend on the function
    manager being populated (which only happens after analysis), so a
    conditional ``-noanalysis`` would silently return zero functions on
    the analysis path — that was a real bug in the previous version.
    """
    headless = _find_analyze_headless()
    if headless is None:
        return {
            "error": (
                f"analyzeHeadless not found. Set GHIDRA_INSTALL_DIR (tried {GHIDRA_INSTALL_DIR})"
            )
        }

    with tempfile.TemporaryDirectory(prefix="dcp_ghidra_") as tmpdir:
        script_path = Path(tmpdir) / "dcp_script.py"
        script_path.write_text(script_body, encoding="utf-8")
        project_dir = Path(tmpdir) / "project"
        project_dir.mkdir()
        out_path = Path(tmpdir) / "dcp_out.json"

        cmd = [
            headless,
            str(project_dir),
            "dcp_tmp",
            "-import",
            binary,
            "-postScript",
            str(script_path),
            *script_args,
            "-deleteProject",
        ]

        env = {**os.environ, "DCP_GHIDRA_OUT": str(out_path)}
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_HEADLESS_TIMEOUT,
                cwd=tmpdir,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"Ghidra headless timed out after {_HEADLESS_TIMEOUT}s"}
        except FileNotFoundError:
            return {"error": f"analyzeHeadless not executable: {headless}"}

        if not out_path.exists():
            # Surface returncode + stderr tail so the caller (or the agent)
            # can diagnose. analyzeHeadless usually exits 0 even on script
            # error, so the absence of the output file is the real signal.
            stderr_tail = (result.stderr or "")[-2000:]
            stdout_tail = (result.stdout or "")[-1000:]
            return {
                "error": (
                    f"Ghidra headless produced no output file (exit code {result.returncode})"
                ),
                "stderr_tail": stderr_tail,
                "stdout_tail": stdout_tail,
            }

        try:
            return json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raw = out_path.read_text(encoding="utf-8")
            return {
                "error": f"JSON parse error in Ghidra output: {exc}",
                "raw": raw[:2000],
            }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ghidra_analyze_binary(binary: str) -> GhidraAnalysis:
    """Analyze a binary with Ghidra — MCP if available, headless otherwise."""
    # Try MCP first
    if _mcp_available():
        try:
            data = _mcp_post("/mcp/analyze", {"binary_path": binary})
            return GhidraAnalysis(
                program_name=data.get("program_name", ""),
                language=data.get("language", ""),
                image_base=data.get("image_base", ""),
                function_count=data.get("function_count", 0),
                functions=[
                    GhidraFunction(**{k: v for k, v in f.items() if k in _GHIDRA_FUNC_KEYS})
                    for f in data.get("functions", [])[:500]
                ],
                imports=data.get("imports", [])[:500],
                exports=data.get("exports", [])[:200],
            )
        except Exception:
            pass  # Fall through to headless

    data = _run_headless(binary, _HEADLESS_ANALYSIS_SCRIPT)
    if "error" in data:
        return GhidraAnalysis(
            program_name="",
            language="",
            image_base="",
            function_count=0,
            error=data["error"],
        )
    return GhidraAnalysis(
        program_name=data.get("program_name", ""),
        language=data.get("language", ""),
        image_base=data.get("image_base", ""),
        function_count=data.get("function_count", 0),
        functions=[
            GhidraFunction(**{k: v for k, v in f.items() if k in _GHIDRA_FUNC_KEYS})
            for f in data.get("functions", [])[:500]
        ],
        imports=data.get("imports", [])[:500],
        exports=data.get("exports", [])[:200],
    )


def ghidra_decompile_function(binary: str, function_name: str) -> GhidraDecompilation:
    """Decompile a single function — MCP if available, headless otherwise."""
    # Try MCP
    if _mcp_available():
        try:
            data = _mcp_post(
                "/mcp/decompile",
                {
                    "binary_path": binary,
                    "function": function_name,
                },
            )
            return GhidraDecompilation(
                function_name=data.get("function_name", function_name),
                address=data.get("address", ""),
                source=data.get("source", ""),
                return_type=data.get("return_type", ""),
            )
        except Exception:
            pass

    # Validate function_name before passing to subprocess argv. Ghidra's
    # getScriptArgs() receives the argument as a string, but we still
    # refuse NUL / newline / overly-long inputs so a malformed binary
    # symbol can't break process invocation or produce confusing logs.
    if (
        not function_name
        or len(function_name) > 256
        or "\x00" in function_name
        or "\n" in function_name
        or "\r" in function_name
    ):
        return GhidraDecompilation(
            function_name=function_name,
            address="",
            source=(
                f"invalid function name: contains NUL/newline or exceeds "
                f"256 chars (len={len(function_name)})"
            ),
        )

    data = _run_headless(binary, _HEADLESS_DECOMPILE_SCRIPT, function_name)
    if "error" in data:
        return GhidraDecompilation(
            function_name=function_name,
            address="",
            source=data["error"],
        )
    return GhidraDecompilation(
        function_name=data.get("function_name", function_name),
        address=data.get("address", ""),
        source=data.get("source", ""),
        return_type=data.get("return_type", ""),
    )


def ghidra_get_xrefs(binary: str, address: str) -> list[GhidraXref]:
    """Get cross-references to an address — MCP only (headless is too slow)."""
    if not _mcp_available():
        return []
    try:
        data = _mcp_post(
            "/mcp/xrefs",
            {
                "binary_path": binary,
                "address": address,
            },
        )
        return [
            GhidraXref(
                from_address=x.get("from_address", ""),
                to_address=x.get("to_address", address),
                ref_type=x.get("ref_type", ""),
                from_function=x.get("from_function", ""),
            )
            for x in data.get("xrefs", [])[:200]
        ]
    except Exception:
        return []


def ghidra_available() -> dict[str, bool | str]:
    """Report which Ghidra backends are available."""
    return {
        "headless": _find_analyze_headless() is not None,
        "mcp": _mcp_available(),
        "ghidra_install_dir": GHIDRA_INSTALL_DIR,
        "ghidra_mcp_url": GHIDRA_MCP_URL,
    }
