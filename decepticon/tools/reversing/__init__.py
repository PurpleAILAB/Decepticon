"""Binary reversing and firmware analysis package.

Pure-Python implementations that run without Ghidra / radare2 installed:

- ``binary``  — ELF / PE / Mach-O header parser with architecture, segment, section, and protection flag extraction
- ``strings`` — classified string extraction with URL/IP/crypto constant/version heuristics
- ``packer``  — entropy-based packer detection (UPX, ASPack, Themida hints)
- ``rop``     — ROP gadget finder operating on raw bytes via a tiny x86 disassembler
- ``symbols`` — import/export table walker + sanitizer-symbol detection
- ``scripts`` — Ghidra + r2 script generators the agent can drop on disk and run

The agent can escalate to a real disassembler via bash (radare2,
ghidra_headless, objdump) — this package is the fast first pass.
"""

from __future__ import annotations

from decepticon.tools.reversing.binary import BinaryInfo, identify_binary
from decepticon.tools.reversing.packer import PackerVerdict, detect_packer
from decepticon.tools.reversing.rop import RopGadget, find_rop_gadgets
from decepticon.tools.reversing.scripts import ghidra_recon_script, r2_recon_script
from decepticon.tools.reversing.strings import ExtractedString, extract_strings
from decepticon.tools.reversing.symbols import SymbolReport, summarize_symbols

__all__ = [
    "BinaryInfo",
    "ExtractedString",
    "PackerVerdict",
    "RopGadget",
    "SymbolReport",
    "detect_packer",
    "extract_strings",
    "find_rop_gadgets",
    "ghidra_recon_script",
    "identify_binary",
    "r2_recon_script",
    "summarize_symbols",
]
