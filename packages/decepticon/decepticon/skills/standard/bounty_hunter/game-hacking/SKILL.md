---
name: game-hacking
description: "Videogame security research — anti-cheat bypass analysis, client memory/integrity attacks, netcode/protocol abuse, and server-authority & economy exploits. Reverse the game client (Unity IL2CPP/Mono, Unreal), find where the server trusts the client, and demonstrate a server-trust or integrity break (not a local-only trainer). For authorized bug-bounty / VDP targets only."
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "videogame, game hacking, anti-cheat, anticheat, memory hacking, cheat, trainer, aimbot, wallhack, ESP, speedhack, netcode, game protocol, packet replay, server authority, server-side validation, game economy, item dupe, currency exploit, save manipulation, save tampering, Unity, IL2CPP, Mono, Unreal, GNames, Frida"
  tags: game, anti-cheat, memory, netcode, reverse-engineering, protocol
  mitre_attack:
---

# Videogame Security Research (Game Hacking)

Game hacking, as security research, is about one question: **what does the game
trust the client to tell the truth about, and what breaks when it lies?** The
high-value findings are not local trainers — they are **server-authority and
integrity failures**: the server accepting client-asserted state it should
recompute, missing server-side validation, replayable/forgeable protocol
messages, and economy/logic flaws that mint value or duplicate items. Client RE
and anti-cheat analysis are the *means* to find and prove those server-side bugs.

## 0. Scope & Legality (read first)

Only operate against a target that is **explicitly in scope** of an authorized
bug-bounty program, VDP, or your own/lab environment. Game publishers are
aggressive about cheat tooling and EULA/anti-circumvention; "I was researching"
is not a defence outside an authorized program.
- Confirm the program's scope covers the game **client and/or its servers**, and
  that RE / network testing is permitted.
- **Never** distribute working cheats, target *other players'* clients/accounts,
  or test on production matches with real users. Use private servers, test
  realms, or solo/sanctioned environments.
- Frame every finding as a server-side or integrity defect to be *fixed*, with a
  reproducible PoC — not as a usable cheat.

---

## 1. Client Reverse Engineering

The client is the map to the protocol and to what the server validates. Identify
the engine first — it dictates the toolchain.

### Identify the engine & runtime
```bash
# Unity: look for the data layout
ls -R | grep -iE 'UnityPlayer|globalgamemanagers|level[0-9]|\.assets$|il2cpp|Mono'
#  Mono backend  -> managed DLLs in <game>_Data/Managed/  (Assembly-CSharp.dll etc.)
#  IL2CPP backend-> GameAssembly.dll / libil2cpp.so  + <game>_Data/il2cpp_data/Metadata/global-metadata.dat
# Unreal: pak files + the engine names
ls -R | grep -iE '\.pak$|\.uasset$|\.umap$|UE4|UE5|Shippping|-Shipping'
strings ./Game.exe | grep -iE 'UnrealEngine|UE4|UE5|UObject|GNames'
```

### Unity — Mono backend (managed)
Managed assemblies are CIL; decompile to near-source:
```bash
# decompile the game logic to C#:
ilspycmd <game>_Data/Managed/Assembly-CSharp.dll -o ./decomp   # ILSpy CLI
# (or open in dnSpy/dnSpyEx for an interactive decompiler+debugger you can edit & patch)
```
Read networking, validation, and economy classes directly: search for RPC
attributes, `[Command]`/`[ClientRpc]` (Mirror/UNet), serialization, and any
client-side check that gates a server action.

### Unity — IL2CPP backend (AOT-compiled to native)
C# is compiled to C++ then to a native blob; metadata is in
`global-metadata.dat`. Recover symbols, then treat it as native RE:
```bash
# rebuild type/method names from the metadata + the binary:
python3 Il2CppDumper.py GameAssembly.dll global-metadata.dat   # emits dump.cs + script.json + il2cpp.h
# then load the symbol script into ghidra/r2 so functions are named, not sub_XXXX
```

### Unreal Engine (native C++)
Unreal uses the `UObject` reflection system; the hooks for an SDK are the global
name and object tables (**`GNames`/`FNamePool`** and **`GUObjectArray`**) plus
`UFunction` dispatch (`ProcessEvent`). Public SDK dumpers walk these to emit a
C++ SDK of the game's classes/structs/offsets; from there:
```bash
# static recovery of the engine globals + ProcessEvent for RPC dispatch:
r2 -A ./Game-Shipping.exe
# > / GNames        ; locate name pool / object array refs, map UFunction -> handler
# ghidra: import, find ProcessEvent, recover UObject/struct field offsets feeding net replication
```

### Dynamic analysis (runtime structure & function discovery)
Use a dynamic instrumentation framework to confirm offsets, hook functions, and
read live structures — far faster than pure static work for finding *what the
server is told*:
```bash
# Frida: enumerate modules/exports, hook a candidate function, dump args
frida -p "$(pgrep -f Game)" -l hook.js     # Interceptor.attach to RPC/serialize/validation fns
```
Use a memory scanner (Cheat Engine, scanmem/GameConqueror on Linux) to locate
player/entity/inventory structures and confirm field offsets, then correlate
with the static SDK. The goal of all of this is to learn the **wire protocol**
and the **client-side checks** — so you can ask the server the wrong question.

---

## 2. Anti-Cheat Surface — as *bypasses to report*

Anti-cheat (AC) is itself attack surface; in a bounty context the finding is
"the integrity guarantee can be bypassed / the AC can be evaded," reported so it
can be hardened. Map which model the target uses:
- **Kernel-mode AC** — EasyAntiCheat (EAC), BattlEye, Riot **Vanguard**, Activision
  **Ricochet**: a signed driver loads early (sometimes at boot) and does memory
  scanning, handle-stripping, integrity attestation, and hypervisor-assisted
  protection. Bypass research = signed-driver/HVCI weaknesses, attestation
  spoofing, or scanning blind spots — high bar, high value.
- **User-mode AC** — in-process integrity checks, anti-debug, packed/obfuscated
  modules, periodic memory CRC. Easier to analyze and bypass; report the evaded
  check.
- **Detection vectors to enumerate** (each a candidate blind spot): module/region
  scanning, hooked-import / inline-hook detection, code-section CRC/integrity,
  debugger detection, known-tool signatures, and server-side heuristics
  (statistical anomaly detection on telemetry).

Treat AC analysis as: *which integrity invariant does the AC claim to enforce,
and what path violates it without detection?* That violated invariant is the
finding — and it usually exists **because the server trusts client integrity it
can't actually verify** (which loops back to §3).

---

## 3. Netcode / Protocol Abuse — the high-value bugs

This is where the durable, server-side findings live: the server **trusting
client-asserted state** it should authoritatively own or recompute.
```bash
# capture and study the wire protocol (authorized/test env only):
wireshark -k -i <iface>                 # or tshark -i <iface> -w game.pcap
tshark -r game.pcap -Y "udp.port==<gameport>" -T fields -e data    # extract payloads
```
What to look for, framed as server-authority defects:
- **Missing server-side validation.** The client sends an action (move, shoot,
  buy, pickup, damage) and the server applies it without re-checking
  legality/bounds/cooldown/line-of-sight/range. *Client-authoritative position,
  hit registration, or damage* is the archetype — the server should compute, not
  accept.
- **Trusting client state.** Health, cooldowns, currency, inventory, level, or
  permissions sent by (or derivable from) the client and accepted as truth.
- **Packet replay.** A captured action packet re-sent succeeds because there is
  no nonce/sequence/timestamp/HMAC binding it to one use (replay an item-grant,
  a purchase, a reward).
- **Packet forgery / unbounded fields.** Hand-crafted messages with
  out-of-range IDs/quantities/coordinates the server accepts (no allow-list,
  no range/ownership check).
- **Encryption/auth gaps.** Plaintext or trivially keyed protocol (key shipped
  in the client, recovered via §1) lets you read/forge at will.

The reportable finding is the **server defect** (e.g. "server applies
client-reported hit damage without server-side hit validation; a forged packet
inflicts arbitrary damage on any player"), demonstrated against a test server.

---

## 4. Game-Economy / Logic Exploits

These are business-logic bugs in game clothing — high value because they affect
revenue and fairness:
- **Item / currency duplication** — race conditions or non-atomic
  trade/mail/storage flows (TOCTOU on an inventory transaction), or a flow that
  credits before it debits.
- **Save / state tampering** — for games that trust a client-side save or a
  client-supplied progress blob (offline or hybrid), modifying it to grant
  items/currency/unlocks the server then ingests as authoritative.
- **Purchase / reward validation** — accepting a client-asserted purchase
  receipt, reward claim, or quest completion without server-side verification
  (replay or forge the "I earned this" message).
- **Pricing / quantity manipulation** — negative or overflowing quantities,
  client-set prices, or discount stacking the server doesn't bound.

Analyze these exactly like web business-logic flaws: enumerate the state machine
of the transaction, find the step the server delegates to the client, and prove
the invariant break.

---

## 5. PoC Bar

Demonstrate a **server-trust or integrity break**, not a local convenience:
1. **Not a local trainer.** Freezing your own ammo in single-player / a memory
   edit only you see is **not** a finding. The bug must affect the *server's*
   model of the game or break an integrity guarantee the program relies on.
2. **Show the trust violation.** E.g. a forged/replayed packet the **server
   accepts**; an economy action that mints/dupes value persisted **server-side**;
   an AC integrity check provably **bypassed without detection**.
3. **Authorized environment.** Test server / private realm / solo / sanctioned
   account — never against real players in production.
4. **Reproducible.** Exact game build/version, the client offsets/symbols used,
   the exact packet bytes or transaction sequence, and the observed server-side
   effect (state change, granted item, undetected bypass).

---

## 6. Findings Protocol

Write each confirmed finding to `findings/FIND-NNN.md`; one file per finding,
never overwrite:
```markdown
# FIND-001: <one-line: server applies client-reported damage without validation>
- Game / component: <title + build/version> — <subsystem: netcode/economy/anti-cheat>
- Engine / backend: <Unity IL2CPP | Unity Mono | Unreal UE5 | custom>
- Trust boundary: client (attacker-controlled) -> game server (authoritative)
- Root cause: server accepts <client-asserted value / forged packet / replayed msg>
  as <truth> without <server-side recompute / nonce / ownership / range check>.
- Reproduction:
    SETUP:   <build, test-server, client offsets/symbols, capture tooling>
    TRIGGER: <exact packet bytes / transaction sequence / tampered save / forged receipt>
    OBSERVE: <server-side state change / granted item/currency / undetected AC bypass>
- Impact: <arbitrary damage | item/currency dupe | economy inflation | integrity bypass>
- Severity: <mapped to the program's tiering; note real-player / revenue impact>
- Suggested fix: <server-authoritative recompute | nonce/sequence + HMAC | atomic
  transaction | server-side range/ownership validation | move check off the client>
- Dedup check: not matched by <advisories/known issues reviewed>.
```

---

## 7. Tools

| Tool | Purpose |
|------|---------|
| `ghidra` / `r2` (radare2) | Static RE of native clients (IL2CPP blobs, Unreal Shipping builds, custom engines) |
| `Il2CppDumper` | Recover Unity IL2CPP type/method symbols from `GameAssembly`/`libil2cpp` + `global-metadata.dat` |
| `ilspycmd` / dnSpy(Ex) | Decompile/inspect (and patch) Unity Mono managed assemblies |
| `frida` | Dynamic instrumentation — hook RPC/serialize/validation fns, confirm offsets, dump live structs |
| `gdb` | Native debugging / breakpoints on protocol & validation routines |
| Cheat Engine / `scanmem` (GameConqueror) | Locate player/entity/inventory structures, confirm field offsets |
| `wireshark` / `tshark` | Capture & dissect the wire protocol; build replay/forge inputs (authorized env only) |
| `fuzz_generate_harness` / `fuzz_triage_crash` / `fuzz_status` | Agent fuzzing scaffolding + crash triage for a host-lifted protocol/serializer parser (`decepticon.tools.fuzzing`) |
| `python3` (scapy / sockets) | Craft, replay, and forge protocol packets against a test server |
