---
name: reverser-overview
description: Root pointer for the binary reversing lane. Covers triage, string extraction, packer unpacking, symbol risk, ROP, Ghidra deep analysis, and firmware extraction.
metadata:
  subdomain: reverse-engineering
  when_to_use: "reverser binary reversing triage strings packer unpack rop ghidra firmware overview routing"
  upstream_ref: "Decepticon reverser lane catalog — Ghidra, AFL++, libFuzzer, binwalk, and binary triage tooling"
---

# Reverser Skill Catalog

## Playbooks
| Skill | Use for |
|---|---|
| `/skills/standard/reverser/triage/SKILL.md`            | First-pass ELF/PE/Mach-O triage |
| `/skills/standard/reverser/firmware/SKILL.md`          | Router / IoT firmware extraction |
| `/skills/standard/reverser/packer-unpacking/SKILL.md`  | UPX / ASPack / Themida / VMProtect |
| `/skills/standard/reverser/rop-chain/SKILL.md`         | Gadget hunting for exploit dev |
| `/skills/standard/reverser/anti-debug-bypass/SKILL.md` | IsDebuggerPresent, ptrace, NtGlobalFlag |
| `/skills/standard/reverser/ghidra/SKILL.md`            | Deep Ghidra analysis — decompile, xrefs, imports, P-code |

## Workflow
1. `ghidra_status` — check Ghidra MCP bridge and headless availability
2. `bin_identify` — format, arch, NX/PIE
3. `bin_packer` — entropy + signature
4. If packed → follow the packer-unpacking skill, re-identify after unpack
5. `bin_strings` — category=url/ip/crypto/secret/version to seed the graph
6. `bin_symbols_report` — risk bucket classification
7. Version strings → `cve_lookup` + `cve_by_package`
8. `ghidra_analyze` for full analysis, or `bin_ghidra_script` / `bin_r2_script` as fallback
9. `ghidra_decompile` on interesting functions, `ghidra_xrefs` on dangerous imports
10. Record every observation in the knowledge graph
