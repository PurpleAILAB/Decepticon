---
name: deobfuscation-devirtualization
description: Defeat heavy obfuscation and code virtualization — VM-based protectors (VMProtect, Themida/WinLicense, custom anti-cheat VMs), control-flow flattening, MBA expressions, opaque predicates, anti-analysis; covers VM dispatcher/handler recovery, bytecode lifting, and symbolic devirtualization.
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "obfuscation deobfuscation virtualization devirtualization virtualized VMProtect VMP Themida WinLicense Enigma code virtualization virtual machine protector custom VM bytecode handler table dispatcher control flow flattening OLLVM opaque predicate MBA mixed boolean arithmetic junk code anti-disassembly packed protector anti-cheat EAC Easy Anti-Cheat BattlEye Vanguard obfuscated binary"
  tags:
    - obfuscation
    - devirtualization
    - vmprotect
    - themida
    - anti-cheat
    - symbolic-execution
    - mba
    - control-flow-flattening
    - reverse-engineering
  mitre_attack:
    - T1027
    - T1497
    - T1620
---

# Deobfuscation & Devirtualization Playbook

The hardest tier of reverse engineering. Heavy obfuscators rewrite the
original code into shapes a disassembler cannot follow; virtualizing
protectors go further and *delete the native code entirely*, replacing it
with bytecode for a custom CPU that ships inside the binary. There is no
"unpack" step that hands you back the original — you must recover the
semantics by lifting the VM.

This skill assumes you have already classified the binary as packed/
obfuscated (see `packer-unpacking`) and can run it under a debugger (see
`anti-debug-bypass`). It picks up where those stop: when the bytes you get
back are still meaningless.

> Scope reality: full devirtualization of a non-trivial routine is
> **days-to-weeks** of iterative work. NEVER try to devirtualize a whole
> module. Scope to the single security-relevant routine reached by the
> behavior you are researching, and frame the finding around the
> recovered *flaw*, not the act of devirtualizing.

---

## 1. Triage — identify the protection before touching anything

You cannot pick a strategy until you know whether you face a *packer*
(reversible: unpack → original code), an *obfuscator* (original code is
present but mangled: CFF/MBA/junk), or a *virtualizer* (original code is
gone: bytecode + VM — you must lift). Misclassifying wastes days.

```bash
# First pass: decepticon protector/packer detector (entropy + section sigs).
# Recognizes VMProtect (.vmp0/.vmp1), Themida (.themida), Enigma, ASPack,
# UPX, MPRESS, PECompact, Petite, MEW, etc.
python3 -c "from decepticon.tools.reversing.packer import detect_packer; \
import json; print(json.dumps(detect_packer('/tmp/sample'), indent=2))"

# Cross-check with Detect-It-Easy (most reliable signature DB):
diec /tmp/sample            # CLI
diec -j /tmp/sample         # JSON for parsing
detect-it-easy /tmp/sample  # GUI build if available

# Section names + entropy (virtualizers carry a huge high-entropy bytecode blob)
r2 -qc "iSj" /tmp/sample | jq -r '.[] | "\(.name)\tvsize=\(.vsize)\tH=\(.entropy)"'

# Import table — virtualized/obfuscated binaries usually have a tiny IAT
# (imports resolved dynamically by hash); a normal binary has hundreds.
rabin2 -i /tmp/sample | head -40
```

| Class | Tells | Strategy |
|---|---|---|
| Packer (UPX/ASPack/MPRESS) | known section magic, low static entropy after stub, clean OEP | unpack → static analysis (`packer-unpacking`) |
| Obfuscator (OLLVM/Tigress/custom) | code present but flattened, huge basic-block count, MBA arithmetic, opaque branches | simplify in place (§2) |
| Virtualizer (VMProtect/Themida/anti-cheat VM) | `.vmp0/.vmp1`/`.themida` sections, a dispatcher loop, a large bytecode array, RISC/CISC handler soup | lift the VM (§3–4) |

**Packing vs virtualization — the core distinction.** Packing leaves the
original x86 intact and merely hides it until runtime; once you dump the
decrypted image you analyze normal code. Virtualization *compiles a
protected function into bytecode for a bespoke virtual ISA*; the native
x86 for that function no longer exists. There is nothing to dump. You
recover behavior only by understanding the VM that interprets the
bytecode — that is devirtualization.

Note: commercial protectors **combine** layers. VMProtect/Themida pack +
obfuscate the loader and virtualize only the functions you marked. Triage
per-region, not per-file.

---

## 2. Non-virtualized obfuscation classes (defeat these first / around the VM)

Even a virtualized binary surrounds its VM with these. The VM handlers
themselves are usually built from MBA + opaque predicates, so MBA
simplification is a prerequisite for lifting, not a side quest.

### 2.1 Control-flow flattening (OLLVM `-mllvm -fla`)
The function body is shredded into basic blocks, each ending by writing a
*state variable* and jumping back to a central dispatcher `switch`. The
original CFG is recoverable by tracking the state variable.

```bash
# Symptom: one block dominates, every other block flows back to it.
r2 -A /tmp/sample
> s sym.target
> agf            # ASCII CFG — flattened functions look like a star/hub
```
Recover with symbolic/IR tooling that solves the state transitions:
- **miasm** — `miasm` symbolic execution over the IR resolves the next
  state value per block; reconnect blocks to rebuild the original CFG.
  (Canonical CEA/SSTIC tutorials cover OLLVM unflattening with miasm.)
- **D810** — open-source IDA Hex-Rays plugin that unflattens OLLVM and
  simplifies MBA at decompile time.
- **HexRaysDeob** (Rolf Rolles/FLARE) — older but the reference for
  control-flow deflattening + opaque-predicate removal in Hex-Rays.
- **Binary Ninja** MLIL + dataflow: the state var is a constant per block;
  constant-propagate it and the `switch` resolves.

### 2.2 Opaque predicates
Branches whose direction is constant (`7y² - 1 ≠ x²` is always true), used
to inject dead paths and confuse disassembly. Prune by proving the
condition constant with an SMT solver.
```python
# z3: prove a predicate is always-true (UNSAT of its negation) → dead edge
from z3 import *
x, y = BitVecs('x y', 64)
s = Solver(); s.add(7*y*y - 1 == x*x)   # negation of "always !="
print(s.check())   # unsat  => predicate constant => prune the false edge
```
Triton/miasm/angr each evaluate path constraints and report unsatisfiable
branches automatically during exploration.

### 2.3 Mixed Boolean-Arithmetic (MBA)
Identities like `x + y == (x ^ y) + 2*(x & y)` expand a single op into a
tree of and/or/xor/add that no peephole optimizer collapses. This is the
workhorse of modern obfuscation and of VM handler bodies. Simplify with
purpose-built tools (all open-source, runnable in the sandbox):

| Tool | Approach | Note |
|---|---|---|
| **SiMBA** (DenuvoSoftwareSolutions) | algebraic simplification of linear MBA | fast, deterministic; start here |
| **GAMBA** (DenuvoSoftwareSolutions) | general MBA (linear + polynomial/non-linear) | successor scope to SiMBA |
| **msynth** (mrphrazer) | oracle-guided program synthesis + Z3 | recovers semantics of unknown handler blobs |
| **Syntia** (Blazytko et al.) | MCTS program synthesis from I/O behavior | classic for synthesizing VM handler semantics |
| **Arybo** (Quarkslab) | bit-level symbolic boolean/arith canonicalization | exact, good for verification |
| **Triton** AST simplification | rewrites simplification passes over its AST | inline in a lift pipeline |

```bash
# SiMBA on an extracted expression
python3 simba.py --expr "(x ^ y) + 2*(x & y)"        # -> x + y
# Syntia / msynth synthesize a closed form from sampled I/O of a handler
python3 -m msynth simplify --expr-file handler_42.txt
```

### 2.4 Junk / dead code & instruction substitution
OLLVM `-sub` replaces `a+b` with longer equivalent sequences; junk inserts
never-read writes. Kill with **dead-store elimination + constant folding**
in any IR (miasm IR, VTIL optimizer, angr/VEX, Binary Ninja MLIL SSA). The
optimizer that collapses VM overhead in §4f also eats this.

### 2.5 Anti-disassembly
Overlapping instructions, `jmp` into the middle of an instruction, fake
opcode prefixes, `call $+5; add [rsp],N; ret` to forge returns. Linear
sweep desyncs; recursive-traversal + a debugger trace re-syncs.
```bash
objdump -d /tmp/sample          # linear sweep — will desync, shows garbage
r2 -A /tmp/sample; r2> pdf      # recursive, but verify against a trace
# Force-realign at a known-good address:
r2> s 0x140001234; pd 20
```

### 2.6 String / import obfuscation & API hashing
Imports resolved by hashing exported names (ROR13, FNV, custom). Strings
XOR/RC4-decrypted on demand. Resolve **dynamically** — let the binary do
the work and observe:
```bash
# Frida: log every LoadLibrary/GetProcAddress (and the resolved name)
frida-trace -f /tmp/sample.exe -i "GetProcAddress" -i "LoadLibrary*"
# Recover the hash→API map by hooking the resolver and dumping (name,hash).
```
For pure-static hash maps, precompute the hash of every exported symbol in
the relevant DLLs and reverse the lookup table (`flare-floss` also auto-
decodes stack/obfuscated strings: `floss /tmp/sample`).

---

## 3. The VM model — how a virtualizing protector actually works

A virtualizer is a compiler. It takes a function's x86, lowers it to a
custom bytecode ISA, embeds the bytecode + an interpreter, and replaces the
original function with a jump into the interpreter. Anatomy:

```
 native call ──► VM ENTER (vmenter)
                   • push all GP registers + EFLAGS onto a "virtual stack"
                   • set up VM context (virtual registers / scratch slots)
                   • load VPC (virtual program counter) → start of bytecode
                          │
                          ▼
              ┌──► DISPATCHER  (fetch–decode–dispatch loop)
              │      • read next opcode/operand at [VPC]
              │      • (often) decrypt it with a rolling key
              │      • index the HANDLER TABLE, jump to handler
              │            │
              │            ▼
              │      HANDLER  (one virtual instruction)
              │      • VADD/VPUSH/VPOP/VLOAD/VSTORE/VNOR/VJCC/VMEXIT...
              │      • mutates virtual stack / virtual context
              │      • advances VPC, jumps back to dispatcher
              └────────────┘
                          │ (VMEXIT handler)
                          ▼
                VM EXIT — pop virtual context back into real registers,
                          resume native execution after the call
```

**VMProtect (2.x/3.x).** RISC-like handlers — each does *one* tiny thing
(push imm, pop reg-slot, add, nor, load, store, jump). The native logic is
expressed as a long stream of these micro-ops on a stack machine
(everything reduces to `NOR` + stack ops, like a one-instruction-set
machine). Handlers are **duplicated and mutated** across builds and even
within a build (the same VADD appears as many byte-different copies), VPC
and opcodes are obfuscated/encrypted, and register slots are renamed. Key
consequence: handler *byte* signatures don't survive — you must classify by
*semantics*.

**Themida/WinLicense (Oreans).** CISC-style handlers (each handler does
more work) and selectable VM complexity tiers (the FISH / PUMA / TIGER /
SHARK / DOLPHIN family) with optional **nested VMs** — a handler can itself
be virtualized by a second, different VM. Also heavy macro/anti-debug. Much
harder than VMProtect; expect multiple interpreter layers.

**Custom anti-cheat VMs (EAC/BattlEye/Vanguard).** Per-build randomized
handler semantics, mutation, and re-keying so nothing transfers between
game patches; the VM protects only the security-critical routines
(integrity checks, detection logic). Treated in §7.

---

## 4. Devirtualization workflow

The goal is to turn the bytecode stream back into readable logic. Pipeline:

### (a) Locate VM entry / exit
The vmenter is the giveaway: a `push`/`pushfq` burst saving the full
context, then a jump into a tight loop. The dispatcher is the
hottest-executed block at runtime.
```bash
# Static: find the context-save prologue + the dispatch indirect jump
r2 -A /tmp/sample
> /c pushfq            # often near vmenter
> pdf @ entry          # inspect the stub
# Dynamic: the dispatcher is the address with the highest hit count
```

### (b) Identify the handler table and the VPC register
The dispatcher computes `handler = table[opcode]` (or `table_base +
opcode*scale`) and jumps. The register that monotonically walks the
bytecode (read, advanced each handler) is the **VPC**. The register/memory
holding the virtual stack pointer is **VSP**.
```bash
# In the dispatcher, the indirect jump's index source is the opcode;
# the base of the array it indexes is the handler table.
r2> pdf @ sym.dispatcher
# look for:  movzx eax, byte [rVPC]; jmp qword [rTABLE + rax*8]
```

### (c) Trace / record the executed handler sequence
Run the routine on a concrete input and capture which handlers fire, in
order — that *flattens* the VM for one path and is the raw material for
lifting. Use a tracer:

| Tracer | OSS | Note |
|---|---|---|
| **Intel Pin** | yes | DBI; write a pintool to log VPC + handler addr per dispatch |
| **DynamoRIO** | yes | DBI alternative; `drcov`/custom client for the trace |
| **Unicorn** | yes | full CPU emulation in-process; drive the VM from Python, no debugger |
| **qemu** (TCG plugins) | yes | system/user-mode trace via plugins |
| **TinyTracer** (hasherezade) | yes | Pin-based, logs transitions/API; good first trace |
| x64dbg scripts / Frida Stalker | yes | scripted dynamic trace on Windows |

```bash
# Unicorn skeleton: map the image, set hooks, run from vmenter, log dispatch
python3 - <<'PY'
from unicorn import *
from unicorn.x86_const import *
mu = Uc(UC_ARCH_X86, UC_MODE_64)
# map sample image + stack, write bytes, set RIP=vmenter ...
DISPATCH = 0x140001abc            # dispatcher address from §4a
log = []
def hook(uc, addr, size, _):
    if addr == DISPATCH:
        vpc = uc.reg_read(UC_X86_REG_RSI)     # whichever reg is VPC (§4b)
        op  = uc.mem_read(vpc, 1)[0]
        log.append((vpc, op))
mu.hook_add(UC_HOOK_CODE, hook)
# mu.emu_start(VMENTER, VMEXIT)
# -> `log` is the ordered (VPC, opcode) handler sequence for this input
PY
```

### (d) Lift each handler to a semantic micro-op
For every distinct handler, recover *what it does to the virtual context*
as a symbolic expression — independent of its mutated byte form. Symbolic
execution gives you the closed form.

- **Triton** (Quarkslab) — dynamic symbolic execution + taint. Symbolize
  VSP/VPC and the virtual registers, single-step a handler, read the
  output AST → that is the handler's semantics. Triton's AST simplifier
  folds the MBA the handler is built from.
- **miasm** — symbolic engine over miasm IR; `SymbolicExecutionEngine`
  yields the same per-handler effect, and miasm can re-emit IR.
- **angr** — VEX-based symbolic execution; good for solving operand
  encodings and path constraints.
- For handlers whose semantics resist symbolic solving (heavy MBA),
  **synthesize** them from I/O with **Syntia / msynth** (§2.3).

```python
# Triton: recover a handler's effect symbolically
from triton import *
ctx = TritonContext(ARCH.X86_64)
ctx.setConcreteRegisterValue(ctx.registers.rsp, VSP)
ctx.symbolizeRegister(ctx.registers.rax)         # symbolic inputs
# step the handler's instructions...
for insn_bytes, addr in handler_insns:
    i = Instruction(addr, insn_bytes); ctx.processing(i)
ast = ctx.getRegisterAst(ctx.registers.rax)
print(ctx.simplify(ast, True))   # simplified effect, e.g. (bvadd VR0 VR1)
```

### (e) Build an IR of the bytecode program
Map the ordered handler micro-ops into a real intermediate language so you
can optimize across the whole stream. **VTIL — Virtual-machine Translation
Intermediate Language** (vtil-core, by Can Bölük) is the canonical IR for
exactly this: it models a virtual register file + stack and an optimizer
designed to collapse VM-protected code. miasm IR and Binary Ninja MLIL are
viable alternatives.

### (f) Optimize / simplify the IR
This is where VM overhead dissolves back toward original logic. Run, to
fixpoint: **dead-store elimination** (the VM writes scratch slots nothing
reads), **constant folding/propagation** (decrypted opcodes, fixed VSP
deltas), **MBA simplification** (§2.3), **stack-slot coalescing** (virtual
registers → real registers), **identity/peephole** rewrites. VTIL's
optimizer pipeline does all of these; the IR shrinks by 1–2 orders of
magnitude.

### (g) Emit recovered logic
Translate the optimized IR back to native-ish instructions or readable
pseudocode / a recovered CFG, then drop it into a decompiler for a final
high-level read.

- **NoVmp** (Can Bölük) — VTIL-based **VMProtect 2/3 devirtualizer**:
  lifts VMProtect'd routines to VTIL, optimizes, and emits devirtualized
  output. The reference open-source implementation of this whole pipeline.
- **VTIL-NativeLifters** + **vtil-core** — the IR + optimizer + x86 lifter
  underneath it; reusable for custom VMs.
- **vmpattack** (Binary Ninja plugin, Can Bölük) — VMProtect lifting inside
  Binja's MLIL.

---

## 5. Tooling that exists (use the real ones)

Symbolic / IR / lifting:
- **Triton** — DSE + taint + AST simplifier. OSS, sandbox-runnable.
- **miasm** — RE framework: IR, symbolic exec, JIT, unflattening. OSS.
- **angr** — VEX-based symbolic execution + CFG recovery. OSS.
- **Unicorn** — QEMU-derived CPU emulator, scripted from Python. OSS.
- **VTIL / vtil-core** — VM-translation IR + optimizer. OSS (C++).

VMProtect-specific public research/tools:
- **NoVmp** — VTIL-based VMProtect 2/3 devirtualizer. OSS.
- **vmpattack** — Binary Ninja VMProtect lifter. OSS.
- Triton-driven VMProtect lifting writeups; **Mandiant/FLARE** VMProtect
  analysis blog posts (handler classification + deobfuscation method).

Themida/WinLicense:
- **Magicmida** — automatic unpacker for older Themida/WinLicense (loader
  layer, not the VM). OSS. Newer versions: manual + the §3–4 VM workflow.
- Oreans-unpacking communities (tuts4you/unpac.me) for per-version notes.

MBA / synthesis:
- **SiMBA**, **GAMBA** (Denuvo) — MBA simplifiers. OSS.
- **msynth**, **Syntia** (Blazytko) — synthesis-based handler recovery. OSS.
- **Arybo** (Quarkslab) — bit-level boolean/arith canonicalizer. OSS.

Tracing / DBI:
- **Intel Pin**, **DynamoRIO**, **qemu** (TCG plugins), **TinyTracer**.
  All OSS / free; sandbox-runnable (Pin/DR/qemu Linux-side).

Disassembly / decompile:
- **Ghidra** — decompiler + scripting; wired here via the **Ghidra MCP
  bridge** (launch the GUI on :8080 for the bridge). OSS.
- **radare2** — static + r2dbg. OSS, sandbox-runnable.
- **IDA Pro** + Hex-Rays (D810, HexRaysDeob unflatten/MBA plugins) —
  commercial, GUI.
- **Binary Ninja** — MLIL/HLIL, SSA dataflow, vmpattack devirt plugin —
  commercial, GUI.

Dynamic (Windows host / GUI):
- **x64dbg + ScyllaHide** (anti-anti-debug; see `anti-debug-bypass`),
  **Scylla** (dump/IAT-rebuild), **Frida** (runtime hooking, OSS,
  cross-platform), **WinDbg** (user + kernel; §6/§7).

Triage: **Detect-It-Easy** (`diec`/`die`) — protector/version ID. OSS.

> Sandbox note: Triton, miasm, angr, Unicorn, VTIL/NoVmp, Syntia/msynth/
> SiMBA/GAMBA, Pin/DynamoRIO/qemu, Ghidra, radare2, Frida are open-source
> and run in the Kali sandbox via bash. x64dbg/ScyllaHide/Scylla, IDA,
> Binary Ninja, and WinDbg kernel debugging are Windows-host/GUI and run in
> a dedicated analysis VM.

---

## 6. Anti-analysis you must defeat to even run it

Cross-reference **`anti-debug-bypass`** for the full matrix; the obfuscation-
specific ones you will hit while lifting:

| Defense | Mechanism | Counter |
|---|---|---|
| Timing checks | `rdtsc`/`rdtscp`/`QueryPerformanceCounter` deltas detect single-stepping | patch `rdtsc` to a fixed delta; ScyllaHide timing; emulate (Unicorn has no real-time skew) |
| Debugger detection | PEB.BeingDebugged, `NtQueryInformationProcess`, NtGlobalFlag | ScyllaHide; or analyze under emulation where there is no debugger to find |
| Hypervisor/VM detection | `CPUID` leaf `0x40000000` hypervisor bit, VMware backdoor `0x564D5868`, RDTSC variance | KVM `-cpu host,-hypervisor`, mask CPUID, bare-metal, or pure emulation |
| Integrity / self-checksum | hashes its own `.text`; any BP byte (0xCC) or patch trips it | hardware BPs only; emulate; or locate + neutralize the check loop |
| Exception-based control flow | SEH/VEH used as obfuscated `jmp` (deliberate `INT 3`/`#DE`/`#AC`) | register handlers in the debugger; in emulation, model the exception path explicitly |
| TLS-callback tricks | code runs before the entry point | enumerate TLS callbacks (`rabin2 -H`, IDA TLS subview) and breakpoint each |

Emulation (Unicorn/qemu) is the strongest counter to most of these because
there is no real debugger, no real timing, and a synthetic CPUID — the VM
can't detect what isn't there. The cost is you must model every memory page
and API the handlers touch.

**Kernel anti-cheat caution.** EAC/BattlEye/Vanguard ship a **kernel-mode
driver** (and Vanguard a boot-time component / hypervisor). Analyze the
driver in a **dedicated, isolated VM with a clean snapshot** — kernel
exploration crashes the box, and these drivers actively fight tampering.
NEVER analyze a kernel anti-cheat on a host you care about.

---

## 7. The virtualized anti-cheat case (EAC / BattlEye / Vanguard)

The user's motivating example and the hardest realistic target.

**What you face.** Modern Easy Anti-Cheat heavily virtualizes its critical
routines — integrity verification and detection logic — with a **custom,
mutated VM**. BattlEye does the same with its own obfuscation; Riot
**Vanguard** adds a kernel driver (`vgk.sys`) loaded at boot plus TPM/secure-
boot attestation. Crucially, the VM uses **per-build handler randomization**:
opcode→semantics mapping, handler byte forms, and keys differ between game
patches, so static handler signatures from one build are worthless on the
next. You re-derive semantics each build.

**Practical approach (scoped, realistic).**
1. **Isolated kernel-debug setup.** Two-machine **WinDbg** over a named
   pipe / network, or a VMware/Hyper-V guest with `kd` and a clean
   snapshot. Treat the guest as disposable.
2. **Identify the one routine you care about.** Don't lift the module —
   find the specific check (e.g. the function that scans for a known
   signature, or the integrity hash of a page) via behavioral triggering:
   change the thing it's supposed to catch and watch which code reacts.
3. **Capture handler traces dynamically** for *that routine only* (§4c) on
   a concrete input. Per-build randomization means dynamic trace > static
   signatures — always.
4. **Lift the handler chain** with Triton/VTIL (§4d–f), scoped to the
   handlers reached by the target behavior. Synthesize stubborn handlers
   with Syntia/msynth.
5. **Read the recovered logic** and find the **flaw**: a detection that can
   be evaded (a check with a gap, a TOCTOU window, a signature that misses
   an equivalent technique), an integrity check that doesn't cover a region,
   a parsing bug in a handler, a recoverable key/secret.

**Framing for a bounty.** The deliverable is the *bypass / logic flaw*, not
"we devirtualized a function." Devirtualization is the method; the finding
is the security consequence. Scope to **one routine**, set
**days-to-weeks** expectations, and iterate.

> Authorization: this is lawful, authorized RE for bug-bounty / security
> research only — in-scope program, owned/lab environment. Kernel
> anti-cheat work happens exclusively in an isolated, disposable VM.

---

## 8. PoC & findings bar

A finding must demonstrate a concrete **security-relevant** result, not the
mere fact of devirtualization. Acceptable outcomes:
- a **bypassable detection** (input that the check provably fails to flag),
- an **exploitable bug in a handler** (e.g. parsing/length flaw reachable
  through the VM),
- **recovered key/secret/algorithm** with a working reproduction.

Document in `findings/FIND-NNN.md`:
- **Protector + version** (e.g. VMProtect 3.x / Themida FISH / EAC build N),
- **Target routine** (address, what it does),
- **Method** — trace tool + lift tool + IR/optimizer used, scope of the
  handler chain,
- **Recovered semantics** — the simplified logic (pseudocode/IR),
- **The flaw** — precise statement of the security gap,
- **Repro** — minimal steps/input that exercise the bypass or bug.

```
findings/FIND-NNN.md   ← one finding per file, evidence + repro inline
```

---

## 9. Tools table

| Tool | Purpose | Invocation note |
|---|---|---|
| **Detect-It-Easy** (`diec`/`die`) | protector + version ID | OSS, sandbox: `diec -j /tmp/sample` |
| decepticon `packer` (`detect_packer`) | entropy + section protector triage | `from decepticon.tools.reversing.packer import detect_packer` |
| **Triton** | DSE + taint + AST/MBA simplify; handler lifting | OSS, sandbox, Python |
| **miasm** | IR, symbolic exec, OLLVM unflatten, re-emit | OSS, sandbox, Python |
| **angr** | VEX symbolic exec, CFG recovery, constraint solve | OSS, sandbox, Python |
| **Unicorn** | scripted CPU emulation, handler trace/exec | OSS, sandbox, Python |
| **VTIL / vtil-core** | VM-translation IR + optimizer | OSS, sandbox, C++ |
| **NoVmp** | VMProtect 2/3 devirtualizer (VTIL-based) | OSS, sandbox/build |
| **vmpattack** | VMProtect lifter (Binary Ninja) | OSS plugin, Binja GUI |
| **SiMBA / GAMBA** | MBA simplification (Denuvo) | OSS, sandbox, Python |
| **msynth / Syntia** | synthesis-based handler semantic recovery | OSS, sandbox, Python |
| **Arybo** | bit-level boolean/arith canonicalization | OSS, sandbox, Python |
| **Intel Pin / DynamoRIO** | DBI handler/transition tracing | free/OSS, sandbox (Linux side) |
| **qemu** (TCG plugins) / **TinyTracer** | emulation / Pin-based transition trace | OSS, sandbox |
| **Ghidra** (+ MCP bridge) | decompile + scripting | OSS; GUI on :8080 for MCP |
| **radare2** | static analysis + r2dbg | OSS, sandbox: `r2 -A` |
| **flare-floss** | auto-decode obfuscated strings | OSS, sandbox: `floss /tmp/sample` |
| **D810 / HexRaysDeob** | Hex-Rays unflatten + MBA simplify | OSS plugins, IDA GUI |
| **x64dbg + ScyllaHide** | dynamic + anti-anti-debug | Windows-host/GUI |
| **Frida** | runtime hooking, resolve API hashes | OSS, cross-platform |
| **WinDbg** (`kd`) | user + **kernel** debugging (anti-cheat) | Windows; two-machine / VM only |

---

## Cross-links
- `packer-unpacking` — classify + unpack the loader before you reach the VM.
- `anti-debug-bypass` — neutralize anti-debug/anti-VM so the routine runs.

## Known exemplars
- **VMProtect** — commodity malware loaders, banking trojans, commercial
  DRM; NoVmp/vmpattack are the public devirtualizers.
- **Themida/WinLicense** — DRM, games, malware; nested VMs, FISH→DOLPHIN tiers.
- **Denuvo Anti-Tamper** — game DRM; VM + heavy MBA (SiMBA/GAMBA origin).
- **Easy Anti-Cheat / BattlEye** — virtualized detection + integrity routines,
  per-build randomized handlers, kernel driver.
- **Riot Vanguard** — kernel driver + boot-time/TPM attestation + obfuscation.
