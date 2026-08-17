---
name: reverser-overview
description: Root pointer for the binary reversing lane. Covers triage, Radare2 fallback, string extraction, packer unpacking, virtualized protectors, symbol risk, ROP, Ghidra deep analysis, firmware extraction, cross-version symbol migration, Go/Rust reversing, patch diffing, thick-client testing, JS reversing, and protocol reversing.
metadata:
  subdomain: reverse-engineering
  when_to_use: "reverser binary reversing triage strings packer unpack rop ghidra firmware VMProtect VMP2 Themida virtualized protectors binary diff go rust patch diff thick client javascript protocol overview routing"
  upstream_ref: "Decepticon reverser lane catalog — Ghidra, Radare2, Back Engineering VMProtect/Themida research, AFL++, libFuzzer, binwalk, and binary triage tooling"
---

# Reverser Skill Catalog

## Playbooks
| Skill | Use for |
|---|---|
| `/skills/standard/reverser/triage/SKILL.md`            | First-pass ELF/PE/Mach-O triage |
| `/skills/standard/reverser/firmware/SKILL.md`          | Router / IoT firmware extraction |
| `/skills/standard/reverser/packer-unpacking/SKILL.md`  | UPX / ASPack / Themida / VMProtect |
| `/skills/standard/reverser/virtualized-protectors/SKILL.md` | VMProtect / VMP2 / Themida workflow |
| `/skills/standard/reverser/rop-chain/SKILL.md`         | Gadget hunting for exploit dev |
| `/skills/standard/reverser/anti-debug-bypass/SKILL.md` | IsDebuggerPresent, ptrace, NtGlobalFlag |
| `/skills/standard/reverser/ghidra/SKILL.md`            | Deep Ghidra analysis — decompile, xrefs, imports, P-code |
| `/skills/standard/reverser/binary-diff/SKILL.md`       | Cross-version symbol migration to a new build |
| `/skills/standard/reverser/go-rust-reverse/SKILL.md`   | Stripped Go / Rust binaries — GoReSym, panic strings |
| `/skills/standard/reverser/patch-diff-exploit/SKILL.md` | N-day patch diffing → root cause → scoped PoC validation |
| `/skills/standard/reverser/thick-client/SKILL.md`      | Desktop thick-client testing — IPC, local storage, pinning |
| `/skills/standard/reverser/js-reverse/SKILL.md`        | JS signing/anti-bot chains — observe, capture, Node rebuild |
| `/skills/standard/reverser/protocol-reverse/SKILL.md`  | Custom binary protocols, Protobuf/gRPC, PCAP recovery |

## Workflow
1. `ghidra_status` — check Ghidra MCP bridge and headless availability
2. `bin_identify` — format, arch, NX/PIE
3. `bin_packer` — entropy + signature
4. If packed → follow the packer-unpacking skill, re-identify after unpack
5. `bin_strings` — category=url/ip/crypto/secret/version to seed the graph
6. `bin_symbols_report` — risk bucket classification
7. Version strings → `cve_lookup` + `cve_by_package`
8. `ghidra_analyze` for full analysis, or `bin_ghidra_script` / `bin_r2_script` for headless Ghidra / Radare2 fallback
9. `ghidra_decompile` on interesting functions, `ghidra_xrefs` on dangerous imports
10. Record every observation in the knowledge graph
