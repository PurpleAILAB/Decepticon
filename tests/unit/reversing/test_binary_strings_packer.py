"""Tests for binary identification, strings, packer, ROP, symbols."""

from __future__ import annotations

import os
import struct
from pathlib import Path

from decepticon.tools.reversing.binary import identify_binary
from decepticon.tools.reversing.packer import detect_packer, shannon_entropy
from decepticon.tools.reversing.rop import filter_gadgets_by_pattern, find_rop_gadgets
from decepticon.tools.reversing.scripts import ghidra_recon_script, r2_recon_script
from decepticon.tools.reversing.strings import ExtractedString, extract_strings, group_by_category
from decepticon.tools.reversing.symbols import summarize_symbols

# ── Binary identification ───────────────────────────────────────────────


def _minimal_elf64(pie: bool = False) -> bytes:
    e_type = 3 if pie else 2  # ET_DYN vs ET_EXEC
    elf = bytearray(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8)
    # e_type, e_machine, e_version
    elf += struct.pack("<HHI", e_type, 0x3E, 1)
    elf += struct.pack("<Q", 0x400400)  # e_entry
    elf += struct.pack("<Q", 0x40)  # e_phoff
    elf += struct.pack("<Q", 0x1000)  # e_shoff
    elf += struct.pack("<I", 0)  # e_flags
    elf += struct.pack("<HHHHHH", 64, 0x38, 0, 0, 0, 0)
    return bytes(elf)


class TestIdentifyBinary:
    def test_elf64(self, tmp_path: Path) -> None:
        path = tmp_path / "b.bin"
        path.write_bytes(_minimal_elf64(pie=False))
        info = identify_binary(path)
        assert info.format == "elf"
        assert info.architecture == "x86_64"
        assert info.bitness == 64
        assert info.pie is False

    def test_elf64_pie(self, tmp_path: Path) -> None:
        path = tmp_path / "b.bin"
        path.write_bytes(_minimal_elf64(pie=True))
        info = identify_binary(path)
        assert info.pie is True

    def test_pe_header(self, tmp_path: Path) -> None:
        # Build just enough PE: DOS e_lfanew at 0x3C, "PE\0\0" at offset,
        # machine at +4, optional magic at +24, entry at +24+16,
        # DllCharacteristics at +24+70.
        pe_off = 0x80
        buf = bytearray(0x200)
        buf[0:2] = b"MZ"
        buf[0x3C:0x40] = struct.pack("<I", pe_off)
        buf[pe_off : pe_off + 4] = b"PE\x00\x00"
        buf[pe_off + 4 : pe_off + 6] = struct.pack("<H", 0x8664)
        opt = pe_off + 24
        buf[opt : opt + 2] = struct.pack("<H", 0x20B)
        buf[opt + 16 : opt + 20] = struct.pack("<I", 0x1000)
        buf[opt + 70 : opt + 72] = struct.pack("<H", 0x140)
        path = tmp_path / "b.exe"
        path.write_bytes(bytes(buf))
        info = identify_binary(path)
        assert info.format == "pe"
        assert info.architecture == "x86_64"
        assert info.bitness == 64
        assert info.nx is True
        assert info.pie is True

    def test_unknown_format(self, tmp_path: Path) -> None:
        path = tmp_path / "b.bin"
        path.write_bytes(b"random bytes here")
        info = identify_binary(path)
        assert info.format == "unknown"

    def test_missing_file(self, tmp_path: Path) -> None:
        info = identify_binary(tmp_path / "missing")
        assert info.format == "unknown"
        assert any("read error" in n for n in info.notes)


# ── Strings ────────────────────────────────────────────────────────────


class TestStringsExtraction:
    def test_ascii_strings(self) -> None:
        data = b"hello world\n\x00\x01binary\x02\x00more string here"
        strings = extract_strings(data)
        texts = [s.text for s in strings]
        assert "hello world" in texts
        assert any("more string here" in t for t in texts)

    def test_category_url(self) -> None:
        data = b"visit https://evil.com/x.sh for fun"
        strings = extract_strings(data)
        assert any(s.category == "url" for s in strings)

    def test_category_ip(self) -> None:
        data = b"server 192.168.1.1 only"
        strings = extract_strings(data)
        assert any(s.category == "ip" for s in strings)

    def test_category_secret(self) -> None:
        data = b"token AKIAIOSFODNN7EXAMPLE keyfile"
        strings = extract_strings(data)
        assert any(s.category == "secret" for s in strings)

    def test_category_format_string(self) -> None:
        data = b'fmt "%s %d" used somewhere'
        strings = extract_strings(data)
        assert any(s.category == "format" for s in strings)

    def test_category_path(self) -> None:
        data = b"file /usr/bin/bash exists"
        strings = extract_strings(data)
        assert any(s.category == "path" for s in strings)

    def test_group_by_category(self) -> None:
        strings = [
            ExtractedString(offset=0, text="http://a", encoding="ascii", category="url"),
            ExtractedString(offset=10, text="a/b/c/d", encoding="ascii", category="path"),
            ExtractedString(offset=20, text="http://b", encoding="ascii", category="url"),
        ]
        grouped = group_by_category(strings)
        assert len(grouped["url"]) == 2
        assert len(grouped["path"]) == 1


# ── Packer ─────────────────────────────────────────────────────────────


class TestPacker:
    def test_entropy_bounds(self) -> None:
        assert shannon_entropy(b"") == 0.0
        assert shannon_entropy(b"aaaa") == 0.0
        high = shannon_entropy(os.urandom(4096))
        assert 7.0 <= high <= 8.0

    def test_detects_upx(self) -> None:
        data = b"UPX!" + os.urandom(2048)
        v = detect_packer(data)
        assert v.packer == "UPX"
        assert v.likely_packed is True
        assert "UPX" in v.signatures

    def test_detects_vmp(self) -> None:
        data = b"header" + b".vmp0" + os.urandom(1024)
        v = detect_packer(data)
        assert v.packer == "VMProtect"

    def test_high_entropy_no_sig(self) -> None:
        data = os.urandom(8192)
        v = detect_packer(data)
        assert v.likely_packed is True
        assert v.packer is None
        assert any("very high" in n for n in v.notes)

    def test_low_entropy_text(self) -> None:
        data = b"AAAABBBB" * 100
        v = detect_packer(data)
        assert v.likely_packed is False
        assert any("low" in n for n in v.notes)

    def test_empty_data(self) -> None:
        v = detect_packer(b"")
        assert v.likely_packed is False


# ── ROP ─────────────────────────────────────────────────────────────────


class TestRop:
    def test_finds_simple_ret(self) -> None:
        data = b"\x58\xc3"  # pop rax; ret
        gs = find_rop_gadgets(data)
        assert len(gs) == 1
        assert gs[0].ret_opcode == 0xC3

    def test_filter_by_pattern(self) -> None:
        data = b"\x48\x89\xc3\xc3\x58\xc3"
        gs = find_rop_gadgets(data)
        filtered = filter_gadgets_by_pattern(gs, "48")
        assert len(filtered) >= 1

    def test_base_offset_applied(self) -> None:
        data = b"\xc3"
        gs = find_rop_gadgets(data, base=0x400000)
        assert gs[0].offset == 0x400000

    def test_deduplicates_identical_gadgets(self) -> None:
        data = b"\xc3\xc3\xc3"
        gs = find_rop_gadgets(data, max_length=0)
        # Each \xc3 has a unique slice when max_length=0 → single byte each,
        # deduped to 1
        assert len(gs) == 1


# ── Symbols ────────────────────────────────────────────────────────────


class TestSymbols:
    def test_categorises_known_functions(self) -> None:
        r = summarize_symbols(["strcpy", "system", "socket", "IsDebuggerPresent"])
        assert "strcpy" in r.dangerous_c
        assert "system" in r.command_exec
        assert "socket" in r.network
        assert "IsDebuggerPresent" in r.anti_debug

    def test_sanitizer_detection(self) -> None:
        r = summarize_symbols(["__asan_report_load8", "__ubsan_handle_foo"])
        assert len(r.sanitizers) == 2

    def test_risk_score_nontrivial(self) -> None:
        r = summarize_symbols(["system", "strcpy", "VirtualAlloc", "ptrace"])
        assert r.risk_score() > 5

    def test_sanitizer_reduces_score(self) -> None:
        base = summarize_symbols(["system", "strcpy"]).risk_score()
        with_san = summarize_symbols(
            ["system", "strcpy", "__asan_init", "__asan_report_load"]
        ).risk_score()
        assert with_san < base


# ── Scripts ────────────────────────────────────────────────────────────


class TestScripts:
    def test_ghidra_template_non_empty(self) -> None:
        src = ghidra_recon_script("/workspace/target")
        assert "Program" in src
        assert len(src) > 200

    def test_r2_template_non_empty(self) -> None:
        src = r2_recon_script("/workspace/target")
        assert "aaa" in src
        assert "iz" in src
