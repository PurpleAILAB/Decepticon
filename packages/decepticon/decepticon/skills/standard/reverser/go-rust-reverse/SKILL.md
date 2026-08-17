---
name: reverser-go-rust-reverse
description: Reverse engineering stripped Go and Rust binaries — runtime recognition, pclntab/module-data recovery with GoReSym or redress, panic-string-driven Rust analysis, and idiomatic decompilation recovery.
metadata:
  subdomain: reverse-engineering
  when_to_use: "golang go binary rust stripped symbols goresym pclntab moduledata redress panic string rust_begin_unwind buildid tokio cargo language runtime"
  mitre_attack: T1027
  upstream_ref: "reverse-skill:skills/go-rust-reverse (github.com/zhaoxuya520/reverse-skill @ ea582f3, MIT)"
---

# Go / Rust Binary Reverse Engineering

Language-runtime-aware reversing complements generic Ghidra/radare2
work when the sample is a stripped Go or Rust build — common for modern
tooling, implants, and cross-platform malware.

## 1. Confirm the toolchain

```
bin_identify(path="/workspace/target")
bin_strings(path="/workspace/target", category_filter="version")
```

- **Go**: look for `go.buildid`, `runtime.main`, `pclntab` magic, and
  `go1.xx` build strings.
- **Rust**: look for `rust_begin_unwind`, panic strings
  (`called 'Option::unwrap()'`), and crate path fragments
  (`/cargo/registry/src/...`).

Record the runtime evidence as a property on the `file` node.

## 2. Go — recover names and metadata

```bash
# GoReSym: build info, function names, types from pclntab/moduledata
GoReSym -t -p /workspace/target > /workspace/goresym.json
# redress is an alternative when GoReSym misses a packed/tampered pclntab
redress /workspace/target
```

Then decompile with attention to Go idioms:

- `string` is a (ptr, len) pair; `slice` is (ptr, len, cap) — read
  decompiler output accordingly.
- Interface calls go through itab; chase the concrete type first.
- Network/crypto logic routes through `net/http`, `crypto/*` — resolve
  those call sites early, they frame the business logic.

## 3. Rust — panic strings first

```text
□ Collect panic messages and crate paths via strings + xrefs
□ Start analysis AT string xrefs — generics monomorphization bloats
  code, so top-down CFG walking wastes time
□ Async (tokio) functions compile to state machines — reconstruct flow
  from cross-references, not from linear decompilation
```

## 4. Dynamic assist

Frida still works on both runtimes; mind Go's stack switching and
scheduler when hooking. Prefer breakpoints driven by log/config strings
recovered in steps 2–3 over blind entry-point tracing.

## 5. Record

For each binary, log the language runtime evidence and the recovered
function-name map location:

```
kg_add_node("file", label="<sample>",
  props={"lang_runtime": "go1.22|rust-1.7x", "symbols_recovered": N,
         "goresym_report": "/workspace/goresym.json",
         "key": "go-rust:<sha256-short>"})
```

Hand off to `/skills/standard/reverser/deep-analysis/SKILL.md` once
names are restored, or `/skills/standard/reverser/malware-triage/SKILL.md`
if the sample is confirmed malicious.
