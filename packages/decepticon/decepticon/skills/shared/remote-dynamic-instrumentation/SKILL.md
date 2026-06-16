---
name: remote-dynamic-instrumentation
description: Remote / live reverse engineering — dynamic instrumentation and remote debugging of running targets on remote PCs, phones, and embedded devices via Frida, remote GDB/LLDB, JDWP, and JTAG/SWD/serial, over network or USB transports.
allowed-tools: Bash Read Write
metadata:
  subdomain: reverse-engineering
  when_to_use: "remote debugging dynamic instrumentation live analysis attach to process Frida frida-server frida-trace frida gadget objection gdbserver remote gdb gdb-multiarch lldb debugserver JDWP ADB adb connect usbmuxd iproxy libimobiledevice jailbreak OpenOCD JTAG SWD UART serial console hook trace runtime on-device kernel debugging KGDB SSL pinning bypass method tracing memory dump decrypt frida-ios-dump"
  tags:
    - frida
    - remote-debugging
    - dynamic-instrumentation
    - gdb
    - adb
    - ios
    - android
    - jtag
    - runtime
  mitre_attack:
    - T1620
    - T1056
    - T1057
---

# Remote & Live Dynamic Instrumentation Playbook

Static analysis (Ghidra, r2, the `deobfuscation-devirtualization` skill)
tells you what code *could* do. Remote/live RE tells you what it *does* —
on the actual device, against the real server, with the real keys in
memory. You attach to a running process (or halt a running chip), hook the
exact routine you care about, and watch arguments, return values, decrypted
buffers, and control flow as they happen.

This skill is the cross-platform spine for getting an instrumentation
foothold on a **remote PC, a phone (Android/iOS), or an embedded/IoT
device**, over **network or USB** transports, and driving Frida, remote
GDB/LLDB, JDWP, and JTAG/SWD/serial once you are attached.

> **Authorized targets only.** Live instrumentation of a device or app is
> intrusive — you are modifying a running process or halting hardware.
> Operate only on devices you own, an in-scope engagement asset, a CTF, or
> a lab. If scope is unclear, stop and confirm. See `shared/opsec` for
> scope enforcement and evidence handling; don't trample a production
> device (§8).

This skill assumes the target may also be obfuscated or anti-instrumented.
When the live process fights back, cross-link `reverser/anti-debug-bypass`
(defeat anti-Frida / anti-ptrace / debugger detection) and
`reverser/deobfuscation-devirtualization` (when the routine you hooked is
virtualized). For unpacking a flash image you dumped over JTAG, hand off to
the `standard/iot/` firmware skills.

---

## 1. When to go remote/live (vs static)

Reach for live instrumentation when the answer is not in the bytes at rest:

| Use live RE when… | Why static fails |
|---|---|
| Behavior depends on **runtime state** (env, time, server response, RNG, device fingerprint) | the value isn't in the binary; it materializes at runtime |
| The target talks to a **server / hardware peripheral** and you need the live protocol/keys | you need the session keys / nonces in memory, not the cipher |
| The binary is **packed/obfuscated/virtualized** | decrypted code + resolved imports only exist in RAM (`memory dump` beats disasm) |
| You must **hook/trace/dump a live process** — args, return values, decrypted buffers | static can't show concrete values |
| **Anti-static** tricks (string/API hashing, dynamic resolution) hide intent | let the binary resolve them, then observe |
| The logic lives **on-device** (phone app, firmware, kernel) | you can't run it on your workstation |

Live RE is **complementary** to static, not a replacement: triage and map
statically (Ghidra/r2 → find the function, the struct, the candidate
crypto routine), then attach live to confirm and extract. The static map
tells you *where* to put the hook; the hook tells you *what flows through*.

---

## 2. Transports & the sandbox-connectivity reality

The Decepticon sandbox is a **container**. What you can reach depends
entirely on the transport, and this is the single most common point of
confusion — state it honestly before you start.

The remote-RE toolchain (frida-tools, objection, gdb-multiarch, gdbserver,
android-tools-adb, libimobiledevice-utils + usbmuxd + iproxy, openocd,
minicom/picocom, socat, usbutils) is present only when the image was built
with `INSTALL_REMOTE_RE=true`. Verify before assuming: `command -v frida
adb gdb-multiarch iproxy openocd`.

### 2.1 Network transports — work whenever the sandbox can route to the target

No special container privileges needed; you just need IP reachability
(same LAN, VPN, port-forward, or the device on a routable address).

| Transport | Command shape |
|---|---|
| **Frida over TCP** | target runs `frida-server -l 0.0.0.0:27042`; host: `frida -H <ip>:27042` / `frida-ps -H <ip>` |
| **gdbserver** | target: `gdbserver :1234 ./prog`; host: `gdb-multiarch`, `target remote <ip>:1234` |
| **ADB over Wi-Fi/TCP** | device: `adb tcpip 5555` (once over USB), then `adb connect <ip>:5555` |
| **iOS debugserver over TCP** | on device: `debugserver *:1234 -a <proc>`; host lldb: `gdb-remote <ip>:1234` |
| **socat relays** | bridge/forward a serial or TCP endpoint into reach: `socat TCP-LISTEN:9000,fork TCP:<ip>:1234` |

### 2.2 USB transports — require the operator to pass the host USB device into the container

USB-attached phones and JTAG/serial adapters are **not** reachable from a
default container. The operator must expose the host USB to the sandbox at
deployment:

```bash
# Deployment prerequisite (run by the OPERATOR on the host, not inside the sandbox):
# Pass the whole USB bus into the container:
docker run --device=/dev/bus/usb:/dev/bus/usb ...     # specific bus/devices preferred
# or, broad:
docker run --privileged -v /dev/bus/usb:/dev/bus/usb ...
# For iOS USB, the host's usbmuxd socket must be shared so libimobiledevice can see the device:
docker run -v /var/run/usbmuxd:/var/run/usbmuxd ...    # plus the --device line above
# Serial/JTAG adapters appear as /dev/ttyUSB* /dev/ttyACM*: pass those nodes too.
docker run --device=/dev/ttyUSB0 ...
```

Once passed through:
- `lsusb` should list the phone / debug probe (confirms passthrough worked).
- Android USB: `adb devices` shows the device (`adb` talks to its own
  `adb-server`; run `adb kill-server && adb start-server` after passthrough).
- iOS USB: `usbmuxd` must be running in the container (or the host socket
  shared); `idevice_id -l` lists connected devices.

> **Rule of thumb:** if you can `ping`/route to it, prefer network. If it's
> only on a USB cable, you need passthrough first — there is no software
> workaround inside the container. When passthrough isn't available, pivot:
> put the device on the network (`adb tcpip`, frida-server `-l`, iproxy on a
> host-side helper) and connect over TCP.

---

## 3. Frida — the cross-platform spine

Frida is the workhorse: a scriptable DBI framework that injects a
JavaScript engine into the target and lets you hook functions, read/write
memory, trace, and call functions, on Android, iOS, Linux, Windows, macOS,
and many embedded Linux targets.

### 3.1 Architecture — three deployment modes

| Mode | What it is | When |
|---|---|---|
| **frida-server** | a daemon running on the target as root; host CLI connects to it (USB or `-H` TCP) | rooted/jailbroken device, or a PC/embedded box you control |
| **Frida Gadget** | a shared library embedded *inside* the target app, no separate server, no root | non-root Android / non-jailbroken iOS — inject via repackage/re-sign |
| **Local/embedded** | `frida -p <pid>` against a process on the same host | you're already on the box |

Host CLIs (frida-tools): `frida` (REPL), `frida-ps`, `frida-trace`,
`frida-discover`, `frida-ls-devices`. Device selection flags are universal:
`-U` (USB), `-H <host>:<port>` (network/remote), `-D <id>` (specific
device), `-R` (remote default).

### 3.2 Android

```bash
# --- Rooted: push the right-arch frida-server and run it ---
adb shell getprop ro.product.cpu.abi            # arm64-v8a / armeabi-v7a / x86_64
# download matching frida-server-<ver>-android-<arch>, then:
adb push frida-server /data/local/tmp/frida-server
adb shell "chmod 755 /data/local/tmp/frida-server"
adb shell "su -c '/data/local/tmp/frida-server &'"   # run as root, backgrounded

# Enumerate + attach (USB):
frida-ps -U                       # processes on the USB device
frida-ps -Uai                     # installed apps (a) incl. not-running (i)
frida -U -f com.target.app        # SPAWN the app suspended, then resume (best for early hooks)
frida -U -n com.target.app        # ATTACH to a running process by name
frida -U -p 1234                  # ATTACH by pid

# --- TCP instead of USB: forward the server port, or bind it on the device ---
adb forward tcp:27042 tcp:27042   # then: frida-ps -H 127.0.0.1:27042
adb shell "su -c '/data/local/tmp/frida-server -l 0.0.0.0:27042 &'"   # then: frida -H <device-ip>:27042

# --- objection: batteries-included Frida runtime ---
objection -g com.target.app explore
#   android sslpinning disable      # defeat cert pinning
#   android hooking watch class com.target.Crypto
#   memory search / dump, keystore, intent fuzzing, etc.

# --- Non-root: Frida Gadget repackaging (no frida-server, no root) ---
# Decompile, inject libgadget.so + a load hook, rebuild, re-sign, install:
apktool d target.apk -o target_src
# add android:extractNativeLibs / place libgadget.so per-abi under lib/<abi>/,
# inject a System.loadLibrary("gadget") at app entry (smali), then:
apktool b target_src -o target_patched.apk
# (objection can automate the gadget injection: `objection patchapk -s target.apk`)
zipalign -p 4 target_patched.apk target_aligned.apk
apksigner sign --ks debug.keystore target_aligned.apk
adb install -r target_aligned.apk
```

### 3.3 iOS

```bash
# --- Jailbroken: install frida-server via Cydia/Sileo (Frida repo) ---
#   add https://build.frida.re to Sileo sources -> install "Frida"; it runs frida-server as root.
frida-ps -U                              # over usbmuxd (USB)
frida -U -f com.target.App               # spawn
frida -U -n TargetApp                    # attach
# TCP: forward debugserver/frida port off-device with iproxy (see §6), then frida -H 127.0.0.1:27042

# --- Non-jailbroken: Frida Gadget via app re-sign ---
# objection patches the IPA: decrypts/inserts FridaGadget.dylib, re-signs with your provisioning profile:
objection patchipa --source target.ipa --codesign-signature <CODESIGN_ID>
# then deploy the patched IPA (ios-deploy / Xcode / TrollStore on supported iOS), and:
frida-ps -Uai
frida -U -n TargetApp
```

### 3.4 PC (Linux / Windows / macOS)

```bash
# Run frida-server on the target box (download the matching frida-server build), then attach remotely:
./frida-server -l 0.0.0.0:27042 &                 # on the target
frida -H <target-ip>:27042 -n target_process       # from the sandbox
frida-ps -H <target-ip>:27042

# Or, when you're already on the host: attach locally.
frida -p $(pgrep target) -l hook.js
frida -f /usr/bin/target -l hook.js                # spawn + instrument from the first instruction
```

### 3.5 Embedded / Linux

```bash
# Cross-compile or fetch a frida-server matching the device arch (arm/arm64/mips/mipsel).
# Get it onto the device (scp/tftp/adb/ftp), make it executable, run it:
./frida-server-<ver>-linux-<arch> -l 0.0.0.0:27042 &
# From the sandbox (network route required):
frida -H <device-ip>:27042 -n target_daemon
```

### 3.6 Concrete instrumentation

```javascript
// hook.js — Interceptor.attach: log args + return value of a function
const f = Module.getExportByName(null, "EVP_DecryptUpdate");   // null = search all modules
Interceptor.attach(f, {
  onEnter(args) {
    this.out = args[1];                 // out buffer ptr
    this.lenp = args[2];                // int* outl
    console.log("[EVP_DecryptUpdate] inlen=" + args[5].toInt32());
  },
  onLeave(retval) {
    const n = this.lenp.readInt();
    console.log("decrypted " + n + " bytes:\n" +
                hexdump(this.out, { length: n, ansi: true }));
  }
});

// Resolve + read memory / enumerate exports
Process.enumerateModules().forEach(m => console.log(m.name, m.base, m.size));
Module.enumerateExports("libtarget.so").slice(0, 20).forEach(e => console.log(e.name, e.address));
const p = Module.findExportByName("libtarget.so", "g_session_key");
console.log(hexdump(p.readByteArray(32)));

// Java (Android, ART) — hook a method and dump/alter args
Java.perform(() => {
  const C = Java.use("com.target.Crypto");
  C.decrypt.overload("[B").implementation = function (buf) {
    const out = this.decrypt(buf);
    console.log("decrypt -> " + Java.use("java.lang.String").$new(out));
    return out;
  };
});

// ObjC (iOS) — hook a selector
const m = ObjC.classes.NSURLRequest["- initWithURL:"];
Interceptor.attach(m.implementation, {
  onEnter(args) { console.log("URL: " + new ObjC.Object(args[2]).toString()); }
});
```

```bash
# frida-trace — auto-generate + attach handlers for matching functions (wildcards)
frida-trace -U -n TargetApp -i "*decrypt*" -i "CCCrypt"          # by export name
frida-trace -U -f com.target.app -j "com.target.*!*"            # Java methods (Android)
frida-trace -U -n TargetApp -m "-[NSURLSession *]"               # ObjC methods (iOS)

# Stalker-based code tracing (instruction/block-level) lives in JS:
#   Stalker.follow(threadId, { events: { call: true, ret: true }, onReceive(...) {...} })

# Dump decrypted / unpacked modules straight from memory:
#   in REPL:  var m = Process.getModuleByName("libtarget.so");
#             File.writeAllBytes("/data/local/tmp/dump.bin", m.base.readByteArray(m.size));
# iOS App Store binaries are FairPlay-encrypted on disk — dump the decrypted image from RAM:
frida-ios-dump -H <ip> -u root -P <pass> TargetApp   # pulls + decrypts the .app into an IPA
```

### 3.7 Frida detection & bypass

Apps detect Frida via the default port (27042), the `frida-server`
process/thread names, `/proc/self/maps` mentions of `frida`/`gum-js-loop`,
`re.frida.server` D-Bus name, the gadget library name, and ptrace/`TracerPid`
checks. Quick counters: run frida-server on a **non-default port** and a
**renamed binary** (`frida -H ip:9999`, `./fs01 -l 0.0.0.0:9999`), use
**spawn (`-f`)** so your anti-detection hooks land before the check runs,
and hook the detection routines themselves (string compares, `fopen` of
`/proc/self/maps`, `Runtime.exec`). For the full anti-instrumentation
arsenal (anti-ptrace, anti-debug, integrity checks, root/jailbreak
detection) cross-link **`reverser/anti-debug-bypass`**.

---

## 4. Remote GDB / LLDB

When Frida isn't available (stripped embedded daemon, kernel, early boot,
bootloader) or you need instruction-level control, use a remote debug stub.

### 4.1 Linux / embedded ELF (gdbserver)

```bash
# On the TARGET (push gdbserver onto the device if needed; it must match the device, host gdb is cross):
gdbserver :1234 ./prog                 # launch under the stub
gdbserver :1234 --attach <pid>         # attach to a running process
gdbserver --multi :1234                # multiprocess server (extended-remote)

# In the SANDBOX (gdb-multiarch handles foreign arches):
gdb-multiarch ./prog                    # load a local copy with symbols
(gdb) set architecture aarch64          # or arm, mips, etc. — match the target
(gdb) set sysroot /path/to/extracted/rootfs    # so gdb resolves the device's shared libs
(gdb) target remote <device-ip>:1234    # or  target extended-remote  with --multi
(gdb) b *0x4008a0
(gdb) c
(gdb) x/16xb $sp
(gdb) info registers
```

`set sysroot` is the difference between readable backtraces and `??` — point
it at the device's extracted filesystem so symbols/libraries resolve. Use
`solib-search-path` if libraries live elsewhere.

### 4.2 Kernel debugging

```bash
# KGDB over serial: kernel cmdline e.g. kgdboc=ttyS0,115200 kgdbwait, then on the host:
gdb-multiarch vmlinux
(gdb) set serial baud 115200
(gdb) target remote /dev/ttyUSB0        # or a socat-bridged TCP endpoint
# KGDB over network: kgdboc=eth0 with kgdb-over-ethernet patches, or use a serial<->TCP bridge:
socat TCP-LISTEN:4321,reuseaddr,fork FILE:/dev/ttyUSB0,b115200,raw

# QEMU as the gdbstub (emulated firmware / kernel bring-up):
qemu-system-arm ... -s -S                # -s = gdbstub on :1234, -S = freeze CPU at start
gdb-multiarch vmlinux
(gdb) target remote :1234
```

### 4.3 iOS / macOS (debugserver + LLDB)

```bash
# On a jailbroken device, debugserver ships under the DeveloperDiskImage or is sideloaded:
debugserver *:1234 -a TargetApp          # bind on all interfaces, attach by name
# or:  debugserver *:1234 /Applications/Target.app/Target   # launch
# Tunnel USB->TCP first if not on the network (see §6):
iproxy 1234 1234 &
# From the sandbox:
lldb
(lldb) platform select remote-ios
(lldb) process connect connect://127.0.0.1:1234     # via iproxy
# (lldb) gdb-remote <device-ip>:1234                # direct network
(lldb) image list
(lldb) br s -n "-[Target verifyLicense]"
(lldb) c
```

---

## 5. Android specifics

### 5.1 ADB transport

```bash
adb devices -l                       # confirm device (USB needs passthrough, §2.2)
adb tcpip 5555                       # switch the daemon to TCP (one-time, over USB)
adb connect <device-ip>:5555         # now talk to it over the network
adb shell                            # interactive shell
adb pull /data/app/.../base.apk .    # extract the installed APK for static analysis
adb logcat                           # runtime logs
```

### 5.2 run-as (debuggable apps) & file access

```bash
# If the app is android:debuggable="true", run-as gives its uid without root:
adb shell run-as com.target.app ls -l /data/data/com.target.app/
adb shell run-as com.target.app cat databases/secrets.db > secrets.db
```

### 5.3 JDWP — debug a debuggable app with jdb (no Frida)

```bash
adb jdwp                              # lists JDWP-debuggable pids
adb forward tcp:8000 jdwp:<pid>      # forward the JDWP channel of that pid
jdb -attach localhost:8000           # source-level Java debugging
#   stop in com.target.Login.check
#   locals / print / step
```

### 5.4 SSL pinning bypass + method tracing

```bash
# objection one-liner pinning bypass (covers OkHttp/TrustManager/Conscrypt patterns):
objection -g com.target.app explore -s "android sslpinning disable"
# Frida method tracing of the whole package:
frida-trace -U -f com.target.app -j "com.target.*!*"
# Pull traffic through a proxy once pinning is off:  adb shell settings put global http_proxy <host>:8080
```

**Root vs non-root:** root → push `frida-server`, full `frida -U`, system
file access, magisk modules for pinning. Non-root → Frida Gadget
repackaging (§3.2), `run-as` for debuggable apps, JDWP for debuggable apps.

---

## 6. iOS specifics

### 6.1 USB→TCP tunneling with usbmuxd + iproxy

```bash
# usbmuxd must be running (or the host socket shared, §2.2). Confirm the device:
idevice_id -l                        # UDIDs of connected devices
ideviceinfo                          # device/OS details
# iproxy maps a local TCP port to a device port over USB (libusbmuxd-tools):
iproxy 2222 22 &                     # local 2222 -> device SSH (jailbroken, OpenSSH)
iproxy 1234 1234 &                   # local 1234 -> device debugserver
ssh -p 2222 root@127.0.0.1           # ssh into the jailbroken device over USB
```

### 6.2 libimobiledevice tooling

```bash
ideviceinstaller -l                  # list installed apps
ideviceinstaller -i target.ipa       # install
idevicebackup2 backup ./backup       # device backup
idevicesyslog                        # live system log
idevicedebug run com.target.App      # launch an app under the debug service
```

### 6.3 Decrypting App Store binaries (jailbroken)

App Store apps are FairPlay-encrypted on disk; the decrypted text only
exists in RAM at runtime. Dump it:

```bash
frida-ios-dump -H <ip> -u root -P <pass> TargetApp   # Frida-based, pulls a decrypted IPA
# dump-decrypted (dumpdecrypted.dylib via DYLD_INSERT_LIBRARIES) is the classic alternative.
class-dump TargetApp/Target          # recover ObjC headers/selectors from the decrypted Mach-O
# Keychain dump (jailbroken):  objection -> ios keychain dump   (or keychain_dump tools)
```

### 6.4 Jailbroken vs non-jailbroken — keep them separate

| | Jailbroken | Non-jailbroken |
|---|---|---|
| Frida | `frida-server` from Sileo, full `frida -U` | **Gadget** via `objection patchipa` re-sign only |
| Debugger | `debugserver` + lldb, SSH via iproxy | limited; needs a dev-signed app + entitlements |
| Decrypt | frida-ios-dump / dumpdecrypted | not possible without a jailbreak |
| Filesystem | full root FS over SSH | app sandbox only |

---

## 7. Embedded / IoT hardware

When there's no OS-level debug service, drop to the hardware interfaces.
USB debug probes/serial adapters require passthrough (§2.2).

### 7.1 UART / serial console

```bash
# Identify the adapter (FTDI/CP210x/CH340 show up as ttyUSB*, native CDC as ttyACM*):
dmesg | tail; ls /dev/ttyUSB* /dev/ttyACM*
# Common baud rates: 115200, 57600, 38400, 9600. Connect:
picocom -b 115200 /dev/ttyUSB0        # exit: Ctrl-A Ctrl-X
minicom -D /dev/ttyUSB0 -b 115200     # alternative
# A console may drop you at a shell, U-Boot, or a login. U-Boot often allows
# memory peek/poke (md/mw), env edits, and booting custom images.
```

### 7.2 JTAG / SWD via OpenOCD

```bash
# OpenOCD = interface config (the debug probe) + target config (the chip). Examples:
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg          # ST-Link + STM32F4 (SWD)
openocd -f interface/jlink.cfg  -f target/nrf52.cfg             # J-Link + nRF52
openocd -f interface/ftdi/ft2232h.cfg -f target/<soc>.cfg       # generic FT2232 JTAG
# OpenOCD then exposes two endpoints:
#   telnet 127.0.0.1 4444    -> command/monitor shell
#   gdb     :3333            -> GDB remote stub
```

```bash
# Telnet monitor: halt the core, read/dump flash & RAM:
telnet 127.0.0.1 4444
> reset halt
> flash banks
> dump_image firmware.bin 0x08000000 0x100000     # dump 1MB of internal flash
> mdw 0x20000000 16                                # read 16 words of SRAM
> flash write_image erase patched.bin 0x08000000   # (re-flash; destructive — be sure)

# Or attach GDB to the OpenOCD stub for source/asm-level control:
gdb-multiarch firmware.elf
(gdb) target remote :3333
(gdb) monitor reset halt
(gdb) b *0x08001234
(gdb) c
```

### 7.3 SPI flash dump (chip-off / in-circuit)

```bash
# With an SPI programmer (e.g. CH341A / FT2232 via flashrom) wired to the flash chip:
flashrom -p ch341a_spi -r dump.bin                # read the external SPI flash
flashrom -p ft2232_spi:type=232H -r dump.bin
```

Hand the resulting `firmware.bin` / `dump.bin` to the **`standard/iot/`**
firmware skills for unpacking (binwalk, filesystem extraction, bootloader
analysis) and static RE of the recovered binaries.

---

## 8. Workflow & safety

A repeatable live-RE loop, scoped to the targeted behavior:

1. **Authorize & scope.** Confirm the device/app is in scope (`shared/opsec`
   §7). Live instrumentation is intrusive; never attach to a production
   device you don't control. Note that hooks/breakpoints can crash or hang
   the target — don't do it to something load-bearing.
2. **Recon the target.** Arch (`getprop ro.product.cpu.abi`, `uname -m`,
   `readelf -h`), OS, app/package, root/jailbreak state, available debug
   services. This decides Frida-vs-GDB and which deployment mode.
3. **Pick the transport** (§2): network if routable, USB only if the
   operator passed the device through. Establish reachability first
   (`lsusb`/`adb devices`/`idevice_id -l`/`ping`).
4. **Map statically first.** Use Ghidra/r2 to find the exact function,
   selector, or address you want — so your hook is surgical, not a fishing
   net.
5. **Attach & instrument the specific routine.** Spawn (`-f`) when you need
   early hooks (before anti-debug/pinning runs); attach (`-n`/`-p`) for an
   already-running target. Hook only the routine of interest.
6. **Capture evidence.** Save traces, memory dumps, hooked args/return
   values, decrypted buffers to the engagement directory with timestamps
   (`shared/opsec` §6). Reproducibility matters: record the exact attach +
   hook steps.
7. **Correlate with static.** Feed recovered values (keys, addresses,
   decoded strings, resolved imports) back into the static map to confirm
   the vuln/logic.
8. **For bounty/report:** frame the finding around the recovered
   vulnerability or logic flaw — not the act of hooking. Provide a minimal,
   reproducible attach+hook recipe so the triager can replay it.

If the target detects and fights instrumentation, pivot to
`reverser/anti-debug-bypass`; if the hooked routine is virtualized/obfuscated,
pivot to `reverser/deobfuscation-devirtualization`.

---

## 9. Tools reference

| Tool | Purpose | Invocation | Transport |
|---|---|---|---|
| **frida / frida-tools** | scriptable DBI: hook, trace, dump, call | `frida -U/-H/-f/-n/-p`, `frida-ps`, `frida-trace -i/-j/-m` | USB (`-U`) or network (`-H`) |
| **objection** | Frida runtime: pinning bypass, hooking, gadget patching | `objection -g <pkg> explore`, `objection patchapk/patchipa` | rides Frida (USB/net) |
| **frida-ios-dump** | dump decrypted iOS App Store binaries from RAM | `frida-ios-dump -H <ip> -u root -P <pass> <App>` | network (or iproxy USB) |
| **gdb-multiarch** | cross-arch GDB client for remote stubs | `gdb-multiarch`, `set architecture`, `target remote ip:port` | network (stub) / serial |
| **gdbserver** | on-target debug stub for ELF processes | `gdbserver :1234 ./prog` / `--attach <pid>` | network (runs on target) |
| **lldb / debugserver** | macOS/iOS debugger + on-device stub | `debugserver *:1234 -a <proc>`; `(lldb) gdb-remote ip:1234` | network / iproxy USB |
| **adb** | Android Debug Bridge: shell, push/pull, forward, JDWP | `adb connect/tcpip/forward/jdwp/shell/pull` | USB (passthrough) or TCP (`adb connect`) |
| **jdb** | source-level Java debugger over JDWP | `adb forward tcp:8000 jdwp:<pid>; jdb -attach localhost:8000` | via adb (USB/TCP) |
| **libimobiledevice-utils** | iOS device mgmt: info, install, syslog, debug | `idevice_id -l`, `ideviceinstaller`, `idevicesyslog` | USB (usbmuxd) |
| **iproxy** (libusbmuxd-tools) | tunnel a device TCP port over USB to localhost | `iproxy <local> <remote>` | USB→TCP bridge |
| **usbmuxd** | multiplexer daemon backing iOS USB comms | runs as a service (host socket shared into container) | USB |
| **openocd** | JTAG/SWD on-chip debug: halt, dump, flash | `openocd -f interface/<probe>.cfg -f target/<chip>.cfg` → telnet 4444 / gdb :3333 | USB debug probe (passthrough) |
| **picocom / minicom** | serial console terminal | `picocom -b 115200 /dev/ttyUSB0` | USB serial (passthrough) |
| **socat** | relay/bridge serial↔TCP, TCP↔TCP | `socat TCP-LISTEN:4321,fork FILE:/dev/ttyUSB0,b115200,raw` | bridges transports |
| **qemu (gdbstub)** | emulate firmware/kernel with a built-in GDB stub | `qemu-system-<arch> ... -s -S` → gdb `target remote :1234` | local (emulation) |
| **flashrom** | read/write SPI flash via a programmer | `flashrom -p ch341a_spi -r dump.bin` | USB programmer (passthrough) |
| **usbutils (lsusb)** | confirm USB passthrough worked | `lsusb` | USB |
