"""LangChain @tool wrappers for the binary reversing package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.reversing.binary import identify_binary
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


REVERSING_TOOLS = [
    bin_identify,
    bin_strings,
    bin_packer,
    bin_rop,
    bin_symbols_report,
    bin_ghidra_script,
    bin_r2_script,
]
