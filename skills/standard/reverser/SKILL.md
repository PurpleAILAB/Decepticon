---
name: reverser-overview
description: Root pointer for the binary reversing lane. Covers triage, string extraction, packer unpacking, symbol risk, ROP, Ghidra/r2 recon, and firmware extraction.
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

## Workflow
1. `bin_identify` — format, arch, NX/PIE
2. `bin_packer` — entropy + signature
3. If packed → follow the packer-unpacking skill, re-identify after unpack
4. `bin_strings` — category=url/ip/crypto/secret/version to seed the graph
5. `bin_symbols_report` — risk bucket classification
6. Version strings → `cve_lookup` + `cve_by_package`
7. For deeper analysis: `bin_ghidra_script` or `bin_r2_script`, write to disk, run via bash
8. Record every observation in the knowledge graph
