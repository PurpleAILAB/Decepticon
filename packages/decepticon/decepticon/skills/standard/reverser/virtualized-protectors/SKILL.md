---
name: reverser-virtualized-protectors
description: VMProtect, VMP2, Themida, and CodeVirtualizer reversing workflow using Radare2/Ghidra facts and Back Engineering Labs research guidance.
metadata:
  subdomain: reverse-engineering
  when_to_use: "VMProtect VMP2 VMProtect2 Themida CodeVirtualizer virtualized protector devirtualization VMEnter VMEXIT VIP handler table"
  upstream_ref: "Back Engineering Labs vmp2, vmhook, and Static Devirtualization of Themida research"
---

# VMProtect / VMP2 / Themida Workflow

Use this for VMProtect 2, VMP2 tooling questions, Themida, CodeVirtualizer,
and other VM-based protectors. Do not promise automatic devirtualization.
Most wins come from disciplined recovery of VM control-flow facts.

## Source Guidance

Back Engineering Labs' public VMP2/Themida work points to one durable rule:
Avoid brittle VM-handler pattern matching. Handler layouts, opcode tables,
and dispatch glue change too easily. Prefer incremental lifting and control-flow recovery with as little VM-specific logic as possible.

## Loop

1. `bin_identify` and `bin_packer` first; record format, arch, entropy, and
   protector strings.
2. Use `bin_r2_script` or Ghidra to locate VMEnter stubs, handler-table
   references, VM context/virtual stack sections, and suspicious indirect
   dispatch loops.
3. Recover VIP movement. For VMProtect 2, track bytecode/module loads feeding
   the indirect jump. For Themida, expect branch state in VM context and trace
   the branch-taken flag through the VPC update.
4. Classify VMEXIT behavior: return to native epilog, call-shaped exit, or
   unsupported-instruction exit. Record stack displacement evidence.
5. Prefer trace/lift plans that run simple optimizations to convergence:
   constant promotion over VM-private ranges, constant folding, instruction
   combination, branch folding, dead-store/dead-dependency cleanup, and stack
   pointer rewrite.
6. If using VMP2-style tooling, treat `vmemu`/`vmprofiler`/`vmprofiler-cli`
   outputs as evidence, not ground truth. Re-check recovered paths in r2/Ghidra.
7. Write findings with exact addresses, section names, vmenter candidates,
   VMEXIT classification, VIP source, and unresolved symbolic branches.

## Report Shape

- Protector: VMProtect / VMProtect 2 / Themida / CodeVirtualizer / unknown
- Entrypoints: candidate VMEnter addresses and why
- Dispatch: handler-table location, decrypt/transform clues, indirect jump path
- VIP: source load or Themida branch flag/VPC update evidence
- VMEXIT: stack displacement and native continuation/call target
- Recovery plan: trace, lift, or manual simplification; no fake devirt claims
