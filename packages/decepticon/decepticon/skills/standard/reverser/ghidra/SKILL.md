---
name: reverser-ghidra
description: Deep binary analysis via Ghidra — headless analyzeHeadless or live MCP bridge with 245 tools. Decompilation, xrefs, function listing, batch operations, P-code emulation, convention enforcement.
metadata:
  subdomain: reverse-engineering
  when_to_use: "ghidra deep binary analysis headless analyzeHeadless mcp bridge decompile xref function listing p-code"
  upstream_ref: "NSA Ghidra reverse-engineering suite + Decepticon ghidra-mcp bridge (245 tools)"
---

# Ghidra Deep Analysis

Ghidra is the primary reverse engineering backend. Two modes:
- **MCP bridge** (preferred) — 245 tools via HTTP at `$GHIDRA_MCP_URL`
- **Headless** (fallback) — `analyzeHeadless` + postScript for JSON output

## Prerequisites
```
ghidra_status()
```
Check if Ghidra headless and/or MCP bridge are available.

## 1. Full Analysis
```
ghidra_analyze(binary="/workspace/target.exe")
```
Returns: functions (up to 500), imports, exports, language, image base.
Auto-selects MCP if running, headless otherwise.

## 2. Decompile a Function
```
ghidra_decompile(binary="/workspace/target.exe", function="main")
ghidra_decompile(binary="/workspace/target.exe", function="0x401000")
```
Accepts symbol name or hex address. Returns C pseudocode.

## 3. Cross-References (MCP)
```
ghidra_xrefs(binary="/workspace/target.exe", address="0x401000")
```
Returns up to 200 xrefs with source function context.

## 4. Fallback: Script Generation
If headless/MCP are unavailable, generate a recon script and run via bash:
```
bin_ghidra_script(binary="/workspace/target.exe")
```

## MCP Bridge — Full 245-Tool Coverage
When the Ghidra MCP bridge is running, the reverser also has access to
the complete bethington/ghidra-mcp tool surface via bash + curl:

- **Function analysis** — decompilation, call graphs, completeness scoring
- **Data flow** — PCode-graph value propagation (forward / backward)
- **Structure discovery** — struct/union/enum creation, field analysis
- **String extraction** — regex search, quality filtering
- **Import/export analysis** — symbol tables, ordinal resolution
- **Memory inspection** — raw reads, byte pattern search
- **Cross-binary documentation** — SHA-256 function hash matching
- **P-code emulation** — run functions in isolation, brute-force API hashes
- **Batch operations** — bulk rename, comment, type (93% fewer API calls)
- **Script management** — create, run, update Ghidra scripts via MCP
- **Convention enforcement** — auto-fix naming, type safety, documentation

## Workflow
1. `ghidra_status()` → check availability
2. `ghidra_analyze()` → full triage
3. Pick interesting functions → `ghidra_decompile()` each
4. For xref hunting → `ghidra_xrefs()` on dangerous imports
5. Record all findings in the knowledge graph
