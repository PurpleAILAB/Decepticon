---
name: fuzzing
description: "Coverage-guided fuzzing methodology for compiled binaries and libraries: target scoping, fuzzer selection (AFL++/libFuzzer/Honggfuzz), harness skeleton, ASan+UBSan flags, corpus curation, crash triage and minimization (afl-tmin/minimize_corpus), exploitability rubric. Outputs corpora and crashes to /workspace/. Triggers on: 'fuzz', 'fuzzing', 'AFL', 'libFuzzer', 'harness', 'crash triage', 'coverage-guided', 'afl-tmin', 'sanitizer', 'corpus'."
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "fuzz fuzzing afl afl++ libfuzzer honggfuzz harness crash triage coverage guided afl-tmin sanitizer asan ubsan corpus"
  tags: fuzzing, afl++, libfuzzer, honggfuzz, asan, harness, crash-triage
  mitre_attack: T1587.004, T1203
---

# Coverage-Guided Fuzzing Playbook

Find memory-corruption and logic bugs by systematically mutating inputs
while tracking code coverage. Works on parsers, network protocol
handlers, file format readers, crypto implementations.

## 1. Target Scoping

Before writing a harness, answer:
- What is the attack surface? (file parser / network socket / library API)
- What input format does the target consume? (binary struct / text / TLV)
- Is source available? (instrumented build) or binary-only? (QEMU/Frida mode)

```bash
# Quick API surface for a library
nm -D /workspace/target.so | grep ' T ' | awk '{print $3}' | sort > /workspace/exports.txt
# or via radare2
r2 -q -e bin.demangle=true -c "aaa; afl~pub" /workspace/target.so 2>/dev/null | head -40
```

## 2. Fuzzer Selection

| Scenario | Fuzzer | Rationale |
|----------|--------|-----------|
| Source available, C/C++ | AFL++ | Best coverage feedback, mutator ecosystem |
| Source available, any lang | libFuzzer | In-process, lower overhead, LLVM native |
| Binary-only | AFL++ QEMU mode | `AFL_USE_QEMU=1` |
| Binary-only (faster) | AFL++ Frida mode | Lighter than QEMU on some targets |
| Multi-CPU farm | AFL++ + honggfuzz | honggfuzz for socket fuzzing |
| Go / Rust | native `go-fuzz` / `cargo fuzz` | Language-native instrumentation |
| Network protocol daemon | AFL++ persistent + preeny | Desock the accept() loop |

## 3. Instrumented Build (source-available)

```bash
# AFL++
CC=afl-clang-fast CXX=afl-clang-fast++ \
  cmake -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_C_FLAGS="-fsanitize=address,undefined -g -O1" \
        -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -g -O1" \
        -S /workspace/src -B /workspace/build-afl
cmake --build /workspace/build-afl -j$(nproc)

# libFuzzer (alternative)
CC=clang CXX=clang++ \
  cmake -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_C_FLAGS="-fsanitize=fuzzer,address,undefined -g" \
        -DCMAKE_CXX_FLAGS="-fsanitize=fuzzer,address,undefined -g" \
        -S /workspace/src -B /workspace/build-lf
cmake --build /workspace/build-lf -j$(nproc)
```

Minimum sanitizer flags: `-fsanitize=address,undefined`. Add
`-fsanitize=memory` (MSan) on a separate build for uninit reads.
Do NOT combine MSan with ASan — they conflict.

## 4. Harness Skeleton

### AFL++ persistent-mode harness (C)
```c
/* harness.c — compile with afl-clang-fast */
#include <stdint.h>
#include <string.h>

/* Include target headers */
#include "target_api.h"

/* AFL++ persistent mode — loops inside the same process (~20x faster) */
__AFL_FUZZ_INIT();

int main(void) {
    __AFL_INIT();
    const uint8_t *buf = __AFL_FUZZ_TESTCASE_BUF;
    while (__AFL_LOOP(10000)) {
        size_t len = __AFL_FUZZ_TESTCASE_LEN;
        /* Call the target function directly */
        target_parse(buf, len);   /* replace with actual API */
    }
    return 0;
}
```

### libFuzzer target (C)
```c
/* fuzz_target.cc */
#include <stdint.h>
#include <stddef.h>
#include "target_api.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    /* Wrap any setup in thread_local or static init if needed */
    target_parse(data, size);
    return 0;  /* non-zero aborts fuzzer */
}
```

Key harness rules:
- Allocate nothing that leaks between iterations (use arena or reset)
- Do not call `exit()` or `abort()` inside the harness — let ASan terminate
- Minimize initialization overhead outside the fuzz loop
- If target needs a null-terminated string: `strndup((char*)data, size)`

## 5. Seed Corpus Curation

```bash
# Create corpus dir
mkdir -p /workspace/corpus/initial

# If target is a file parser, seed with real samples
find /usr/share -name "*.png" 2>/dev/null | head -10 | \
  xargs -I{} cp {} /workspace/corpus/initial/

# For binary protocols, create minimal valid inputs by hand
# For text protocols, minimal valid requests:
printf 'GET / HTTP/1.0\r\n\r\n' > /workspace/corpus/initial/http_get.bin

# AFL++ minimize corpus to remove redundant seeds
afl-cmin -i /workspace/corpus/initial \
         -o /workspace/corpus/minimized \
         -- /workspace/build-afl/harness @@
```

Good seed = valid, minimal, diverse. 5–50 seeds beats 5000 random bytes.

## 6. Run AFL++

```bash
mkdir -p /workspace/findings/afl

# Single-core
AFL_SKIP_CPUFREQ=1 \
AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
afl-fuzz \
  -i /workspace/corpus/minimized \
  -o /workspace/findings/afl \
  -t 1000 \           # timeout per testcase (ms)
  -- /workspace/build-afl/harness @@

# Multi-core (1 main + N-1 secondary)
# Main:
afl-fuzz -M main-fuzzer -i /workspace/corpus/minimized \
  -o /workspace/findings/afl -- /workspace/build-afl/harness @@
# Secondary (run in parallel):
afl-fuzz -S sec-01 -i /workspace/corpus/minimized \
  -o /workspace/findings/afl -- /workspace/build-afl/harness @@
```

### Key AFL++ environment flags

| Flag | Effect |
|------|--------|
| `AFL_USE_ASAN=1` | Enable ASan in afl-fuzz without recompile |
| `AFL_DISABLE_TRIM=1` | Skip trim step (faster iteration) |
| `AFL_FAST_CAL=1` | Reduce calibration cycles |
| `AFL_CUSTOM_MUTATOR_LIBRARY` | Load grammar/structure-aware mutator |
| `AFL_LLVM_CMPLOG=1` + `-c cmplog_binary` | Token extraction from cmp instructions |

## 7. Run libFuzzer

```bash
mkdir -p /workspace/findings/lf /workspace/corpus/lf-work

# Merge initial corpus into working corpus first
/workspace/build-lf/fuzz_target \
  -merge=1 \
  /workspace/corpus/lf-work \
  /workspace/corpus/minimized

# Fuzz with ASAN_OPTIONS for cleaner reports
ASAN_OPTIONS=halt_on_error=1:print_stats=1 \
/workspace/build-lf/fuzz_target \
  -max_total_time=3600 \
  -artifact_prefix=/workspace/findings/lf/ \
  -jobs=$(nproc) \
  -workers=$(nproc) \
  /workspace/corpus/lf-work
```

## 8. Crash Triage

### Reproduce a crash
```bash
# AFL++ crash
ASAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
/workspace/build-afl/harness /workspace/findings/afl/default/crashes/id:000000*

# libFuzzer crash
ASAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
/workspace/build-lf/fuzz_target /workspace/findings/lf/crash-*
```

### Minimize crash (AFL++)
```bash
afl-tmin \
  -i /workspace/findings/afl/default/crashes/id:000000 \
  -o /workspace/findings/crash-min.bin \
  -- /workspace/build-afl/harness @@
```

### Parse crash output

| ASan report prefix | Bug class | Exploitability |
|-------------------|-----------|---------------|
| `heap-buffer-overflow` | OOB read/write on heap | Write → HIGH, Read → MEDIUM |
| `stack-buffer-overflow` | OOB on stack | Often HIGH (canary missing → RCE) |
| `heap-use-after-free` | UAF | HIGH — check if write capability |
| `global-buffer-overflow` | OOB on global | Context-dependent |
| `null-dereference` | NULL deref | LOW-MEDIUM (usually DoS) |
| `double-free` | Double free | HIGH in glibc < 2.35 |
| UBSan `signed-integer-overflow` | Integer overflow | Context-dependent |
| UBSan `shift-exponent` | Undefined shift | Usually LOW |

## 9. Exploitability Rubric

Assess each unique crash:

1. **Is it write or read?** Write-anywhere = HIGH. Read = may still be HIGH
   (information leak) or MEDIUM (crash only).
2. **Is address attacker-controlled?** Check if `addr` in the ASan report
   correlates with bytes from the fuzz input.
3. **Is there a canary?** `checksec --file=/workspace/build-afl/harness`.
   No canary on a stack overflow = trivially exploitable.
4. **Unique crash count:** Run `afl-whatsup -s /workspace/findings/afl/`.
   Deduplicate by first 3 frames of the stack trace.

```bash
# Deduplicate crashes by backtrace hash (quick)
for f in /workspace/findings/afl/default/crashes/id:*; do
  ASAN_OPTIONS=halt_on_error=1 \
  /workspace/build-afl/harness "$f" 2>&1 | \
  grep "^    #[0-2] " | md5sum | cut -d' ' -f1
done | sort | uniq -c | sort -rn | head -20
```

## 10. Promote to KG

For each confirmed unique crash:

```
kg_add_node("vulnerability",
  label="heap-buffer-overflow in target_parse()",
  props={
    "crash_input": "/workspace/findings/crash-min.bin",
    "class": "heap-buffer-overflow",
    "asan_report_summary": "WRITE of size 1 at 0x... heap base+0x28",
    "exploitability": "HIGH",
    "repro": "ASAN_OPTIONS=halt_on_error=1 ./harness crash-min.bin",
    "key": "fuzzing:heap-bof-target-parse"
  })
```

## Tools Quick Reference

| Tool | Install | Use |
|------|---------|-----|
| `afl-fuzz` | `apt install afl++` | Coverage-guided mutation fuzzer |
| `afl-clang-fast` | bundled with afl++ | Instrumented compilation |
| `afl-tmin` | bundled | Test case minimization |
| `afl-cmin` | bundled | Corpus minimization |
| `afl-whatsup` | bundled | Multi-instance status summary |
| libFuzzer | clang built-in | In-process fuzzer (LLVM) |
| honggfuzz | `apt install honggfuzz` | Good for network/socket targets |
| `cargo fuzz` | `cargo install cargo-fuzz` | Rust fuzzing (libFuzzer backend) |
