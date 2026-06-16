---
name: hypervisor-vm-escape
description: "Hypervisor & virtualization vulnerability research — VM escape (guest-to-host), device-emulation bugs, and the hypercall/MMIO/PIO/virtio/DMA attack surface across QEMU/KVM, Xen, VMware (Workstation/ESXi), and Hyper-V. Maps the guest->host trust boundary: a malicious guest driving emulated devices, virtio rings, and hypercall interfaces to corrupt or disclose host memory, with QEMU/KVM labs, device fuzzing (morphuzz/Nyx concepts + the agent fuzzing tools), and a strict guest-to-host PoC bar."
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "hypervisor, virtualization, VM escape, guest-to-host, breakout, QEMU, KVM, Xen, VMware, ESXi, Workstation, Hyper-V, virtio, vring, virtqueue, MMIO, PIO, hypercall, vmcall, vmexit, device emulation, device model, SR-IOV, vfio, DMA, grant table, VMBus, SVGA, backdoor port"
  tags: hypervisor, virtualization, vm-escape, qemu, kvm, xen, vmware, device-emulation
  mitre_attack: T1611
---

# Hypervisor / Virtualization Vulnerability Research (VM Escape)

A hypervisor multiplexes one physical machine into many guests and promises a
hard isolation boundary: a fully-compromised guest (you have ring-0 / root
**inside** the VM) must not be able to read/write host memory or run code in the
host context. **VM escape** is the act of breaking that promise. The canonical,
in-scope, top-severity finding is **guest-to-host code execution** (or host
memory disclosure) reached through a **legitimately exposed virtual-hardware
interface** — not through a host-side misconfiguration or a bug that needs
prior host access.

The attacker model that makes a finding valid:
- You **own the guest**: kernel driver, arbitrary port/MMIO access, arbitrary
  guest-physical DMA, arbitrary hypercalls. That is *given*, not a vulnerability.
- The **defended boundary** is the emulator / hypervisor code that consumes
  guest-controlled bytes (device registers, descriptor rings, hypercall args)
  and runs in the **host** address space (the VMM userspace process, or the
  hypervisor kernel/EL2 context).
- A bug **counts** only if guest-controlled input crosses that boundary and
  causes memory corruption / disclosure / control-flow hijack **in the host**.

In scope (each shares this skill, surface differs):
- **QEMU/KVM** — KVM is the in-kernel CPU/MMU virtualizer (`/dev/kvm`); QEMU is
  the userspace VMM providing device emulation. Most escapes live in QEMU device
  models (`hw/`); some live in the KVM instruction emulator.
- **Xen** — Type-1 hypervisor: hypercalls, grant tables, event channels, plus a
  per-HVM-guest QEMU device model (the "device-model stubdomain"/`qemu-dm`).
- **VMware** — Workstation/Fusion/ESXi: the `vmx`/`vmm` monitor, the VMware
  Backdoor I/O port, the SVGA II display device, vmxnet3, xHCI.
- **Hyper-V** — VMBus + synthetic devices, hypercalls (`vmcall`), and the host
  user-mode worker process (`vmwp.exe`) / kernel `vmswitch`.

---

## 1. The Guest->Host Trust Boundary & Threat Model

### Privilege picture (Intel VMX shown; AMD-V/SVM is analogous)
```
 Guest                                   Host
 -----                                   ----
 ring 3  guest userspace                 VMM userspace  (QEMU process, vmwp.exe, qemu-dm)
 ring 0  guest kernel  <-- you own this  ring 0 host kernel / KVM module / vmswitch
                                         VMX root / EL2  hypervisor (Xen, ESXi vmkernel, Hyper-V hvix64)
```
A guest runs in **VMX non-root** (or AMD guest mode). Certain operations —
sensitive instructions, accesses to trapped MMIO/PIO, explicit hypercalls —
cause a **VM exit**: the CPU saves guest state to the VMCS/VMCB and transfers to
the host hypervisor at the configured exit handler. The exit reason routes the
event to KVM (in-kernel) or back out to the userspace VMM (QEMU) to *emulate*
the device the guest touched. **Every emulation handler is attack surface**: it
runs in the host context and parses values the guest fully controls.

### What is in scope vs. not
| Boundary crossed | In scope (high/critical) | Out of scope / capped |
|------------------|--------------------------|------------------------|
| Guest kernel -> QEMU process (device emulation) | OOB R/W, UAF, type confusion in `hw/*` reachable from a guest -> host RCE/leak | a bug needing QEMU started with a non-default unsafe flag the program excludes |
| Guest -> KVM (in-kernel emulator/MMIO/hypercall) | memory corruption in the host *kernel* from a guest | needs host root already; a host-only local-privesc unrelated to a guest |
| Guest -> Xen hypervisor (hypercall/grant) | host-memory disclosure/corruption from a PV/HVM guest | dom0-only issues, or needing dom0 cooperation |
| Guest -> VMware vmx/vmm | guest->host RCE via SVGA/backdoor/vmxnet3 | host UI / installer issues |
| Guest -> Hyper-V host (VMBus/hypercall) | guest->host in `vmwp.exe`/`vmswitch`/`hvix64` | bugs in the guest integration components only |

**The decisive sentence for every finding:** *"A guest with ring-0 supplies
___ via ___ (a device register / vring descriptor / hypercall arg); host code at
`file:func` uses it as ___ without ___; the result is host-side ___."* If the
"host-side ___" is just a guest crash or a guest-local effect, it is **not** an
escape.

---

## 2. The Attack Surface a Guest Can Reach

A guest can only influence the host through interfaces the platform exposes. Map
them exhaustively; each is a class of entry points.

### 2.1 Emulated device registers — MMIO & PIO
The guest reads/writes a device's MMIO region or legacy I/O port; the access
traps and lands in the device's register callbacks. In QEMU these are
`MemoryRegionOps`:
```c
static const MemoryRegionOps mydev_mmio_ops = {
    .read  = mydev_mmio_read,    /* hwaddr addr, unsigned size -> uint64_t */
    .write = mydev_mmio_write,   /* hwaddr addr, uint64_t val, unsigned size */
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1, .valid.max_access_size = 4,
};
```
The `addr` (register offset) and `val` are **guest-controlled**. Bugs: the
handler indexes an internal array/state machine with `addr` without bounding it,
or interprets `val` as a length/index/pointer-offset into a host buffer.

### 2.2 virtio rings — the highest-traffic surface
virtio (virtio-net, virtio-blk, virtio-scsi, virtio-gpu, virtio-balloon,
vhost-*) moves data through a **virtqueue** living in *guest* memory:
```
 Descriptor Table   desc[i] = { uint64 addr; uint32 len; uint16 flags; uint16 next; }
 Available Ring     guest publishes head indices it wants serviced
 Used Ring          device publishes completed indices back
```
The device walks a guest-published descriptor chain. **Everything in the chain
is guest-controlled and mutable** — `addr` is a guest-physical address, `len` is
a size, `flags & VRING_DESC_F_NEXT` chains more descriptors, `next` is the link
index. Bugs: trusting `len` for a host-side `memcpy`/loop; following `next`
without cycle/length limits (unbounded chain -> DoS or state confusion);
mapping `addr`+`len` without checking it stays in guest RAM; **double-fetch**
because the guest can rewrite a descriptor after the device validated it.

### 2.3 Hypercalls / VMCALL / Backdoor
Explicit guest->hypervisor calls with register-passed args:
- **KVM** hypercalls (`KVM_HC_*`) and paravirt MSRs; the in-kernel x86
  *instruction emulator* (`arch/x86/kvm/emulate.c`) is itself reachable when the
  guest faults on instructions KVM must decode.
- **Xen** hypercalls (`HYPERVISOR_memory_op`, `grant_table_op`,
  `mmu_update`, `event_channel_op`, ...) — args are guest pointers/handles.
- **VMware Backdoor**: the guest executes `in/out` on port `0x5658` with magic
  `0x564D5868` ('VMXh') in EAX and a command in CX; the monitor dispatches a huge
  command table (time, clipboard, drag-n-drop, RPC/`guestrpc`).
- **Hyper-V**: `vmcall`/`HvCall*` with a guest-physical input/output page.

### 2.4 Shared memory & DMA
Beyond virtio, devices do bus-master DMA via guest-physical addresses
(`pci_dma_read`/`pci_dma_write`/`dma_memory_read`/`address_space_map` in QEMU;
grant-table mappings in Xen; `MmMapIoSpace`/GPA pages in Hyper-V). The guest
controls the descriptor addresses **and** can mutate the backing memory
concurrently from another vCPU -> TOCTOU.

### 2.5 SR-IOV / VFIO / device passthrough
With passthrough, a guest drives real hardware (or a VF) and the IOMMU is the
only thing standing between guest-programmed DMA and host memory. Bugs in the
VFIO path, IOMMU group handling, or interrupt remapping become escape primitives.

---

## 3. Per-Hypervisor Surface (where the bugs actually are)

### 3.1 QEMU / KVM
- **QEMU device models — `hw/`** is the dominant escape surface (userspace, so a
  bug is host-process RCE). Hot subtrees:
  - `hw/net/` — `e1000.c`, `e1000e.c`, `rtl8139.c`, `virtio-net.c`, `vmxnet3.c`
    (descriptor/length handling; classic OOB/overflow territory).
  - `hw/block/` — `virtio-blk.c`, and `fdc.c` (the floppy controller behind
    **VENOM**, CVE-2015-3456 — a fixed-size FIFO overflow).
  - `hw/scsi/`, `hw/usb/` (`hcd-xhci.c`, `hcd-ehci.c`, `dev-*`), `hw/display/`
    (`virtio-gpu.c`, `cirrus_vga.c`, `vga.c`), `hw/char/`, `hw/audio/`,
    `hw/nvme/`, `hw/9pfs/` (virtfs path handling).
  - DMA helpers: `dma_memory_read/write`, `pci_dma_*`, `address_space_map` and
    its `*plen` truncation semantics (a mapped length can be **shorter** than
    requested — code that ignores the returned length OOBs).
- **KVM (in-kernel)** — `arch/x86/kvm/`: the MMU (`mmu/`), `vmx/` & `svm/` exit
  handlers, and **`emulate.c`** (the x86 instruction emulator invoked on MMIO and
  on instructions hardware can't virtualize). Emulator decode bugs and nested-VMX
  (`nested.c`) state handling have produced host-kernel memory-corruption escapes.
- **vhost** (`drivers/vhost/` in the host kernel) accelerates virtio in-kernel —
  same vring trust issues but the sink is the host kernel.

### 3.2 Xen
- **Hypercall surface** (`xen/common/`, `xen/arch/x86/`): `do_*` handlers for
  `memory_op`, `mmu_update`, `grant_table_op`, `event_channel_op`,
  `physdev_op`, `hvm_op`. Args are guest handles/GFNs.
- **Grant tables** (`grant_table.c`) — a guest grants another domain access to
  its pages; mis-validated grant refs/flags let a guest map memory it shouldn't.
- **p2m / shadow / HAP** paging code — GFN->MFN translation; confusion here can
  cross domains.
- **Device model**: for HVM guests Xen uses QEMU (`qemu-dm`/stubdomain) — so the
  entire QEMU `hw/` surface above also applies to Xen HVM.
- Xen publishes **XSA** advisories — read them to scope and dedup.

### 3.3 VMware (Workstation / Fusion / ESXi)
- **Backdoor** (port `0x5658`, magic `'VMXh'`): the `guestrpc` channel and the
  command dispatch table in the `vmx` process. Many historical escapes are
  command handlers that mishandle a guest-supplied RPC buffer.
- **SVGA II** virtual GPU (`svga`) — the FIFO command processor and 3D/Surface
  commands have been repeated Pwn2Own escape targets (guest-controlled command
  stream parsed in the host `vmx`).
- **vmxnet3** paravirtual NIC and **xHCI** USB controller — descriptor/length
  parsing in `vmx`.
- ESXi adds the `vmkernel` and `vmx`/`vmm` split; escapes there hit the host
  hypervisor process. Build a Workstation guest tools/driver to exercise these.

### 3.4 Hyper-V
- **VMBus** — the ring-buffer channel transport between guest VSC drivers and
  host VSPs; synthetic devices (NetVSP `vmswitch`, StorVSP, video, keyboard) are
  parsed in the host. `vmwp.exe` (the per-VM user-mode worker) and `vmswitch.sys`
  (kernel) are the host sinks.
- **Hypercalls** — `vmcall` with a guest-physical input/output page parsed by
  `hvix64.exe`/`hvax64.exe` (the hypervisor). Microsoft runs a dedicated Hyper-V
  bounty; the in-scope boundary is guest->host.
- VMBus packet headers (`vmpacket`), GPADL (guest physical address descriptor
  lists) handling, and synthetic-device message parsing are the practical bug
  factories.

---

## 4. Vulnerability Classes to Hunt (C smell + impact)

| Class | What it looks like | Where | Impact |
|-------|--------------------|-------|--------|
| **Device-emulation OOB R/W** | register handler indexes `s->buf[addr]` / `s->regs[idx]` with a guest offset/index not bounded to the array | QEMU `hw/*` MMIO/PIO callbacks, SVGA FIFO, VMBus parser | host-process OOB -> RCE/leak -> **Critical** |
| **Use-after-free** | device reset/unrealize/hotplug frees a buffer still referenced by an in-flight request or another vCPU; dangling `BHandler`/QObject | QEMU async/DMA completion, USB/SCSI request lifecycles | host UAF -> RCE -> **Critical** |
| **Integer overflow in DMA/descriptor math** | `addr + len`, `n * desc_size`, `total - hdr` on guest u32/u64 that wraps and defeats a later bounds check | virtio vring walk, DMA descriptor rings, GPADL | bounds bypass -> OOB -> **High/Crit** |
| **TOCTOU / double-fetch on shared rings** | reads `desc->len`/`desc->addr`/header twice from guest memory, or validates then re-reads; another vCPU mutates between fetches | virtio descriptors, VMBus ring, Xen grant args | check bypass -> corruption -> **High** |
| **Type / state confusion** | command/opcode arm reuses another's buffer or interprets a VALUE as a pointer; device state machine resumed in wrong state | SVGA/Backdoor command tables, virtio-gpu resource types, KVM emulator | control over host parsing -> **High/Crit** |
| **Missing bounds on guest length/offset** | `memcpy(host, guest_ptr, guest_len)` / loop bounded by guest count with no cap | any DMA/copy from a guest-supplied size | OOB -> **High/Crit** |
| **Unbounded descriptor chain / loop** | follows `desc->next` (or VMBus subchannels) with no cycle/iteration limit | virtio vring `next` chains | host hang / state exhaustion -> **Medium/High** (escalates if it corrupts) |
| **Hypercall arg / GFN validation gap** | hypercall handler trusts a guest GFN/handle/length, maps it, or treats it as in-range without checking ownership | Xen `do_*`, KVM `KVM_HC_*`, Hyper-V `HvCall*` | cross-domain/host memory access -> **Critical** |
| **`address_space_map` short-map ignored** | code requests `len` bytes, gets a shorter mapping back, but uses `len` anyway | QEMU DMA helpers | OOB on a host bounce buffer -> **High** |

For every candidate write the boundary sentence from §1, then prove
**reachability from a legitimate guest action** (a real driver write / vring
submission / hypercall), not from calling an internal function directly.

---

## 5. Build & Run a QEMU/KVM Lab for PoC

> A valid PoC is driven from **inside an unprivileged-to-the-host guest** through
> the device's normal programming interface. Build the VMM with debug symbols +
> sanitizers so a corruption is caught and attributable.

### 5.1 Build QEMU from source with AddressSanitizer
```bash
git clone https://gitlab.com/qemu-project/qemu && cd qemu
git checkout v9.0.0            # pin to the in-scope tag; dups/fixes matter
mkdir build && cd build
../configure --target-list=x86_64-softmmu \
  --enable-debug --extra-cflags="-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1" \
  --extra-ldflags="-fsanitize=address,undefined"
make -j"$(nproc)"
# the binary: ./qemu-system-x86_64  (ASan will abort + backtrace on OOB/UAF)
```

### 5.2 Boot a Linux guest with the target device attached
```bash
# KVM-accelerated; expose exactly the device under test so a guest driver can poke it
./qemu-system-x86_64 -enable-kvm -m 2048 -smp 2 -nographic \
  -kernel bzImage -initrd rootfs.cpio.gz -append "console=ttyS0 root=/dev/ram" \
  -device virtio-net-pci,netdev=n0 -netdev user,id=n0 \
  -device e1000e \
  -device qemu-xhci -device usb-storage,drive=u0 -drive id=u0,file=disk.img,if=none
# attach a debugger to the QEMU process for the corruption:
gdb -p "$(pgrep -f qemu-system-x86_64)"
```
From inside the guest, drive the device with a kernel module / direct MMIO
(`/sys/bus/pci/devices/.../resource0` mmap), legacy port I/O (`ioperm`+`outl`),
or by crafting raw virtio descriptors against the device's BAR. The trigger must
be an action a real guest can perform.

### 5.3 For Xen / VMware / Hyper-V
- **Xen**: build Xen + a dom0, boot an HVM/PV guest, issue the hypercall or grant
  op from a guest kernel module; the QEMU `hw/` surface is reachable in HVM via
  `qemu-dm`.
- **VMware**: install Workstation, run a Linux/Windows guest, write a guest
  driver that issues the Backdoor `in/out` sequence or programs SVGA FIFO / xHCI
  / vmxnet3; attach to the host `vmware-vmx` process.
- **Hyper-V**: a Windows host with the Hyper-V role; a guest VSC driver issuing
  crafted VMBus packets / `vmcall`s; debug `vmwp.exe` / `vmswitch.sys` /
  the hypervisor with the Windows kernel debugger.

---

## 6. Fuzzing the Device Surface

The device/MMIO/PIO/DMA surface is wide and uniform — fuzz it.

### 6.1 QEMU's built-in device fuzzer (qtest fuzz target)
QEMU ships an in-process, libFuzzer-based device fuzzer under `tests/qtest/fuzz/`
(OSS-Fuzz integrated). It drives `qtest` I/O — guest PIO/MMIO writes and DMA — so
the fuzzer *is* a synthetic malicious guest:
```bash
# in the QEMU source tree, configure with the fuzzer + sanitizers:
../configure --enable-fuzzing --target-list=x86_64-softmmu \
  --extra-cflags="-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1"
make -j"$(nproc)" qemu-fuzz-i386
# list the generic + per-device fuzz targets:
./qemu-fuzz-i386 --fuzz-target=help
# fuzz a device (generic-fuzz drives MMIO/PIO/DMA for the named device):
QEMU_FUZZ_ARGS="-device virtio-net,netdev=n0 -netdev user,id=n0" \
  ./qemu-fuzz-i386 --fuzz-target=generic-fuzz -max_total_time=3600 corpus/
```
**morphuzz** extends this generic fuzzer with better DMA modelling (it teaches
the fuzzer to respond to the device's DMA reads), reaching deep descriptor-ring
states — use its target/seed approach when the generic target stalls on
DMA-heavy devices (virtio, NVMe, xHCI). **Nyx** is a complementary
KVM-snapshot, coverage-guided full-VM fuzzer (KVM-Nyx + AFL++) for fuzzing
hypervisor/guest interfaces (incl. Hyper-V/KVM) from a real guest snapshot — use
it when the bug needs full-system state the in-process qtest fuzzer can't model.

### 6.2 Use the agent fuzzing tools for harness scaffolding + triage
Don't hand-roll harness boilerplate or eyeball ASan dumps:
- `fuzz_generate_harness(target_library, target_function, input_type)` → emits a
  compile-ready libFuzzer/AFL++ C harness + `compile_cmd`/`run_cmd`/sanitizer
  flags. Use it to host-lift an isolated parser (e.g. a virtio descriptor walker
  or a VMBus packet parser extracted into a standalone TU with the platform layer
  stubbed) and fuzz it directly.
- `fuzz_triage_crash(crash_output, binary_path)` → parses an ASan/UBSan/signal
  dump and returns `crash_type`, `severity`, faulting address, stack frames, and
  exploitability notes — point it at the QEMU/qemu-fuzz ASan output.
- `fuzz_status()` → reports which fuzzers/sanitizers are on PATH.

A crash from the fuzzer is a **lead**, not a finding — it must be reproduced from
a real guest action and shown to corrupt/disclose **host** state (§8).

---

## 7. Static-Review Workflow (ghidra / r2 / grep / semgrep)

```bash
# 1. clone + pin the in-scope tag, read advisories first (scope + dedup)
git clone https://gitlab.com/qemu-project/qemu && cd qemu
git tag | grep -E '^v[0-9]'         # pick the maintained release
git log --oneline -- hw/ | head     # recent device fixes = dup risk

# 2. enumerate device entry points (the guest-reachable callbacks)
grep -rn "MemoryRegionOps" hw/ | sort          # MMIO/PIO register handlers
grep -rn "VirtIODevice\|virtqueue_pop\|vring" hw/virtio/ hw/*/virtio-*.c
grep -rn "pci_dma_read\|pci_dma_write\|dma_memory_\|address_space_map" hw/

# 3. trace guest-controlled length/offset -> dangerous sink with semgrep
semgrep -l c -e 'memcpy($DST, $SRC, $LEN)' hw/          # then check $LEN provenance
semgrep -l c -e 'address_space_map($AS, $ADDR, &$PLEN, $W, $A)' hw/   # is *plen re-checked?
# index a state array with a guest offset:
grep -rn "->regs\[" hw/ | sort
```
For **VMware / Hyper-V / vendor blobs with no source**, recover the device model
or hypercall dispatcher by disassembly:
```bash
# radare2: find the backdoor/command dispatch table in vmware-vmx, or VMBus parser in vmwp.exe
r2 -A ./vmware-vmx
# >  / 0x5658        # search for the backdoor port constant
# >  axt @ <addr>    # xrefs to the dispatch table; map command-id -> handler
# ghidra: import the binary, decompile the handler, recover guest-controlled
# field offsets feeding memcpy/array-index sinks.
```
Per hit: confirm the value is **guest-controlled**, confirm **no validation
dominates the sink on all paths**, confirm **reachability from a legitimate
guest programming sequence**, then build the PoC (§5).

---

## 8. PoC Requirements (read before claiming a finding)

Hypervisor programs (QEMU/KVM, Xen XSA, VMware/Zero Day Initiative, Microsoft
Hyper-V bounty) reject PoCs that don't model a real guest:
1. **Driven from inside the guest, legitimately.** Trigger the bug by programming
   the device / issuing the hypercall the way a guest driver does (MMIO/PIO
   writes, vring submission, `vmcall`, Backdoor `in/out`). Do **not** call an
   internal emulator function directly, do **not** patch in a fake caller, do
   **not** require the VMM to be launched with a non-default unsafe flag the
   program excludes.
2. **Crash != escape.** A QEMU/ASan abort or a guest hang is the *start*. You must
   show **host-side impact**: host-process (or host-kernel/hypervisor) **memory
   corruption, control-flow hijack, or memory disclosure** — ideally guest->host
   code execution or a host memory leak. A guest-only crash/DoS is a lower tier
   (and sometimes out of scope).
3. **Respect the model.** State the boundary crossed (guest kernel -> QEMU
   process / -> KVM / -> Xen hypervisor / -> vmx / -> vmwp.exe) and which
   isolation invariant breaks. A bug needing prior **host** access is not an
   escape.
4. **Reproducible.** Exact product+version/commit, exact VMM build flags, exact
   launch command (devices attached), the exact guest-side trigger (driver
   source / MMIO+PIO sequence / vring descriptor bytes / hypercall args), and the
   observed host impact (ASan trace with host backtrace, leaked host bytes,
   hijacked RIP).

---

## 9. Findings Protocol

Write each confirmed finding to `findings/FIND-NNN.md`; one file per finding,
never overwrite:
```markdown
# FIND-001: <one-line: guest->host OOB write in QEMU virtio-net descriptor handling>
- Product / component: QEMU x86_64-softmmu — hw/net/virtio-net.c
- Affected function: <func>  (lines L..L)
- Version / commit: <tag> @ <full-sha>
- Boundary crossed: guest ring-0 (Linux driver) -> QEMU host process
- Threat-model justification: guest fully owned (given); host process memory is
  the defended boundary; invariant "<X>" is violated. Not host-only because <reason>.
- Root cause: <guest-controlled value: desc->len / MMIO offset / hypercall GFN>
  used as <sink: memcpy len / array index / mapped ptr> without <missing check>;
  <int-overflow / double-fetch / missing bounds / short-map ignored> at <file:func>.
- Reproduction:
    BUILD:   <configure flags + sanitizers>
    LAUNCH:  <exact qemu/xen/vmware/hyper-v command + devices>
    TRIGGER: <guest driver source / MMIO+PIO sequence / vring desc bytes / vmcall args>
    OBSERVE: <ASan host backtrace / leaked host bytes / hijacked control flow>
- Impact: <guest->host RCE | host memory disclosure | host-kernel/hypervisor corruption>
- Severity / CVSS: <vector + score mapped to the program's tiering>
- Suggested fix: <bound the index/length before use | checked add/mul | copy-once
  then validate | re-check address_space_map returned *plen | validate GFN ownership>
- Dedup check: not matched by <CVE/XSA/advisory IDs reviewed>.
```
Re-verify the repro from a clean build before submission.

---

## 10. Tools

| Tool | Purpose |
|------|---------|
| `qemu-system-x86_64` (debug+ASan build) | Run a guest and the device under test; ASan attributes the corruption |
| `qemu-fuzz-*` (`--enable-fuzzing`) | In-process device fuzzer (generic-fuzz / per-device) driving MMIO/PIO/DMA |
| morphuzz / Nyx (KVM-Nyx + AFL++) | DMA-aware device fuzzing (morphuzz) and full-VM snapshot fuzzing (Nyx) |
| `libvirt` / `virsh` | Manage guests, define device topologies, snapshot for repeatable triggers |
| `gdb` / `gdb-multiarch` | Attach to the VMM process (QEMU/vmx/vmwp) at the corruption; step the handler |
| `ghidra` / `r2` (radare2) | Reverse closed-source VMMs (VMware vmx, Hyper-V vmwp/vmswitch/hvix64) — recover dispatch tables & field offsets |
| `clang` + libFuzzer / AFL++ | Host-lift and fuzz isolated parsers (vring walker, VMBus packet parser) |
| ASan / UBSan / MSan (`-fsanitize=...`) | Catch host-side OOB, UAF, int-overflow, uninit reads |
| `semgrep` | Pattern-match guest-input -> sink, missing bounds, ignored `address_space_map` length |
| `grep` / `git log` / `git blame` | Enumerate `MemoryRegionOps`/virtqueue/DMA call sites; pick maintained branch; dedup vs fixes |
| `fuzz_generate_harness` / `fuzz_triage_crash` / `fuzz_status` | Agent fuzzing scaffolding + crash triage (`decepticon.tools.fuzzing`) |
