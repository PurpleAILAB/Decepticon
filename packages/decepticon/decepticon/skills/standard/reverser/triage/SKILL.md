---
name: reverser-triage
description: Fast-path binary triage — identify format/arch/mitigations, grab high-signal strings and imports in under a minute.
metadata:
  subdomain: reverse-engineering
  when_to_use: "binary triage format architecture mitigations strings imports nm objdump readelf checksec file"
  upstream_ref: "Decepticon reverser triage playbook — file / readelf / checksec / strings / nm"
---

# Binary Triage (fast path)

## 1. Identify
```
bin_identify(path="/workspace/target")
```
Record: format, arch, bitness, NX, PIE, entry point. Add `file` node with these props.

## 2. Mitigation check
```bash
# checksec for extra signals (stack canary, RELRO, fortify)
apt-get install -y checksec 2>/dev/null || true
checksec --file=/workspace/target --format=json
```
Add any missing mitigation as a `vulnerability` node with severity=medium.

## 3. String harvest (categorized)
```
bin_strings(path="/workspace/target", category_filter="secret")
bin_strings(path="/workspace/target", category_filter="url")
bin_strings(path="/workspace/target", category_filter="crypto")
bin_strings(path="/workspace/target", category_filter="version")
```
Each hit in secret/crypto → add a `secret` node. Each url/ip → consider
adding an `entrypoint` or C2 candidate.

## 4. Imports risk
```bash
nm -D /workspace/target 2>/dev/null | awk '$2=="U"{print $3}' > /tmp/imports.txt
# or
objdump -T /workspace/target | awk '/\*UND\*/{print $NF}' > /tmp/imports.txt
```
Feed the list to `bin_symbols_report`. Anything with risk_score > 10 =
worth deeper look.

## 5. Version → CVE
For every version string found in step 3, call `cve_lookup` with the
candidate CVE IDs from `cve_by_package` if it's a known library.

## 6. Handoff
If NX/PIE are both off AND there are dangerous C imports → this is a
prime exploit-dev target; load `/skills/standard/reverser/rop-chain/SKILL.md`.
