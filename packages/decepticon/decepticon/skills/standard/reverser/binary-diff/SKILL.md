---
name: reverser-binary-diff
description: Cross-version symbol migration — port function names, globals, and struct offsets from a previously analyzed binary to a new build of the same target instead of re-reversing from scratch.
metadata:
  subdomain: reverse-engineering
  when_to_use: "binary diff symbol migration cross-version bindiff diaphora ghidriff missing symbols new build offset migration rename porting version compare"
  upstream_ref: "reverse-skill:skills/binary-diff (github.com/zhaoxuya520/reverse-skill @ ea582f3, MIT)"
---

# Cross-Version Symbol Migration (Binary Diff)

Use when you have an analyzed older build of a target (named functions,
globals, struct offsets) and a new build drops with no symbols — kernel
images without published PDBs, an updated C2 implant, a patched service
binary. The goal is to make the new build analyzable fast by migrating
prior results, not to re-reverse.

Do NOT use this skill to diff two unrelated binaries — that is generic
binary diffing (BinDiff/Diaphora directly). To find what a security
patch fixed, load `/skills/standard/reverser/patch-diff-exploit/SKILL.md`.

## 1. Pick reliable anchors

Anchor quality determines everything downstream — a wrong anchor
poisons every migrated symbol that hangs off it.

| Anchor type | Reliability | Notes |
|---|---|---|
| Exported function | Highest | Name stable, address moves |
| String reference | High | String content stable, xref site moves |
| Constant / magic value | Medium | Characteristic immediates survive |
| Code pattern | Medium | Similar CFG, addresses all change |

Confirm at least one anchor pair manually before any bulk work.

## 2. Export both builds

Load both versions in Ghidra (or IDA). For each anchor function export
disassembly + decompilation from the old build (with names) and the new
build (without). Headless export works:

```bash
analyzeHeadless /workspace/ghidra_proj OldProj \
  -import /workspace/target_old -scriptPath /workspace/scripts \
  -postScript ExportFunction.java -process
```

Keep exports one function per file pair so later steps stay small.

## 3. Structured comparison (one function at a time)

Compare the old/new pair and collect every reference to symbols from
the old build's name list. Work one function per pass — never dump a
whole binary into one comparison. Emit results as YAML in five buckets:

- `found_vcall` — indirect/virtual call: `insn_va`, `vfunc_offset`, `func_name`
- `found_call` — direct call: `insn_va`, `func_name`
- `found_funcptr` — function pointer load: `insn_va`, `funcptr_name`
- `found_gv` — global reference: `insn_va`, `gv_name`
- `found_struct_offset` — struct member access: `offset`, `struct_name`, `member_name`

For medium functions (<200 lines decompiled) a fast model is enough;
escalate only when control flow is dense or output looks wrong. Cache
every result under `/workspace/diff/` to avoid paying for re-runs.

## 4. Apply in batch

```text
found_call          → rename call target
found_vcall         → comment at insn: "vcall: {func_name} @ +{offset}"
found_funcptr       → rename pointer target
found_gv            → rename global
found_struct_offset → comment at insn: "{struct_name}.{member_name}"
```

Apply via Ghidra script (`bin_ghidra_script`) or IDAPython — never
hand-rename more than a handful.

## 5. Iterate outward

Each migrated function becomes a new anchor. Step into its callees,
repeat the comparison, and keep going until all target functions are
covered. Spot-check a sample of results — automated matching is not
100%, and critical symbols must be verified by hand.

## 6. Record

```
kg_add_node("file", label="target_new.exe",
  props={"symbols_migrated": N, "anchor_strategy": "exports+strings",
         "diff_workspace": "/workspace/diff/",
         "key": "binary-diff:<target>-<old>-<new>"})
```

Hand off to `/skills/standard/reverser/ghidra/SKILL.md` for deep
analysis on the newly-named new build.
