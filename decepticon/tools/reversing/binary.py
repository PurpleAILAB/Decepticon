"""ELF / PE / Mach-O header identification.

A minimal parser — we only extract the information an agent needs to
decide whether to hand the file to Ghidra, radare2, or unpack first:

- Format (ELF / PE / Mach-O / Java class / WASM / other)
- Architecture (x86, x86_64, ARM, ARM64, MIPS, RISC-V, PowerPC)
- Bitness and endianness
- Entry point address
- NX / RELRO / PIE / Canary flags when derivable from headers

Full parsing (symbol tables, relocations) is delegated to dedicated
modules. Keeping this file standalone lets other tools depend on it
without pulling in heavy libraries.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BinaryInfo:
    """Result of ``identify_binary``."""

    path: str
    format: str
    architecture: str | None = None
    bitness: int | None = None
    endianness: str | None = None
    entry_point: int | None = None
    nx: bool | None = None
    pie: bool | None = None
    relro: str | None = None
    canary: bool | None = None
    size: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "architecture": self.architecture,
            "bitness": self.bitness,
            "endianness": self.endianness,
            "entry_point": f"0x{self.entry_point:x}" if self.entry_point is not None else None,
            "nx": self.nx,
            "pie": self.pie,
            "relro": self.relro,
            "canary": self.canary,
            "size": self.size,
            "notes": list(self.notes),
        }


# ── Magic numbers ───────────────────────────────────────────────────────

_MAGICS: dict[bytes, str] = {
    b"\x7fELF": "elf",
    b"MZ": "pe",
    b"\xcf\xfa\xed\xfe": "macho64",
    b"\xce\xfa\xed\xfe": "macho32",
    b"\xca\xfe\xba\xbe": "macho-fat",
    b"\xfe\xed\xfa\xce": "macho-big",
    b"\xfe\xed\xfa\xcf": "macho-big64",
    b"\x00asm": "wasm",
    b"\xca\xfe\xba\xbe\x00\x00\x00": "java-class",
}


# ── ELF machine codes (subset) ──────────────────────────────────────────

_ELF_MACHINE = {
    0x03: "x86",
    0x3E: "x86_64",
    0x28: "arm",
    0xB7: "arm64",
    0x08: "mips",
    0xF3: "riscv",
    0x14: "powerpc",
    0x15: "powerpc64",
    0x2B: "sparc",
    0x16: "s390",
}


# ── PE machine codes ────────────────────────────────────────────────────

_PE_MACHINE = {
    0x014C: "x86",
    0x8664: "x86_64",
    0x01C0: "arm",
    0xAA64: "arm64",
    0x0200: "ia64",
    0x0166: "mips",
}


def _detect_format(header: bytes) -> str:
    # Check longer prefixes first to avoid collisions (e.g. java-class
    # 7-byte magic vs macho-fat 4-byte magic share the same prefix).
    for magic, name in sorted(_MAGICS.items(), key=lambda x: len(x[0]), reverse=True):
        if header.startswith(magic):
            return name
    return "unknown"


def _parse_elf(data: bytes, info: BinaryInfo) -> None:
    if len(data) < 0x34:
        info.notes.append("truncated ELF header")
        return
    ei_class = data[4]
    ei_data = data[5]
    info.bitness = 64 if ei_class == 2 else 32
    info.endianness = "little" if ei_data == 1 else "big"
    fmt = "<" if ei_data == 1 else ">"
    # e_type@0x10, e_machine@0x12
    e_type, e_machine = struct.unpack(fmt + "HH", data[0x10:0x14])
    info.architecture = _ELF_MACHINE.get(e_machine, f"unknown (0x{e_machine:x})")
    if info.bitness == 64 and len(data) >= 0x40:
        entry = struct.unpack(fmt + "Q", data[0x18:0x20])[0]
    elif info.bitness == 32 and len(data) >= 0x28:
        entry = struct.unpack(fmt + "I", data[0x18:0x1C])[0]
    else:
        entry = None
    info.entry_point = entry
    info.pie = e_type == 3  # ET_DYN
    # NX: look for a PT_GNU_STACK program header with PF_X cleared.
    if info.bitness == 64 and len(data) >= 0x40:
        e_phoff = struct.unpack(fmt + "Q", data[0x20:0x28])[0]
        e_phentsize, e_phnum = struct.unpack(fmt + "HH", data[0x36:0x3A])
    elif info.bitness == 32:
        e_phoff = struct.unpack(fmt + "I", data[0x1C:0x20])[0]
        e_phentsize, e_phnum = struct.unpack(fmt + "HH", data[0x2A:0x2E])
    else:
        return
    try:
        for i in range(min(e_phnum, 64)):
            off = e_phoff + i * e_phentsize
            if off + 8 > len(data):
                break
            p_type = struct.unpack(fmt + "I", data[off : off + 4])[0]
            if info.bitness == 64:
                p_flags = struct.unpack(fmt + "I", data[off + 4 : off + 8])[0]
            else:
                # 32-bit: flags come later
                if off + 24 > len(data):
                    break
                p_flags = struct.unpack(fmt + "I", data[off + 24 : off + 28])[0]
            if p_type == 0x6474E551:  # PT_GNU_STACK
                info.nx = (p_flags & 0x1) == 0
            if p_type == 0x6474E552:  # PT_GNU_RELRO
                info.relro = "partial"  # full RELRO needs DT_BIND_NOW — out of scope
    except struct.error:
        info.notes.append("program header parse error")


def _parse_pe(data: bytes, info: BinaryInfo) -> None:
    if len(data) < 0x40:
        info.notes.append("truncated DOS header")
        return
    (pe_offset,) = struct.unpack("<I", data[0x3C:0x40])
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        info.notes.append("no PE signature")
        return
    machine = struct.unpack("<H", data[pe_offset + 4 : pe_offset + 6])[0]
    info.architecture = _PE_MACHINE.get(machine, f"unknown (0x{machine:x})")
    info.endianness = "little"
    # Optional header magic tells us 32/64
    opt_magic_off = pe_offset + 24
    if opt_magic_off + 2 <= len(data):
        magic = struct.unpack("<H", data[opt_magic_off : opt_magic_off + 2])[0]
        info.bitness = 64 if magic == 0x20B else 32
        # Entry point is at offset 16 in the optional header
        if opt_magic_off + 20 <= len(data):
            (entry,) = struct.unpack("<I", data[opt_magic_off + 16 : opt_magic_off + 20])
            info.entry_point = entry
        # DllCharacteristics at offset 70 (PE32) or 70 (PE32+) — ASLR=0x40, NX=0x100
        dll_char_off = opt_magic_off + 70
        if dll_char_off + 2 <= len(data):
            (dll_char,) = struct.unpack("<H", data[dll_char_off : dll_char_off + 2])
            info.nx = bool(dll_char & 0x100)
            info.pie = bool(dll_char & 0x40)


def identify_binary(path: str | Path, *, max_read: int = 4096) -> BinaryInfo:
    """Inspect a binary's header and return a structured summary.

    Only the first ``max_read`` bytes are touched, so this is safe to
    call on huge firmware blobs.
    """
    p = Path(path)
    info = BinaryInfo(path=str(p), format="unknown", size=0)
    try:
        info.size = p.stat().st_size
        with p.open("rb") as f:
            data = f.read(max_read)
    except OSError as e:
        info.notes.append(f"read error: {e}")
        return info
    fmt = _detect_format(data)
    info.format = fmt
    if fmt == "elf":
        _parse_elf(data, info)
    elif fmt == "pe":
        _parse_pe(data, info)
    elif fmt.startswith("macho"):
        info.bitness = 64 if "64" in fmt else 32
        info.endianness = "big" if "big" in fmt else "little"
        info.architecture = "unknown (parse deferred to radare2)"
    return info
