---
name: windows-driver-assessment
description: "Defensive Windows internals and driver exposure assessment for owner-authorized systems and disposable research VMs."
allowed-tools: Read Write Bash
metadata:
  subdomain: reverse-engineering
  when_to_use: "windows internals kernel driver signed driver BYOVD exposure HVCI VBS blocklist WinDbg ETW minidump defensive assessment"
  upstream_ref: "Microsoft vulnerable and malicious driver guidance, HVCI/VBS documentation, Windows Driver Kit debugging guidance"
  capability_contract:
    lane: windows-internals
    scope: isolated-lab
    environment: [disposable-windows-vm, snapshot-rollback, isolated-network]
    required_tools: [windbg, etw, sigcheck]
    evidence: [driver-inventory, signer-version-record, minidump, mitigation-recheck]
    verification: "reproduce only against a dedicated research driver in a freshly restored VM snapshot"
    negative_control: "confirm the documented mitigation or block policy prevents the same lab action"
    scorecard: [reproducer-rate, crash-dedup-precision, mitigation-verification-rate]
    benchmark: held-out-windows-driver
---

# Windows Driver Exposure Assessment

## Scope

Use this lane only for an owner-authorized endpoint inventory or a disposable
research VM. Preserve Windows security controls. Do not load vulnerable drivers,
disable HVCI/VBS, bypass EDR, deploy a BYOVD chain, or use anti-cheat systems as
test targets.

## Evidence-first workflow

1. **Pin the environment.** Record the Windows build, kernel build, VM snapshot
   ID, Secure Boot, HVCI, VBS, Microsoft vulnerable-driver blocklist state, and
   the exact driver file hash before analysis.
2. **Inventory exposure.** Collect driver path, service name, publisher,
   Authenticode chain, file version, loaded state, device interface, and
   vulnerability advisory or blocklist correlation. A name-only match is a lead,
   not a finding.
3. **Triage safely.** Perform static import/IOCTL/symbol review and ETW or
   debugger observation in the disposable VM. Capture a call stack or trace that
   ties the conclusion to the pinned binary.
4. **Verify a mitigation.** For a real exposure, capture the pre-remediation
   inventory; apply the documented vendor update, removal, or block policy; then
   repeat the same inventory and confirm the exposure no longer exists.
5. **Handle crashes as research artifacts.** Preserve the minimized input,
   minidump, symbols/build identity, stack trace, and a benign control execution.
   Do not convert a crash into persistence, privilege escalation, stealth, or
   production exploitation.

## Promotion rule

A driver finding requires a stable binary hash, signer/version evidence, a
reproducible observation in the isolated VM, and a negative control showing the
mitigated configuration does not reproduce the condition. Otherwise record a
triage lead only.
