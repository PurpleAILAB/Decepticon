---
name: kernel-ac-internals
description: "kernel-level anti-cheat security research — EasyAntiCheat (VMProtect 2), BattlEye (VMProtect), Vanguard (proprietary packer), kernel driver internals, BYOVD, callback chains, integrity checking, hypervisor detection, DMA attack surface, and known security weaknesses from academic papers."
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "EasyAntiCheat, EAC, BattlEye, BEDaisy, Vanguard, vgk, kernel anti-cheat, kernel driver, anti-cheat driver, BYOVD, bring your own vulnerable driver, kernel bypass, ring-0, kernel callback, ObRegisterCallbacks, PatchGuard, HVCI, hypervisor protected code integrity, DMA cheat, PCILeech, kdmapper, DSE, driver signature enforcement, anti-cheat internals, EAC bypass, anti-cheat security research, kernel privilege escalation"
  tags:
    - eac
    - battleye
    - vanguard
    - kernel
    - anti-cheat
    - byovd
    - hvci
    - patchguard
    - dma
  mitre_attack:
    - T1068
    - T1014
    - T1543.003
---

# Kernel-Level Anti-Cheat Internals (security research)

Kernel anti-cheat (AC) drivers are **Ring 0 code with maximum system
privilege**, loaded onto millions of consumer machines. In a bug-bounty
context the research question is *not* "how do I bypass the cheat detection" —
it is **"where is the security flaw in this highly privileged code?"** Any
memory-corruption, arbitrary-R/W, or unchecked-IOCTL bug in `EasyAntiCheat.sys`,
`BEDaisy.sys`, or `vgk.sys` is a **local privilege escalation (LPE) to Ring 0**:
an unprivileged process turns a signed, trusted driver into a kernel-write
primitive. That is the reportable finding.

This skill is the deep methodology for that surface. It assumes you have already
classified the driver's protection (see
`reverser/deobfuscation-devirtualization`) and read the program's scope (see
`bounty-methodology`). Load both before touching a target.

> Authorization & legality: this is lawful, authorized RE for an **in-scope
> bug-bounty / VDP program or your own lab**. Riot Games, Epic Games, and others
> run programs that explicitly cover their anti-cheat components precisely
> because Ring 0 code is an LPE attack surface. "I was researching" is not a
> defence outside an authorized program — and EULA / anti-circumvention law is
> aggressively enforced against cheat tooling. Frame every finding as a *security
> defect to be fixed*, never as a usable cheat.

---

## 1. Threat model and research framing

Treat a kernel AC driver like any other signed kernel driver under audit:
- **Trust boundary:** an unprivileged (or medium-IL) user-mode process talks to
  a Ring 0 driver via IOCTLs, shared buffers, or registered callbacks. Every
  byte crossing that boundary is attacker-controlled. The vulnerability classes
  are the usual kernel ones — unchecked `METHOD_NEITHER` IOCTLs, missing
  `ProbeForRead/Write`, integer overflow on buffer sizes, double-fetch / TOCTOU,
  arbitrary `MmMapIoSpace` / physical-memory access, type confusion in the
  dispatch routine.
- **Impact ceiling:** LPE to Ring 0 (kernel arbitrary R/W → SYSTEM, or
  disable-DSE → load unsigned driver). Lower tiers: kernel info-leak
  (KASLR defeat, pool-address disclosure), or a detection bypass that the
  program counts.
- **Attack vector is Local.** Encode `AV:L` in CVSS — there is no remote vector
  for an LPE in a locally loaded driver. Do not inflate to `AV:N` (§9).

> **Two-machine WinDbg setup is mandatory.** Kernel exploration crashes the box,
> and these drivers actively fight tampering (PatchGuard, integrity self-checks,
> anti-debug). **NEVER debug a kernel AC on a host you care about.** Use a
> dedicated, disposable target machine with a clean snapshot and a separate host
> running the debugger (§8).

---

## 2. EasyAntiCheat (EAC) internals

### 2a. Architecture

EAC is a three-component design (the modern launcher/EOS split aside):

- **`EasyAntiCheat.sys`** — kernel-mode driver (Ring 0), **demand-start**:
  loaded at game launch, unloaded on exit. This is the core detection engine.
  The best annotated public reference is **`adrianyy/EACReversing`**, whose
  reconstructed source names the modules clearly: `systemthread.c` (the kernel
  system thread that drives periodic scans), `hwid.c` (hardware-ID collection),
  `kernelpatch.c` (PatchGuard / kernel-hook detection), `physmem.c` (physical
  memory access), and `driver.c` (IOCTL dispatch / device setup).
- **`EasyAntiCheat.exe`** — user-mode service. Communicates with the kernel
  driver through a **shared buffer**, aggregates results, and forwards
  encrypted telemetry to the EAC servers.
- **`EasyAntiCheat.dll`** — injected into the protected game process; hooks game
  API. After its entry point runs, the module **erases its own PE header**, and
  the `HANDLE` to `EasyAntiCheat.sys` is encoded into the now-unused space
  *after* the entry point (the back.engineering 2021 design flaw, §2d).
- **`EasyAntiCheat_EOS.sys`** — a separate, lighter variant for **Epic Online
  Services** titles. Fully reverse-engineered at
  **`TempAccountNull/EasyAntiCheat_EOS`** — a good clean starting point because
  it is far less obfuscated than the full game driver.

### 2b. VM / obfuscation layer (read this first)

**EAC.sys is protected with VMProtect 2 — not a bespoke proprietary VM.** This
matters enormously: the public VMProtect tooling (`reverser/deobfuscation-
devirtualization` §3–4) applies directly.

- **Evidence it is VMP2:** **`backengineering/vmhook`** hooks VMProtect 2's
  `READQ`/`READDW`/`READB` *virtual-instruction handlers* **inside EAC's own
  interpreter** and redirects integrity-check reads to a clean copy. That hook
  only works if the interpreter *is* the VMP2 interpreter — it confirms the VM
  family at the handler level, not by a section signature.
- **Section layout:** the `.eac0` section holds the VMP2 bytecode. EAC uses a
  **VMProtect enterprise build with custom section names** (`.eac0` instead of
  `.vmp0`/`.vmp1`) and **stripped watermarks** — cosmetic changes; the
  underlying protector is still VMP2.
- **What is virtualized:** the integrity-check comparison logic, the
  self-protection dispatch, and the hook-detection scanning.
- **What is NOT virtualized (the soft underbelly):** the **SHA-1 hash function**,
  the import-table setup, and the communications layer all run **natively**. The
  SHA-1 computation over `.text + .eac0` runs in plain x86 — which is exactly why
  patching at *section ends* (where the SHA-1 input tolerates zero-padding) is
  safe and documented in the `vmhook-eac` README.
- **Per-build instability:** handler indexes change **every time EAC is
  re-vmprotected** (typically on significant game/AC updates). Any tool that
  hooks specific handlers (`vmhook-eac`) must be re-derived per build. Use
  **dynamic traces over static signatures** for the VM layer (devirt skill §7).

### 2c. Detection mechanisms

Enumerate each as a candidate blind spot — the finding is usually "this
invariant can be violated without detection":

1. **Self-integrity.** Computes SHA-1 over `.text + .eac0`; a `vmcall` triggers a
   self-check comparing the live image against a **pool-allocated clean copy**.
   The CVEAC-2020 bypass (§2d) locates that pool copy via
   `ZwQuerySystemInformation(SystemBigPoolInformation, …)` and patches *both* the
   live image and the clean copy so the comparison still matches.
2. **Hypervisor / VM detection.** Executes `vmread` at driver init — if no `#UD`
   fires, EAC concludes it is running in **VMX root mode** (under a hypervisor)
   and blocks game launch. Also uses `rdtsc; cpuid; rdtsc` timing to detect the
   VMEXIT overhead of a thin hypervisor.
3. **`IA32_EFER` SCE-bit check.** Reads `IA32_EFER` after ~30 minutes of
   gameplay to detect syscall-hooking hypervisors that toggle the SYSCALL-Enable
   bit.
4. **Kernel callbacks.** Registers `PsSetCreateProcessNotifyRoutineEx`,
   `PsSetCreateThreadNotifyRoutine`, and `PsSetLoadImageNotifyRoutine` for
   system-wide process/thread/image monitoring (§6).
5. **Hook detection.** Scans kernel memory for hooks pointing *outside expected
   address ranges* (inline hooks, IAT/EAT redirects, SSDT-adjacent patches).
6. **Physical-memory monitoring.** The `physmem.c` module watches for
   cross-process **physical** memory access (the classic external-cheat path
   around handle stripping).
7. **Handle-table scanning.** Scans for unauthorized handles to the protected
   game process (complements the `ObRegisterCallbacks` access stripping).
8. **HWID collection.** `hwid.c` aggregates system identifiers for server-side
   ban enforcement (bans are enforced on the backend, not by the client).
9. **Driver scanning + telemetry.** Logs all loaded drivers; ships
   network-encrypted telemetry to EAC servers. The "EAC Kernel Packet Fucker"
   technique blocks the *outbound kernel-mode packets* to silence that telemetry
   — itself an interesting integrity/observability gap to study.

### 2d. Known public security findings

- **CVEAC-2020** — `thesecretclub/CVEAC-2020`. Pool-copy integrity bypass:
  uses **`.pdata` function-table entries** to locate the integrity-check routine
  *without* reversing the VMP2 bytecode, then patches the live image and the
  pool clean copy together. Writeup:
  `secret.club/2020/04/08/eac_integrity_check_bypass.html`.
- **vmhook-eac** — `backengineering/vmhook`. Runtime hook of VMP2's
  `READQ/READDW/READB` handlers, redirecting integrity reads to a clean clone.
  This is the load-bearing evidence that **EAC is VMP2** (§2b). Handler indexes
  are version-specific; the README is explicit that "plenty of detection
  vectors" remain — it defeats *one* check, not the whole driver.
- **EAC design flaw (back.engineering, Aug 2021).** `EasyAntiCheat.dll` encodes
  the `HANDLE` to `EasyAntiCheat.sys` into the post-entry-point space *after*
  erasing its own PE header. An attacker who reads that handle can **talk
  directly to the kernel driver** — granting thread creation and hook placement
  *inside* EAC-protected processes. A textbook case of the AC's own design being
  the attack surface.
- **Apex Legends ALGS incident (March 2024).** During a live tournament,
  streamers had cheats activated mid-match on EAC-protected clients. **EAC
  publicly denied a kernel-driver RCE**; the official root cause was left
  unresolved (game-engine vector or pre-compromised machines suspected). Useful
  as a reminder that "the AC says it wasn't us" is a claim to verify, not accept.

---

## 3. BattlEye (`BEDaisy.sys`)

- **VM layer.** A **heavily customized VMProtect build**. The `.be0` section is
  ~**7.4 MB of VMP bytecode**. All kernel-API imports are **resolved at runtime**
  into a hidden table in `.data`, so static analysis sees **no normal import
  table** — you recover the API map dynamically (hook the resolver, dump
  `(name, address)` pairs).
- **Static-analysis reality.** Per **`Aki2k/BEDaisy`** annotations, essentially
  *everything in `.text` calls into the `.be0` VMP bytecode* — the native `.text`
  is a thin trampoline layer over the VM. The `adrianyy` / `s4dbrd.github.io`
  (March 2026) blog post gives a detailed modern static analysis.
- **Detection mechanisms.** `PsSetCreate*` callbacks (registers **all three**
  Ps\* notify routines system-wide), handle-table scanning, **APC-based stack
  walking**, section-mapping integrity checks, and **minifilter filesystem
  monitoring** for game-file modification (§6).
- **Academic analysis.** *"Battling The Eye: Exploring the Anti-Cheat Techniques
  of BattlEye"* (CheckMATE / MATE Workshop **2025**,
  `dl.acm.org/doi/10.1145/3733817.3762701`) is the **first formal security
  analysis of BattlEye via RE**. It identifies design weaknesses that allow
  loading an **unsigned driver despite BattlEye**, and demonstrates a PoC that
  performs **persistent arbitrary writes into the game process without a ban** —
  a concrete, reportable integrity break, not a theoretical one.

---

## 4. Vanguard (`vgk.sys`)

Riot's Vanguard is the most intrusive of the three and the highest bar.

- **Boot-start driver.** `vgk.sys` is `SERVICE_BOOT_START` — loaded **before
  most of system init**, so it observes *every subsequent driver load*. This is
  fundamentally more invasive than EAC/BattlEye's demand-start model.
- **VM / packer layer.** Vanguard uses a **proprietary "Packman" packer** —
  binary encryption decrypted at launch time. It is **NOT VMProtect**; there is
  **no public devirt tooling**, and it blocks static analysis entirely until you
  recover the launch-time decryption.
- **Shadow memory.** Cloned page tables with a whitelist; guarded kernel memory
  enforced via **`SwapContext` hooks**. Documented at
  `reversing.info/posts/guardedregions/`.
- **Syscall hooks.** Full dispatch-table hooks. `archie-osu.github.io`
  (April 2025) published the **first public full list of hooked syscalls**.
- **HVCI mandatory.** Vanguard has **required HVCI since July 10, 2024**, which
  by itself defeats most BYOVD mapping (§5, §7).
- **DMA defense (the deepest of any mainstream AC).** PCIe bus scanning at launch
  (since Jan 2024); **honeypotted memory regions**; randomized **A/B testing for
  spoofed USB controllers**; FPGA-as-WiFi-card detection; and — first for a
  mainstream AC — **IOMMU enforcement for flagged accounts (May 2026)**,
  hardware-level DMA blocking (§7).
- **Bounty.** Riot runs an **active bug-bounty program** and Vanguard is
  **explicitly in scope** — Ring 0 code is treated as LPE attack surface. This is
  the canonical "authorized kernel AC research" target.

---

## 5. BYOVD — Bring Your Own Vulnerable Driver

The dominant technique (2024–2026) for getting unsigned code into the kernel,
relevant both to AC research and to security research broadly. The workflow:

1. **Find a legitimate WHQL-signed driver with a dangerous IOCTL** — arbitrary
   kernel R/W, `MmMapIoSpace` with attacker-controlled physical address/size,
   unchecked MSR or control-register writes, etc.
2. **Load it via `CreateService` / `StartService`.** **DSE passes it** because it
   is validly Microsoft-/vendor-signed.
3. **Exploit the IOCTL** to either patch out DSE (e.g. the `CiCallbacks` /
   `g_CiOptions` route) or **directly map an unsigned driver** into kernel space.
4. **Common BYOVD targets:** MSI, Gigabyte, ASUS, and Intel NIC drivers (the
   `iqvw64e.sys` family below).
5. **AC detection of mapped drivers:** scan for **compiler byte patterns**
   (`_GSHandlerCheckCommon`, statically-linked `memset`/`memcpy` signatures) in
   **unregistered memory regions** — these survive even after the mapped image's
   PE header is erased, because the *code body* still matches.
6. **HVCI defeats most BYOVD.** Under VTL1, **all kernel code must be
   Microsoft-signed before it executes**, so a *mapped* unsigned driver **cannot
   run** even though a vulnerable signed driver still loads. As of 2025–2026,
   **no reliable public HVCI bypass exists** — HVCI is the practical wall (§7).
7. **`kdmapper`** — the classic BYOVD mapper exploiting **`iqvw64e.sys`** (Intel
   NIC). It cleans `PiDDBCacheTable`, `MmUnloadedDrivers`, and
   `g_KernelHashBucketList` to hide the load — but the **mapped payload is now
   detectable by the byte-pattern scan of step 5**, and it is blocked entirely
   under HVCI.

---

## 6. Kernel callback chain

What kernel ACs register (common across EAC, BattlEye, Vanguard, FACEIT). Each
is both a detection mechanism *and* a piece of attack surface (a bug in the
callback runs in the registering driver's Ring 0 context):

- **`ObRegisterCallbacks`** — the most critical. Invoked when a handle to a
  process/thread object is **opened or duplicated**. The AC uses the
  pre-operation callback to **strip dangerous access rights**
  (`PROCESS_VM_READ`, `PROCESS_VM_WRITE`, `PROCESS_VM_OPERATION`) from any handle
  to the protected game process opened by a non-AC process. Defeating handle
  stripping is the classic external-cheat path; a flaw in the callback's filter
  logic is the *research* finding.
- **`PsSetCreateProcessNotifyRoutineEx`** — notified on process
  creation/exit; the AC checks the parent process's integrity.
- **`PsSetCreateThreadNotifyRoutine`** — thread-creation monitoring; detects
  remote-thread injection into the protected process.
- **`PsSetLoadImageNotifyRoutine`** — image/driver load notifications; the AC
  checks each loaded module against its allowlist.
- **Minifilter (`IoRegisterFsFilterCallbacks` / FltRegisterFilter)** —
  filesystem monitoring for game-file modification.

---

## 7. HVCI and the hypervisor layer

- **What HVCI does.** Hyper-V's **VTL1 secure kernel** enforces that **all
  kernel-mode code pages are signed before execution**, independently of
  PatchGuard. Patches to kernel memory are caught and reverted; **mapped unsigned
  drivers cannot execute**. This is the structural defeat of most BYOVD (§5.6).
- **DSE bypass routes and why they fail under HVCI:**
  - `SepInitializeCodeIntegrity` / `CiInitialize` patch at boot (**EfiGuard**) —
    **fully blocked by HVCI**.
  - `SetVariable` hook (EfiGuard alternate mode) — **also blocked**.
  - Both EfiGuard modes are explicitly documented as **ineffective against
    HVCI**.
- **Historical HVCI bypasses (patched).**
  - **CVE-2024-21305** (Jan 2024) — `tandasat`'s GitHub PoC: arbitrary
    kernel-mode execution within the root partition, bypassing HVCI. Patched.
  - **CVE-2024-21431** (Feb 2024) — also patched.
  Track these as the *shape* of an HVCI break; do not expect them to work on a
  current build.
- **Hypervisor-based cheating (the defensive research angle).** The **VIC** work
  (*"Virtualization-based cheating"*, `arXiv:2502.12322`) runs the game in a
  **QEMU + LibVMI** guest and reads memory via **KVMI** without touching the
  guest kernel or user space. EAC's hypervisor detection (`vmread` + VMEXIT
  timing, §2c) can be defeated with **proper TSC emulation**. Vanguard's **IOMMU
  enforcement (May 2026)** is the hardware-level counter.
- **DMA (PCILeech).** `ufrisk/pcileech` drives an **FPGA PCIe card** that reads
  host memory **without OS involvement**. EAC and Vanguard detect it via VID/PID
  checks, **Xilinx7 config-space signing**, and PCIe-slot scanning; defeating
  detection requires **custom gateware**. Vanguard's IOMMU enforcement blocks the
  DMA read itself, not just the device fingerprint.

---

## 8. Setting up a kernel debugging environment

Two-machine **WinDbg** setup — **mandatory**; never debug a kernel AC on a
machine you care about. Treat the target as disposable (clean snapshot, restore
after every crash).

1. **Target machine** (the disposable box running the AC):
   ```
   bcdedit /debug on
   bcdedit /dbgsettings net hostip:<host_ip> port:50000 key:<key>
   ```
   (Serial or USB transport are alternatives to net.)
2. **Host machine** (running the debugger): WinDbg →
   `File → Kernel Debug → Net`, set the IP and the same key.
3. **Break in:** `Ctrl+Break` on the host, or configure KD to wait at boot.
4. **Symbols:** Microsoft public symbol server +, where available, AC-specific
   PDB loading (`.sympath`, `.reload /f`).
5. **Analyze the callbacks/driver:**
   ```
   .process /r /p <eproc>          ; switch to the game process context
   !callbacks                       ; enumerate registered notify routines
   !drvobj \Driver\EasyAntiCheat 7  ; driver object, dispatch table, IOCTL handler
   ```
6. **For EAC specifically:** dump the **`.eac0`** section and treat it as **VMP2
   bytecode**; use **`backengineering/vmprofiler`** to extract VMP2 handlers and
   locate the handler index in the handler table (devirt skill §4).
7. **For BEDaisy:** the **`.be0`** section is *all* VM bytecode and the runtime
   API table lives in **`.data`** — set breakpoints on the driver entry points
   **after runtime init** has populated that table, or you will read unresolved
   imports.

---

## 9. Findings protocol

Write each confirmed finding to `findings/FIND-NNN.md` (one file per finding,
never overwrite — per `bounty-methodology` §7). A kernel-AC finding must record:

- **Affected component** — driver name + **version + build hash** (the VM layer
  is per-build; the hash is the only stable identifier).
- **The flaw** — which kernel callback was exploited, which integrity mechanism
  was bypassed, or which IOCTL/parsing bug was hit, stated precisely.
- **Reproduction** — the two-machine WinDbg setup, the exact breakpoint, and the
  trigger (input/IOCTL/handle operation) that exercises it. Minimal and
  deterministic.
- **Impact** — **LPE to Ring 0** vs **kernel info-leak** vs **detection
  bypass**. Be honest about which.
- **CVSS vector** — `AV:L` is **required** (local only). Example:
  ```
  CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H   # unchecked IOCTL → kernel arbitrary write → SYSTEM
  CVSS:3.1/AV:L/AC:H/PR:L/UI:N/S:U/C:H/I:N/A:N   # pool-address / KASLR info-leak
  ```
- **MITRE ATT&CK** — **T1068** (Exploitation for Privilege Escalation),
  **T1014** (Rootkit), **T1543.003** (Create or Modify System Process: Windows
  Service — the BYOVD `CreateService` load).

> Cross-reference: load **`bounty-methodology`** for scope/RoE discipline and
> de-duplication (check the program's prior reports — EAC/BattlEye/Vanguard have
> a deep public research history; many obvious findings are already known) before
> reporting. Load **`reverser/deobfuscation-devirtualization`** for the VMP2
> handler-lifting workflow EAC/BattlEye require.

---

## Tools

| Tool | Purpose | Reference |
|------|---------|-----------|
| **WinDbg** (`kd`) | Two-machine kernel debugging of the AC driver | Windows host; net/serial/USB transport |
| **`backengineering/vmprofiler`** | Extract & classify VMProtect 2 handlers (EAC `.eac0`) | `github.com/backengineering/vmprofiler` |
| **`backengineering/vmhook`** | Runtime hook of VMP2 `READQ/READDW/READB` handlers; evidence EAC is VMP2 | `github.com/backengineering/vmhook` |
| **`adrianyy/EACReversing`** | Annotated reconstructed EAC source (`systemthread.c`, `hwid.c`, `kernelpatch.c`, `physmem.c`, `driver.c`) | `github.com/adrianyy/EACReversing` |
| **`TempAccountNull/EasyAntiCheat_EOS`** | Fully RE'd EOS variant — least-obfuscated starting point | `github.com/TempAccountNull/EasyAntiCheat_EOS` |
| **`thesecretclub/CVEAC-2020`** | EAC pool-copy integrity bypass via `.pdata` | `github.com/thesecretclub/CVEAC-2020` |
| **`Aki2k/BEDaisy`** | Annotated BattlEye `BEDaisy.sys` static analysis | `github.com/Aki2k/BEDaisy` |
| **`niemand-sec/AntiCheat-Testing-Framework`** | AC technique testing harness | `github.com/niemand-sec/AntiCheat-Testing-Framework` |
| **`AlSch092/UltimateAntiCheat`** | Reference open-source AC — study expected protections to find their gaps | `github.com/AlSch092/UltimateAntiCheat` |
| **`ufrisk/pcileech`** | FPGA PCIe DMA host-memory R/W (DMA attack-surface research) | `github.com/ufrisk/pcileech` |
| **`tandasat/CVE-2024-21305`** | HVCI bypass PoC (patched) — shape of an HVCI break | `github.com/tandasat/CVE-2024-21305` |
