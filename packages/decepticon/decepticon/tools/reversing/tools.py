"""LangChain @tool wrappers for the binary reversing package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.reversing.binary import identify_binary
from decepticon.tools.reversing.ghidra import (
    ghidra_analyze_binary,
    ghidra_available,
    ghidra_decompile_function,
    ghidra_get_xrefs,
)
from decepticon.tools.reversing.hexbe import (
    hexbe_analyze_binary,
    hexbe_available,
    hexbe_decompile,
    hexbe_find_functions,
    hexbe_search_bytes,
)
from decepticon.tools.reversing.packer import detect_packer
from decepticon.tools.reversing.rop import filter_gadgets_by_pattern, find_rop_gadgets
from decepticon.tools.reversing.scripts import ghidra_recon_script, r2_recon_script
from decepticon.tools.reversing.strings import extract_strings, group_by_category
from decepticon.tools.reversing.symbols import summarize_symbols


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def bin_identify(path: str) -> str:
    """Parse a binary's header and return format, arch, bitness, NX/PIE, entry point."""
    info = identify_binary(path)
    return _json(info.to_dict())


@tool
def bin_strings(path: str, min_length: int = 5, category_filter: str = "") -> str:
    """Extract and classify strings from a binary.

    Categories: url, ip, email, path, crypto, version, format, secret,
    import, text. Pass ``category_filter`` to narrow output.
    """
    try:
        strings = extract_strings(path, min_length=min_length)
    except OSError as e:
        return _json({"error": str(e)})
    grouped = group_by_category(strings)
    if category_filter:
        if category_filter not in grouped:
            return _json({"count": 0, "strings": []})
        items = grouped[category_filter][:200]
    else:
        # Return the interesting categories with caps
        items = []
        for cat in ("url", "ip", "path", "crypto", "secret", "version", "import", "format"):
            items.extend(grouped.get(cat, [])[:50])
    return _json(
        {
            "total": len(strings),
            "category_counts": {k: len(v) for k, v in grouped.items()},
            "strings": [s.to_dict() for s in items],
        }
    )


@tool
def bin_packer(path: str) -> str:
    """Compute entropy and match packer signatures against a binary."""
    try:
        v = detect_packer(path)
    except OSError as e:
        return _json({"error": str(e)})
    return _json(v.to_dict())


@tool
def bin_rop(path: str, max_length: int = 10, limit: int = 200, pattern_hex: str = "") -> str:
    """Scan for ROP gadgets (bytes ending in a RET opcode).

    Not a disassembler — returns raw byte sequences for the agent to
    feed into Ropper / ROPgadget. ``pattern_hex`` filters to gadgets
    containing the given hex substring.
    """
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        return _json({"error": str(e)})
    gadgets = find_rop_gadgets(data, max_length=max_length)
    if pattern_hex:
        gadgets = filter_gadgets_by_pattern(gadgets, pattern_hex)
    gadgets = gadgets[:limit]
    return _json({"count": len(gadgets), "gadgets": [g.to_dict() for g in gadgets]})


@tool
def bin_symbols_report(symbols: str) -> str:
    """Classify a newline-separated list of symbol names into risk buckets.

    Accepts output from ``nm``, ``objdump -T``, ``readelf -Ws``, etc.
    """
    items = [s.strip() for s in symbols.splitlines() if s.strip()]
    report = summarize_symbols(items)
    return _json(report.to_dict())


@tool
def bin_ghidra_script(binary: str, script_name: str = "decepticon_recon.py") -> str:
    """Emit a Ghidra headless recon script body the agent can write to disk."""
    return _json({"path": script_name, "source": ghidra_recon_script(binary, script_name)})


@tool
def bin_r2_script(binary: str) -> str:
    """Emit a radare2 recon script body the agent can feed via ``r2 -i``."""
    return _json({"source": r2_recon_script(binary)})


# ---------------------------------------------------------------------------
# Ghidra deep-analysis tools
# ---------------------------------------------------------------------------


@tool
def ghidra_analyze(binary: str) -> str:
    """Run full Ghidra analysis on a binary — functions, imports, exports.

    Auto-selects backend: Ghidra MCP if a server is running, headless
    ``analyzeHeadless`` otherwise.  Returns structured JSON with up to
    500 functions, 500 imports, and 200 exports.
    """
    result = ghidra_analyze_binary(binary)
    return _json(result.to_dict())


@tool
def ghidra_decompile(binary: str, function: str) -> str:
    """Decompile a single function from a binary using Ghidra.

    ``function`` can be a symbol name (e.g. ``main``) or a hex address
    (e.g. ``0x401000``).  Returns C pseudocode from the Ghidra
    decompiler.
    """
    result = ghidra_decompile_function(binary, function)
    return _json(result.to_dict())


@tool
def ghidra_xrefs(binary: str, address: str) -> str:
    """Get cross-references to an address or symbol in a Ghidra-analyzed binary.

    Requires a running Ghidra MCP server.  Returns up to 200 xrefs
    with source function context.
    """
    xrefs = ghidra_get_xrefs(binary, address)
    return _json({"count": len(xrefs), "xrefs": [x.to_dict() for x in xrefs]})


@tool
def ghidra_status() -> str:
    """Check Ghidra availability — headless install and MCP server."""
    return _json(ghidra_available())


@tool
def re_status() -> str:
    """Report which reverse engineering backends are available."""
    return _json({"ghidra": ghidra_available(), "hexbe": hexbe_available()})


# ---------------------------------------------------------------------------
# Commercial RE backend (advanced disassembler + decompiler)
# ---------------------------------------------------------------------------


@tool
def hex_analyze(binary: str) -> str:
    """Deep binary analysis via the commercial RE backend — functions, imports, exports.

    Produces richer results than Ghidra for C++/RTTI/Go/Rust/Swift/ObjC
    targets and handles VMProtect-packed sections through the built-in
    unpacker.  Falls back gracefully when the backend is unavailable.
    """
    result = hexbe_analyze_binary(binary)
    return _json(result.to_dict())


@tool
def hex_decompile(binary: str, function: str) -> str:
    """Decompile *function* from *binary* using the advanced commercial decompiler.

    *function* can be a name or a hex address (e.g. ``0x4015a0``).
    Produces high-quality C pseudocode with advanced decompiler output
    for x86-64, ARM, MIPS, PPC, RISC-V, V850, and ARC targets.
    """
    result = hexbe_decompile(binary, function)
    return _json(result.to_dict())


@tool
def hex_find_functions(binary: str, pattern: str = "", limit: int = 200) -> str:
    """List functions in *binary*, optionally filtered by name *pattern*.

    Useful for locating VM dispatcher loops, handler tables, and integrity-
    check routines by name fragment (e.g. ``'handler'``, ``'check'``).
    """
    funcs = hexbe_find_functions(binary, pattern=pattern, limit=limit)
    return _json({"count": len(funcs), "functions": [f.to_dict() for f in funcs]})


@tool
def hex_search_bytes(binary: str, pattern: str) -> str:
    """Search for a byte pattern inside a binary (e.g. ``'55 8B EC'``).

    Returns all addresses (up to 100) where the pattern matches.  Useful
    for locating VM enter/exit stubs, known instruction sequences, and
    integrity-check code.
    """
    matches = hexbe_search_bytes(binary, pattern)
    return _json({"count": len(matches), "matches": matches})


@tool
def hex_status() -> str:
    """Check whether the commercial RE backend is available and licensed."""
    return _json(hexbe_available())


REVERSING_TOOLS = [
    # Core triage
    bin_identify,
    bin_strings,
    bin_packer,
    bin_rop,
    bin_symbols_report,
    # Script generators
    bin_ghidra_script,
    bin_r2_script,
    # Ghidra deep analysis
    ghidra_analyze,
    ghidra_decompile,
    ghidra_xrefs,
    ghidra_status,
    # Commercial RE backend
    hex_analyze,
    hex_decompile,
    hex_find_functions,
    hex_search_bytes,
    hex_status,
    # Availability probe (all backends)
    re_status,
]
