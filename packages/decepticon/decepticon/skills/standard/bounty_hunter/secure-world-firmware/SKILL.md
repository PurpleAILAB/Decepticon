---
name: secure-world-firmware
description: "Covers ARM secure-world vulnerability research — TF-A/TF-M/OP-TEE/Mbed TLS, SMC/PSA interface attacks, secure-boot chain, world-boundary validation, secure-partition/trusted-app isolation, and crypto-library fuzzing. Maps the ARM Trusted Firmware bug-bounty attack surface: NS-world callers attacking the secure world across the SMCCC/PSA boundary, secure-boot signature/parsing flaws (TBBR/FIP/X.509), and memory-safety bugs in source-available C reachable through legitimate supported-platform use under QEMU/FVP."
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "TF-A, TF-M, OP-TEE, trusted firmware, mbed tls, mbedtls, psa crypto, tf-psa-crypto, secure world, trustzone, SMC, secure monitor, EL3, S-EL1, secure boot, bl1, bl2, bl31, trusted application, secure partition, ARM aarch64 firmware, SPM, RME, realm"
  tags: arm, trustzone, tee, firmware, secure-boot, mbedtls, psa, optee, fuzzing
  mitre_attack: T1542.001, T1212
---

# ARM Secure-World / Trusted Firmware Vulnerability Research

Source-available C firmware that runs at the highest privilege on Arm SoCs.
The bounty surface is the **trust boundary**: code in a more-privileged or
isolated world parsing data supplied by a less-trusted world. Find a path
where **normal-world (NS) input crosses into the secure world and is mishandled**
— that is the canonical, in-scope, high-severity finding. Everything else is
graded against the project threat model.

In scope (all source-available C, all share this skill):
- **TF-A** — Trusted Firmware-A (Cortex-A / Armv8/9-A). EL3 monitor + secure boot.
- **TF-M** — Trusted Firmware-M (Cortex-M / Armv8-M, TrustZone-M). PSA RoT.
- **OP-TEE** — `optee_os` S-EL1 TEE core + S-EL0 trusted applications.
- **Mbed TLS / TF-PSA-Crypto** — X.509, ASN.1, TLS, PSA Crypto. Prime fuzz target.

---

## 1. Threat Model & World Model — what counts as a bug

### A-profile (TF-A / OP-TEE) privilege rings
```
 Non-secure world           Secure world
 ----------------           ------------
 EL0  NS apps               S-EL0  Trusted Applications (OP-TEE TAs) / SPs
 EL1  NS kernel (Linux)     S-EL1  Trusted OS  (OP-TEE core, SPMC)
 EL2  NS hypervisor         S-EL2  Secure hypervisor / SPMC (FF-A)
 EL3  Secure Monitor (TF-A BL31) — owns the world switch, NS bit, GICv3 grp0
 ---- Armv9 RME adds: Root world (EL3) + Realm world (R-EL0/1/2) ----
```
The `NS` bit (SCR_EL3.NS / GPT in RME) selects which world a memory access and a
CPU mode belong to. The monitor at EL3 is the only code that can flip it.

### M-profile (TF-M) split
TrustZone-M splits a single Cortex-M into **SPE** (Secure Processing Env) and
**NSPE** (Non-Secure). The SAU/IDAU mark address ranges secure / non-secure /
**NSC** (Non-Secure Callable — the only region NS code may `BLXNS`/`SG` into).
TF-M's SPM dispatches NSPE `psa_call`s to PSA Root-of-Trust services.

### Canonical attacker → what each project assumes
| Project | Attacker controls | In-scope (high) | Out-of-scope / capped |
|---------|-------------------|-----------------|-----------------------|
| TF-A | NS world (EL1/EL2 kernel), SMC args, NS memory, NS-supplied FIP/cert on update paths | NS→EL3 memory corruption, secure-boot bypass, world-isolation break, info-leak of secure state to NS | bugs needing prior EL3/secure-world code exec; physical/glitch unless the platform threat model includes it |
| TF-M | NSPE code, `psa_call` invecs/outvecs, NS pointers | NSPE→SPE corruption, RoT-service bypass, ITS/PS secret disclosure, attestation forgery | a malicious *secure partition* attacking another SP is lower tier |
| OP-TEE | NS Linux + the OP-TEE client, shared memory, `optee_msg_arg` | NS→TEE-core (S-EL1) corruption, TA isolation break, secure-storage/key disclosure | **a malicious TA** (you already have S-EL0 code) is explicitly **severity-capped** |
| Mbed TLS | attacker-supplied certs/TLS bytes/keys/inputs to the API | memory safety in parsers, key/plaintext disclosure, signature-verify bypass, practical timing oracle | misuse of the API by the integrator; "constant-time" claims outside documented guarantees |

**Why "outside the threat model" is rejected.** Each repo ships an explicit
threat model (see §6). If a finding requires capabilities the model already
grants the attacker (e.g. you start as a malicious TA, or you need a JTAG/glitch
the model excludes), the program treats it as **not a vulnerability** — there is
no boundary being crossed that the design promised to defend. Read the threat
model *first* and frame every finding as "untrusted X crosses boundary Y and
violates invariant Z that the model guarantees."

---

## 2. The Boundaries That Matter

### 2.1 SMC Calling Convention (SMCCC) — the A-profile front door
NS code issues `SMC #0`; the CPU traps to EL3. Arguments arrive in registers,
fully attacker-controlled:
- `x0` = **Function Identifier (FID)**, `x1..x7` = arguments (`w1..w7` for SMC32).
- Return in `x0..x3` (SMC32) / `x0..x7` (SMC64).

FID bitfield (`x0`):
```
 bit[31]      Fast Call (1) vs Yielding/std Call (0)
 bit[30]      SMC64/64-bit (1) vs SMC32/32-bit (0)
 bits[29:24]  Owning Entity Number (OEN) — selects the service range
 bits[23:16]  reserved (must be zero on fast calls — a classic validation gap)
 bits[15:0]   function number within the service
```
OEN ranges: `0x00` Arm Arch, `0x01` CPU, `0x02` **SiP** (silicon-provider,
custom — the buggiest range), `0x03` OEM, `0x04` Standard Secure (PSCI lives
here, e.g. `PSCI_VERSION=0x84000000`, `CPU_ON_aarch64=0xC4000003`), `0x05`
Standard Hyp, `0x06` Vendor-Hyp.

In TF-A a service is registered with:
```c
DECLARE_RT_SVC(my_svc, OEN_SIP_START, OEN_SIP_END, SMC_TYPE_FAST, init, handler);

uintptr_t my_smc_handler(uint32_t smc_fid,
                         u_register_t x1, u_register_t x2,
                         u_register_t x3, u_register_t x4,
                         void *cookie, void *handle, u_register_t flags) {
    /* flags bit tells you the caller's world: */
    if (is_caller_secure(flags)) { ... }   /* SMC_FROM_SECURE */
    /* x1..x4 are attacker-controlled when is_caller_non_secure(flags) */
    switch (smc_fid) { ... }
    SMC_RET1(handle, rc);
}
```
**Where validation must happen:** every `switch` arm that consumes `x1..x7` from
a non-secure caller. Hunt for handlers that (a) skip `is_caller_non_secure()`
gating, (b) treat an NS-supplied value as a pointer, (c) use an NS-supplied
length/offset without bounds checks, (d) have FID arms that fall through or share
state machines (FID confusion).

### 2.2 The NS-buffer / shared-memory problem (the #1 bug factory)
Secure code must **never trust a normal-world pointer**. Failure modes:
- **NS-pointer dereference.** Secure code reads/writes through an address handed
  in by NS without checking it points into *non-secure* memory the caller may
  access (and not into secure RAM / MMIO). TF-A guards entrypoints with
  `arm_validate_ns_entrypoint()` (must be in NS DRAM); missing/incorrect
  equivalents on other services are findings.
- **Double-fetch / TOCTOU.** Shared memory is mutable by NS *concurrently*. If
  secure code reads a length/type field, validates it, then re-reads it (or
  reads the payload after the check), NS can flip the value between fetches.
  Correct pattern: **copy once into secure memory, then validate the copy.**
- **Missing bounds on NS lengths/offsets.** `len`, `offset`, `size`, element
  counts from NS feeding `memcpy`/loop bounds/`alloca` → overflow or OOB.
- **Integer overflow on NS sizes.** `a + b`, `n * elemsize`, `len - hdr` where
  the operands are NS-controlled and wrap, defeating a later bounds check.

### 2.3 PSA Firmware Framework IPC (TF-M & OP-TEE PSA path)
NSPE/clients talk to RoT services via the PSA API — same boundary discipline:
```c
psa_handle_t h = psa_connect(SOME_SID, version);
psa_invec  in[]  = { {buf_in,  in_len}  };   /* NS-supplied ptr+len */
psa_outvec out[] = { {buf_out, out_len} };
psa_status_t s = psa_call(h, type, in, IOVEC_LEN(in), out, IOVEC_LEN(out));
```
Inside the service, NS data is reached with `psa_read(msg, idx, dst, num)`,
`psa_skip`, and results written with `psa_write(msg, idx, src, num)`; sizes live
in `msg.in_size[i]` / `msg.out_size[i]`. **Findings:** a service that trusts
`in_size`/`out_size` blindly, `psa_read`s more than it allocated, writes past
`out_size`, or dereferences a vector base directly instead of via `psa_read`.
TF-M validates NS pointers in `tfm_hal_memory_check()` / `tfm_memory_check()` —
audit every RoT service for a path that bypasses it.

OP-TEE marshals NS calls through `struct optee_msg_arg` (in shared memory) into
`TEE_Param params[4]`, each typed by `TEE_PARAM_TYPES(t0,t1,t2,t3)` with members
`TEE_PARAM_TYPE_{NONE,VALUE_*,MEMREF_*}`. The core validates memref ranges with
`vm_check_access_rights()` / `core_pbuf_is()`. **Findings:** type-confusion
between VALUE and MEMREF, a memref whose `buffer`/`size` escapes the access
check, or core code reading the `optee_msg_arg` fields twice (double-fetch on
shared memory).

---

## 3. Per-Project Attack Surface + Build/Run for PoC

> A valid PoC runs through **legitimate, supported platform code** (QEMU/FVP is
> fine) — see §7. Build the in-scope branch, then drive the boundary from the
> normal world.

### 3.1 TF-A (Trusted Firmware-A)
Repo: `https://github.com/ARM-software/arm-trusted-firmware`
(mirror `https://git.trustedfirmware.org/TF-A/trusted-firmware-a.git`).

Boot/runtime chain & where to look:
```
BL1  AP Trusted ROM     bl1/        — first parser of BL2 image+cert
BL2  Trusted Boot FW    bl2/        — FIP unpack, full TBBR cert-chain auth, loads BL3x
BL31 EL3 Runtime (SMC)  bl31/ + services/   — secure monitor, runtime SMC dispatch
BL32 Secure Payload     (OP-TEE etc., S-EL1)
BL33 NS firmware        (U-Boot/UEFI, EL2/EL1)
```
Hot directories:
- `services/std_svc/` (PSCI, SDEI, SPM/SPMD/FF-A, RMMD for RME).
- `services/spd/` (Secure Payload Dispatchers — opteed, tspd) and
  `services/std_svc/spm*` (Secure Partition Manager).
- `plat/<vendor>/` SiP SMC handlers (OEN_SIP) — vendor C, weakest validation.
- `drivers/auth/` + `drivers/io/` — image auth, FIP parsing, the secure-boot
  parsers (`auth_mod`, `img_parser`, mbedtls glue) reachable on update paths.

Build + boot under QEMU (no hardware):
```bash
# cross toolchain: aarch64-none-elf- or aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-gnu-
# BL33 = any NS payload; a tiny U-Boot or UEFI build, or a stub for SMC fuzzing
make PLAT=qemu DEBUG=1 BL33="$PWD/bl33.bin" all fip
# qemu 'qemu' plat boots a flash image = bl1 ++ fip
dd if=build/qemu/debug/bl1.bin of=flash.bin bs=4096 conv=notrunc
dd if=build/qemu/debug/fip.bin of=flash.bin seek=64 bs=4096 conv=notrunc
qemu-system-aarch64 -nographic -machine virt,secure=on -cpu max \
  -smp 2 -m 1024 -bios flash.bin -d unimp -semihosting-config enable=on,target=native
# enable secure boot for TBBR/auth bugs:
make PLAT=qemu DEBUG=1 TRUSTED_BOARD_BOOT=1 GENERATE_COT=1 MBEDTLS_DIR=<path> ... fip
```
Drive SMCs from BL33/NS: from a Linux NS kernel use an `smccc`-issuing module or
PSCI calls; for fast iteration, a minimal bare-metal BL33 that executes
`SMC #0` with chosen `x0..x7` lets you sweep the FID/argument space directly.

### 3.2 TF-M (Trusted Firmware-M)
Repo: `https://git.trustedfirmware.org/TF-M/trusted-firmware-m.git`
(GitHub `TrustedFirmware-M/trusted-firmware-m`).

Surface: PSA RoT services — **Crypto**, **Internal Trusted Storage (ITS)**,
**Protected Storage (PS)**, **Initial Attestation**, **Firmware Update** — plus
the **SPM** dispatch and each **secure partition** manifest. Code:
`secure_fw/partitions/*`, `secure_fw/spm/`, the NSC veneer layer.

Build for AN521 (FVP/QEMU model, no hardware):
```bash
# arm-none-eabi-gcc toolchain
cmake -S . -B build \
  -DTFM_PLATFORM=arm/mps2/an521 \
  -DTFM_TOOLCHAIN_FILE=toolchain_GNUARM.cmake \
  -DTFM_PROFILE=profile_medium \
  -DCMAKE_BUILD_TYPE=Debug -DTFM_ISOLATION_LEVEL=2
cmake --build build -- install
# run the combined image on the AN521 Fixed Virtual Platform:
FVP_MPS2_AEMv8M --application cpu0=build/bin/bl2.axf \
  --data cpu0=build/bin/tfm_s_ns_signed.bin@0x10080000
# or QEMU model:
qemu-system-arm -M mps2-an521 -kernel build/bin/tfm_s.elf -nographic -semihosting
```
PoC = an NSPE app calling `psa_connect`/`psa_call` with crafted invec/outvec
sizes against the targeted RoT service.

### 3.3 OP-TEE
Repos: `https://github.com/OP-TEE/optee_os` (the TEE core) and
`https://github.com/OP-TEE/build` (QEMU build harness).

Surface: TEE-core syscalls (`core/`), the entry/dispatch path
(`core/arch/arm/tee/entry_std.c`, `optee_msg`/`optee_smc` glue), TA parameter
marshalling (`TEE_Param`, `utee_params`, `optee_msg_param`), memory/shared-mem
checks (`core/mm/vm.c`, `core/arch/arm/mm/core_mmu*.c`), crypto (`core/crypto/`),
and the per-arch context switch (`core/arch/arm/`).

Build + run all-in-one under QEMUv8:
```bash
mkdir optee && cd optee && repo init -u https://github.com/OP-TEE/manifest.git \
  -m qemu_v8.xml && repo sync -j$(nproc)        # or git clone OP-TEE/build
cd build && make -j$(nproc) toolchains
make -j$(nproc) run                # builds TF-A+OP-TEE+Linux, launches qemu, two consoles
# in the NS Linux console: tee-supplicant runs; load xtest / your client TA
xtest                              # regression suite — also a corpus of valid calls
```
PoC = an NS client (libteec / `tee_client_api.h`) opening a session and invoking
a command with crafted `TEE_Param` types/memrefs to hit the TEE core. (A bug
only reachable *by a malicious TA you author* is severity-capped — frame it as
NS→core if at all possible.)

### 3.4 Mbed TLS / TF-PSA-Crypto
Repos: `https://github.com/Mbed-TLS/mbedtls`,
`https://github.com/Mbed-TLS/TF-PSA-Crypto` (crypto core, consumed as the
framework submodule by recent Mbed TLS).

Prime surfaces (attacker bytes → parser):
- **X.509 / ASN.1**: `library/x509_crt.c`, `x509_csr.c`, `x509_crl.c`,
  `x509.c`, `asn1parse.c` — `mbedtls_x509_crt_parse()` & friends.
- **TLS/DTLS record + handshake**: `library/ssl_tls.c`, `ssl_msg.c` (record),
  `ssl_tls12_server.c` / `ssl_tls13_*.c` (handshake state machines).
- **PSA Crypto API**: `psa_crypto*.c` — `psa_import_key`, `psa_aead_*`,
  `psa_cipher_*`, `psa_sign_hash`/`psa_verify_hash`, `psa_mac_*`.
- **Key parsing**: `pkparse.c` (`mbedtls_pk_parse_key`/`_public_key`).

Build for analysis with sanitizers (host build, no hardware):
```bash
git clone --recurse-submodules https://github.com/Mbed-TLS/mbedtls && cd mbedtls
# toggle features via the config tool (e.g. force PSA path):
python3 scripts/config.py set MBEDTLS_USE_PSA_CRYPTO
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_C_FLAGS="-fsanitize=address,undefined -fno-sanitize-recover=all -g -O1"
cmake --build build -j$(nproc)
ctest --test-dir build           # sanity-run the suite
```

---

## 4. Vulnerability Classes to Hunt (what each looks like in C + impact tier)

| Class | C smell | Where | Impact |
|-------|---------|-------|--------|
| **NS-pointer deref** | secure handler does `*(uintptr_t*)x1` / `memcpy(dst, (void*)x2, n)` with no `validate_ns`/`vm_check_access_rights`/`tfm_hal_memory_check` | TF-A SiP/SPD handlers, OP-TEE memrefs, TF-M RoT | NS→secure R/W → **Critical** |
| **Integer overflow on NS size** | `if (off+len <= total)` with `off,len` NS u32/u64 that wrap; `n*sz` for `memcpy`/alloc | any size/offset math on NS input | bounds-check bypass → OOB → **High/Crit** |
| **Double-fetch / TOCTOU** | reads `arg->len`/`msg->in_size` twice from shared mem, or validates then re-reads | OP-TEE `optee_msg_arg`, TF-M invec, FF-A | check bypass → corruption → **High** |
| **SMC FID confusion / state-machine** | missing `is_caller_non_secure()` gate; FID arm that reuses another's buffer/handle; yielding-call resumed in wrong state | TF-A dispatch, SPD/PSCI | priv action from NS / world desync → **High** |
| **Secure-boot parse/verify flaw** | FIP/TOC offset trusted before bound; X.509 cert-chain auth that mis-handles a malformed field; algo/keyhash confusion in COT | TF-A `drivers/auth`, `io`, mbedtls glue | **secure-boot bypass = Critical** |
| **Crypto: ASN.1 OOB** | length/tag parsed without checking remaining buffer; nested-length confusion | mbedtls `asn1parse.c`, `x509_*` | OOB read/DoS, sometimes RCE → **High** |
| **Crypto: padding/timing oracle** | non-constant-time compare/branch on secret (RSA PKCS#1 v1.5, CBC-MAC, Bleichenbacher/Lucky13 shape) | mbedtls RSA/CBC/`ssl_msg.c` | key/plaintext recovery → **High** |
| **Uninitialized secure memory leaked to NS** | `outvec`/`out` buffer or SMC return regs written partially; struct with padding copied to NS | TF-M outvec, OP-TEE memref-out, SMC `x0..x7` | secure-RAM/key disclosure → **High** |
| **Missing cache/TLB/reg hygiene across worlds** | secure code leaves data in shared cache lines / scratch regs / GPRs on world switch; no `dcache` clean of secret before handing buffer back | EL3 context save/restore, OP-TEE return path | residual secret to NS → **Medium/High** |

For every candidate, write the boundary sentence: *"NS supplies ___ via ___;
secure code at `file:func` uses it as ___ without ___; result is ___."*

---

## 5. Fuzzing the Crypto / Parsing Surface

Mbed TLS ships ready harnesses in **`tests/fuzz/`**: `fuzz_x509crt`,
`fuzz_x509csr`, `fuzz_x509crl`, `fuzz_privkey`, `fuzz_pubkey`,
`fuzz_client`, `fuzz_server`, `fuzz_dtlsclient`, `fuzz_dtlsserver`. Each is a
libFuzzer `LLVMFuzzerTestOneInput` wrapper (OSS-Fuzz integrated).

Build & run the shipped fuzzers with libFuzzer + ASan/UBSan:
```bash
cd mbedtls
# build the library + fuzzers under clang/libFuzzer; CMake links tests/fuzz
# when a fuzzing engine is present:
export CC=clang CXX=clang++
export CFLAGS="-fsanitize=fuzzer-no-link,address,undefined -fno-sanitize-recover=all -g -O1"
cmake -S . -B build-fuzz -DCMAKE_BUILD_TYPE=Debug -DENABLE_TESTING=On
cmake --build build-fuzz -j$(nproc)
# run a target (libFuzzer):
mkdir -p corpus/x509crt && \
  ./build-fuzz/tests/fuzz/fuzz_x509crt -max_total_time=3600 \
    -artifact_prefix=findings/x509crt- corpus/x509crt
# AFL++ alternative: rebuild with afl-clang-fast, then afl-fuzz -- ./fuzz_x509crt @@
```
Seed wisely — fuzzers are only as good as the corpus:
```bash
# DER/PEM certs make great x509 seeds:
find / -name '*.crt' -o -name '*.pem' 2>/dev/null | head -40 \
  | xargs -I{} sh -c 'openssl x509 -in "{}" -outform DER -out corpus/x509crt/$(basename {}).der 2>/dev/null'
```

Write a **PSA-crypto** harness for an API the shipped set misses:
```c
/* fuzz_psa_import.c — libFuzzer, compile against libmbedcrypto with ASan+UBSan */
#include <stdint.h>
#include <stddef.h>
#include "psa/crypto.h"
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (psa_crypto_init() != PSA_SUCCESS) return 0;
    psa_key_attributes_t a = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_type(&a, PSA_KEY_TYPE_RSA_PUBLIC_KEY);   /* vary the type */
    psa_set_key_usage_flags(&a, PSA_KEY_USAGE_VERIFY_HASH);
    psa_set_key_algorithm(&a, PSA_ALG_RSA_PKCS1V15_SIGN_RAW);
    psa_key_id_t k = 0;
    if (psa_import_key(&a, data, size, &k) == PSA_SUCCESS)
        psa_destroy_key(k);                              /* avoid slot leak */
    return 0;
}
```
Compile: `clang -fsanitize=fuzzer,address,undefined -Iinclude fuzz_psa_import.c
build-fuzz/library/libmbedcrypto.a -o fuzz_psa_import`.

For TF-A/OP-TEE/TF-M, the bulk is C reachable only through the firmware harness,
but pure parsers can be **lifted into a host harness**: extract the translation
unit + its deps, stub the platform layer, and fuzz `optee_msg`/`tlv` parsing or
TF-A's FIP/`io_fip`/`auth` parsers on the host with the same libFuzzer/AFL++
recipe and ASan/UBSan.

Use the agent's built-in fuzzing tools to scaffold and triage instead of hand-rolling:
- `fuzz_generate_harness(target_library, target_function, input_type)` →
  emits a compile-ready AFL++/libFuzzer C harness + `compile_cmd`/`run_cmd`/sanitizer flags.
- `fuzz_triage_crash(crash_output, binary_path)` → parses an ASan/signal dump,
  returns `crash_type`, `severity`, faulting address, stack frames, exploitability notes.
- `fuzz_status()` → reports which fuzzers/sanitizers are on PATH.
For compiled secure-world blobs (vendor BL31/TA images with no source),
disassemble in **ghidra**/**r2** to recover the parser before harnessing.

---

## 6. Static-Review Workflow

```bash
# 1. clone the in-scope project + checkout the SUPPORTED/LTS branch (dups matter)
git clone https://github.com/ARM-software/arm-trusted-firmware tf-a && cd tf-a
git branch -a | grep -iE 'lts|v2\.|v3\.'      # pick the maintained release line
git checkout <lts-or-latest-release-tag>

# 2. read the threat model + advisories FIRST (avoid out-of-scope / dups)
ls docs/threat_model/ docs/security_advisories/      # TF-A
#   TF-M: docs/security/  +  docs/security/security_advisories/
#   OP-TEE: documentation + GitHub Security Advisories
#   Mbed TLS: SECURITY.md + published security advisories

# 3. enumerate the boundary entry points
# TF-A SMC service registrations:
grep -rn "DECLARE_RT_SVC" services/ plat/
# TF-A NS-pointer guards (find the ones that are MISSING on a handler):
grep -rn "validate_ns_entrypoint\|is_caller_non_secure\|SMC_FROM_NON_SECURE" .
# OP-TEE access checks (audit every memref path that skips them):
grep -rn "vm_check_access_rights\|core_pbuf_is\|tee_mmu_check" core/
# TF-M NS memory checks:
grep -rn "tfm_hal_memory_check\|tfm_memory_check\|psa_read\|psa_write" secure_fw/
```

Then trace NS-input → dangerous sink with semgrep:
```bash
# memcpy/memmove with an NS-derived length and no preceding bounds check
semgrep -l c -e 'memcpy($DST, $SRC, $LEN)' services/ plat/ core/ secure_fw/
# dereference of an SMC arg used as a pointer
semgrep -l c -e 'memcpy($D, (void *)$X1, $N)' .
# double-fetch: same shared-mem field read twice
grep -rn "in_size\[" secure_fw/ | sort        # then read each call site
```
Workflow per hit: confirm the source is NS-controlled, confirm no validation
dominates the sink on *all* paths, confirm reachability from a legitimate
SMC/`psa_call`/TA invocation, then build the PoC (§3).

---

## 7. PoC Requirements (program-specific — read before claiming a finding)

The Trusted Firmware programs reject PoCs that don't model a real attacker:
1. **Legitimate use only.** Trigger the bug through the software's *supported
   interface* on *existing supported platform code* (QEMU/FVP allowed). Do **not**
   call internal/static functions out of context, do **not** copy-paste the
   vulnerable snippet into a standalone driver, do **not** patch in a fake
   caller. The path must be one a real NS/NSPE attacker can take.
2. **Crash ≠ vulnerability.** A sanitizer abort or hang is the *start*. You must
   show **meaningful security impact**: secure-world memory corruption *from the
   normal world*, a secure-boot/auth bypass, world/TA isolation break, or
   disclosure of a key/secret/secure-RAM content to a less-trusted world.
3. **Respect the threat model & caps.** State which boundary is crossed and which
   documented invariant breaks. Remember: **OP-TEE / TF bugs only reachable by a
   malicious TA or secure partition are severity-capped** (you already hold
   secure-world code execution) — frame NS→secure if any path exists; otherwise
   declare the cap honestly.
4. **Reproducible.** Exact branch/commit, exact build flags, exact run command,
   exact trigger input (SMC FID+regs / `psa_call` vectors / TA cmd+params / the
   malformed cert/TLS bytes), and the observed impact (ASan trace, leaked bytes,
   bypassed check).

---

## 8. Findings Protocol

Write each confirmed finding to `findings/FIND-NNN.md`:
```markdown
# FIND-001: <one-line: NS→S-EL1 OOB write in optee core memref handling>
- Project / component: OP-TEE optee_os — core/arch/arm/tee/entry_std.c
- Affected function: <func>  (lines L..L)
- Branch / commit: <branch> @ <full-sha>
- Boundary crossed: Non-secure (Linux client) -> TEE core (S-EL1)
- Threat-model justification: in-scope NS->core; invariant "<X>" from
  <docs/...threat_model> is violated. (Not the capped malicious-TA case because <reason>.)
- Root cause: <NS-controlled value> used as <sink> without <missing check>;
  <double-fetch / int-overflow / missing vm_check_access_rights> at <file:func>.
- Reproduction:
    BUILD:  <exact cmake/make + flags>
    RUN:    <exact qemu/FVP command>
    TRIGGER:<exact SMC FID+x1..x7 / psa_call vectors / TA cmd+params / cert bytes>
    OBSERVE:<ASan report / leaked bytes / bypassed signature check>
- Impact: <secure memory corruption | secure-boot bypass | key/secret disclosure>
- Severity / CVSS: <vector + score, mapped to the program's tiering>
- Suggested fix: <copy-then-validate | add vm_check_access_rights | checked
  add/mul | constant-time compare | bound TOC offset before use>
- Dedup check: not matched by <advisory IDs reviewed>.
```
Keep one file per finding; never overwrite. Re-verify the repro from a clean
build before submission.

---

## 9. Tools

| Tool | Purpose |
|------|---------|
| `qemu-system-aarch64` | Run TF-A/OP-TEE (A-profile) secure-boot + SMC PoCs without hardware |
| `qemu-system-arm` (mps2-an521) | Run TF-M / Armv8-M PoCs |
| Arm **FVP** (`FVP_MPS2_AEMv8M`, `FVP_Base_*`) | Cycle-accurate models — AN521 for TF-M, Base for TF-A/RME |
| `aarch64-linux-gnu-gcc` / `aarch64-none-elf-gcc` | A-profile cross toolchain (TF-A, OP-TEE) |
| `arm-none-eabi-gcc` | M-profile cross toolchain (TF-M) |
| `cmake` / `make` / `repo` | TF-M & Mbed TLS (cmake); TF-A & OP-TEE (make/repo) builds |
| `clang` + libFuzzer, `afl-fuzz`/`afl-clang-fast` (AFL++) | Fuzz Mbed TLS `tests/fuzz/` + host-lifted parsers |
| ASan / UBSan / MSan (`-fsanitize=...`) | Catch OOB, UAF, int-overflow, uninit reads in C |
| `semgrep` | Pattern-match NS-input→sink; missing validation |
| `grep` / `git log` / `git blame` | Map SMC/PSA handlers, supported branch, dup-check advisories |
| `gdb-multiarch` | Step BL31/TEE-core/TF-M in QEMU (`-S -s`, `target remote :1234`) |
| `ghidra` / `r2` (radare2) | Reverse compiled/vendor secure-world blobs with no source |
| `openssl` / `python3` (cryptography, asn1) | Craft malformed X.509 certs, FIP/COT inputs, TLS records |
| `fuzz_generate_harness` / `fuzz_triage_crash` / `fuzz_status` | Agent fuzzing scaffolding + crash triage (`decepticon.tools.fuzzing`) |
