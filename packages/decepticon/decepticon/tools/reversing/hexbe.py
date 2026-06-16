"""Commercial RE backend — advanced disassembler with decompiler support.

Wraps the commercial RE suite's Python library API when the backend
installation is present and licensed on the host.

Backend discovery uses the ``DECEPTICON_HEXBE_PATH`` environment variable
(path to the installed RE suite).  When the variable is unset or the
library package is not importable, every tool gracefully degrades and
``hexbe_available()`` returns ``{"available": False}``.

All analysis runs in a subprocess so the library's global per-process
state never leaks between tool calls.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HEXBE_PATH: str = os.environ.get("DECEPTICON_HEXBE_PATH", "/opt/hexbe")
_HEXBE_PYTHON: str = os.environ.get(
    "DECEPTICON_HEXBE_PYTHON",
    sys.executable,
)
_ANALYSIS_TIMEOUT: int = int(os.environ.get("HEXBE_ANALYSIS_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class HexbeFunction:
    name: str
    address: str
    size: int = 0
    type_info: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class HexbeDecompilation:
    function_name: str
    address: str
    source: str
    arch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class HexbeAnalysis:
    binary: str
    arch: str
    file_type: str
    image_base: str
    entry_point: str
    function_count: int
    functions: list[HexbeFunction] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "binary": self.binary,
            "arch": self.arch,
            "file_type": self.file_type,
            "image_base": self.image_base,
            "entry_point": self.entry_point,
            "function_count": self.function_count,
            "imports": self.imports[:50],
            "exports": self.exports[:50],
        }
        if self.functions:
            d["functions"] = [f.to_dict() for f in self.functions[:100]]
        if self.error:
            d["error"] = self.error
        return d


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------


def hexbe_available() -> dict[str, Any]:
    """Return availability status of the commercial RE backend."""
    install_ok = Path(HEXBE_PATH).is_dir()
    try:
        result = subprocess.run(
            [_HEXBE_PYTHON, "-c", "import idapro; print('ok')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pkg_ok = result.returncode == 0 and "ok" in result.stdout
    except Exception:
        pkg_ok = False

    return {
        "available": install_ok and pkg_ok,
        "backend_path": HEXBE_PATH,
        "backend_found": install_ok,
        "library_importable": pkg_ok,
    }


# ---------------------------------------------------------------------------
# Embedded analysis script (runs inside a subprocess)
# ---------------------------------------------------------------------------

_ANALYSIS_SCRIPT = r"""
import sys, json, os, traceback

def _run():
    binary   = sys.argv[1]
    op       = sys.argv[2]
    op_args  = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    db_path  = binary + ".i64"      # write db next to the binary

    try:
        import idapro
        idapro.enable_console_messages(False)
        idapro.open_database(binary, run_auto_analysis=True)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"open failed: {e}",
                          "tb": traceback.format_exc()}))
        return

    try:
        import idc, idautils, idaapi

        if op == "analyze":
            result = _analyze(op_args, idc, idautils, idaapi)
        elif op == "decompile":
            result = _decompile(op_args, idc, idautils, idaapi)
        elif op == "functions":
            result = _functions(op_args, idc, idautils)
        elif op == "search_bytes":
            result = _search_bytes(op_args, idc, idautils)
        else:
            result = {"error": f"unknown op: {op}"}

        print(json.dumps({"ok": True, "result": result}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "tb": traceback.format_exc()}))
    finally:
        try:
            idapro.close_database(save=False)
        except Exception:
            pass
        # remove the .i64 database
        try:
            import os
            p = binary + ".i64"
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def _analyze(args, idc, idautils, idaapi):
    limit = args.get("limit", 100)
    funcs = []
    for ea in list(idautils.Functions())[:limit]:
        name = idc.get_func_name(ea)
        size = idc.get_func_attr(ea, idc.FUNCATTR_SIZE)
        funcs.append({"name": name, "address": hex(ea), "size": size})
    imports_list = []
    nimps = idaapi.get_import_module_qty()
    for i in range(nimps):
        mod = idaapi.get_import_module_name(i)
        def _cb(ea, name, _ord, _u=[]):
            if name:
                _u.append(f"{mod}::{name}")
            return True
        idaapi.enum_import_names(i, _cb)
        imports_list.extend(_cb.__closure__[0].cell_contents if _cb.__closure__ else [])
    exports_list = [f"{name}@{hex(ea)}"
                    for ea, _ord, name in idautils.Entries()
                    if name]
    return {
        "arch": idaapi.get_file_type_name(),
        "image_base": hex(idaapi.get_imagebase()),
        "entry_point": hex(idc.get_inf_attr(idc.INF_START_EA)),
        "function_count": len(list(idautils.Functions())),
        "functions": funcs,
        "imports": imports_list[:50],
        "exports": exports_list[:50],
    }


def _decompile(args, idc, idautils, idaapi):
    target = args.get("function", "")
    ea = idc.BADADDR
    if target.startswith("0x") or target.isdigit():
        ea = int(target, 0)
    else:
        ea = idc.get_name_ea_simple(target)
    if ea == idc.BADADDR:
        return {"error": f"function not found: {target}"}
    try:
        cfunc = idaapi.decompile(ea)
        if cfunc is None:
            return {"error": "advanced decompiler returned None — ensure the decompiler plugin is licensed"}
        return {
            "function": idc.get_func_name(ea),
            "address": hex(ea),
            "source": str(cfunc),
        }
    except Exception as e:
        return {"error": str(e)}


def _functions(args, idc, idautils):
    limit = args.get("limit", 200)
    pattern = args.get("pattern", "").lower()
    funcs = []
    for ea in idautils.Functions():
        name = idc.get_func_name(ea)
        if pattern and pattern not in name.lower():
            continue
        funcs.append({"name": name, "address": hex(ea),
                      "size": idc.get_func_attr(ea, idc.FUNCATTR_SIZE)})
        if len(funcs) >= limit:
            break
    return {"count": len(funcs), "functions": funcs}


def _search_bytes(args, idc, idautils):
    pattern = args.get("pattern", "")
    if not pattern:
        return {"error": "pattern required"}
    matches = []
    ea = idc.find_binary(0, idc.SEARCH_DOWN | idc.SEARCH_NEXT, pattern)
    while ea != idc.BADADDR and len(matches) < 100:
        matches.append(hex(ea))
        ea = idc.find_binary(ea + 1, idc.SEARCH_DOWN | idc.SEARCH_NEXT, pattern)
    return {"count": len(matches), "matches": matches}


_run()
"""


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def _run_hexbe(binary_path: str, op: str, **kwargs: Any) -> dict[str, Any]:
    """Run an analysis operation inside a fresh Python subprocess.

    The subprocess performs the operation, prints JSON, and exits.
    stdout is the JSON result; stderr is suppressed (suite console output).
    """
    avail = hexbe_available()
    if not avail["available"]:
        return {"error": "commercial RE backend not available", **avail}

    # Write the script to a temp file so arg quoting is not an issue.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as tmp:
        tmp.write(_ANALYSIS_SCRIPT)
        script_path = tmp.name

    # Stage a writable copy of the binary so the .i64 database can be
    # written next to it without touching the original.
    with tempfile.NamedTemporaryFile(
        suffix=Path(binary_path).suffix, delete=False
    ) as tbin:
        tbin_path = tbin.name
    import shutil
    shutil.copy2(binary_path, tbin_path)

    env = {**os.environ, "IDAUSR": str(Path.home() / ".idapro")}

    try:
        result = subprocess.run(
            [
                _HEXBE_PYTHON,
                script_path,
                tbin_path,
                op,
                json.dumps(kwargs),
            ],
            capture_output=True,
            text=True,
            timeout=_ANALYSIS_TIMEOUT,
            env=env,
        )
        raw = result.stdout.strip().splitlines()
        # Last line should be the JSON payload
        for line in reversed(raw):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"error": "no JSON output", "stderr": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": f"analysis timed out after {_ANALYSIS_TIMEOUT}s"}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        Path(script_path).unlink(missing_ok=True)
        Path(tbin_path).unlink(missing_ok=True)
        # Also clean up any .i64 / .id0 / .nam the analysis left
        for ext in (".i64", ".id0", ".id1", ".nam", ".til"):
            Path(tbin_path).with_suffix(ext).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def hexbe_analyze_binary(binary_path: str, func_limit: int = 100) -> HexbeAnalysis:
    """Run full analysis on *binary_path*, returning functions/imports/exports."""
    raw = _run_hexbe(binary_path, "analyze", limit=func_limit)
    if not raw.get("ok"):
        return HexbeAnalysis(
            binary=binary_path, arch="", file_type="", image_base="",
            entry_point="", function_count=0, error=raw.get("error", "unknown"),
        )
    r = raw["result"]
    funcs = [HexbeFunction(**f) for f in r.get("functions", [])]
    return HexbeAnalysis(
        binary=binary_path,
        arch=r.get("arch", ""),
        file_type=r.get("arch", ""),
        image_base=r.get("image_base", ""),
        entry_point=r.get("entry_point", ""),
        function_count=r.get("function_count", 0),
        functions=funcs,
        imports=r.get("imports", []),
        exports=r.get("exports", []),
    )


def hexbe_decompile(binary_path: str, function: str) -> HexbeDecompilation:
    """Decompile *function* (name or hex address) from *binary_path*."""
    raw = _run_hexbe(binary_path, "decompile", function=function)
    if not raw.get("ok"):
        return HexbeDecompilation(
            function_name=function, address="",
            source=f"/* error: {raw.get('error', 'unknown')} */",
        )
    r = raw["result"]
    if "error" in r:
        return HexbeDecompilation(
            function_name=function, address="",
            source=f"/* error: {r['error']} */",
        )
    return HexbeDecompilation(
        function_name=r.get("function", function),
        address=r.get("address", ""),
        source=r.get("source", ""),
    )


def hexbe_find_functions(
    binary_path: str, pattern: str = "", limit: int = 200
) -> list[HexbeFunction]:
    """List functions, optionally filtered by *pattern* (case-insensitive)."""
    raw = _run_hexbe(binary_path, "functions", pattern=pattern, limit=limit)
    if not raw.get("ok"):
        return []
    return [HexbeFunction(**f) for f in raw["result"].get("functions", [])]


def hexbe_search_bytes(binary_path: str, pattern: str) -> list[str]:
    """Search for a byte pattern (hex string like ``'90 90 C3'``) in the binary."""
    raw = _run_hexbe(binary_path, "search_bytes", pattern=pattern)
    if not raw.get("ok"):
        return []
    return raw["result"].get("matches", [])
