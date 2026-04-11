"""Tiny ROP gadget finder for x86 / x86_64.

This isn't a Ropper replacement — it's a fast first pass agents can
run without installing capstone / keystone. We scan backwards from
every ``0xc3`` (RET), ``0xc2`` (RET imm16), ``0xcb`` (RETF), ``0xca``
(RETF imm16) byte and emit the preceding 1–5 instructions as a
candidate gadget. Full disassembly is deferred to real tools — we
just capture the raw bytes + offset so the agent can follow up.

For byte-level disassembly the agent should ``radare2 -qc "/R" file``
or ``ROPgadget --binary file``; this module gives them a Python
vector quickly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_RET_OPCODES = {0xC3, 0xC2, 0xCB, 0xCA}


@dataclass
class RopGadget:
    offset: int
    bytes_: bytes
    hex: str
    ret_opcode: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": f"0x{self.offset:x}",
            "hex": self.hex,
            "length": len(self.bytes_),
            "ret": f"0x{self.ret_opcode:02x}",
        }


def find_rop_gadgets(
    data: bytes,
    *,
    max_length: int = 10,
    base: int = 0,
) -> list[RopGadget]:
    """Scan ``data`` for candidate ROP gadgets.

    ``base`` is the image base address so callers can report virtual
    addresses. ``max_length`` caps the bytes preceding each RET (beyond
    ~12 the signal-to-noise drops off).
    """
    gadgets: list[RopGadget] = []
    seen: set[bytes] = set()
    for i, b in enumerate(data):
        if b not in _RET_OPCODES:
            continue
        start = max(0, i - max_length)
        candidate = data[start : i + 1]
        if candidate in seen:
            continue
        seen.add(candidate)
        gadgets.append(
            RopGadget(
                offset=base + start,
                bytes_=bytes(candidate),
                hex=candidate.hex(),
                ret_opcode=b,
            )
        )
    return gadgets


def filter_gadgets_by_pattern(gadgets: list[RopGadget], pattern_hex: str) -> list[RopGadget]:
    """Filter to gadgets containing a specific byte pattern (hex)."""
    pattern = bytes.fromhex(pattern_hex)
    return [g for g in gadgets if pattern in g.bytes_]
