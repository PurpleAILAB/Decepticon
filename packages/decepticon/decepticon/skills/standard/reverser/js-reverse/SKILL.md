---
name: reverser-js-reverse
description: Front-end JavaScript reverse engineering — locate request-signing and anti-bot logic, capture runtime evidence with minimal intrusion, rebuild the algorithm locally in Node, and deobfuscate for long-term reuse.
metadata:
  subdomain: reverse-engineering
  when_to_use: "javascript reverse js deobfuscation signature signing anti-bot request parameter encryption webpack ast sourcemap runtime hook cdp node rebuild environment patching"
  mitre_attack: T1027, T1140
  upstream_ref: "reverse-skill:skills/js-reverse (github.com/zhaoxuya520/reverse-skill @ ea582f3, MIT)"
---

# JavaScript Reverse Engineering

Targets: signing/encryption parameters on API calls, risk-control
fields, obfuscated bundles. If the target is a binary (PE/ELF/APK),
route to the native reversing skills instead. All capture work stays
within engagement scope — observe and replay only against in-scope
applications.

Core principles: **observe-first, hook-preferred, breakpoint-last,
rebuild-oriented, evidence-first**. Never guess an environment — every
local shim must trace back to observed page behavior.

## 1. Observe

Goal: pin down the target request, the scripts behind it, and candidate
functions — before touching anything.

- Open the page via a controllable browser (CDP endpoint, or the
  environment's browser/JS MCP surface when available)
- List network requests; for the target request, walk the initiator
  chain back to the issuing script
- Search script sources for signature-shaped identifiers
  (`sign`, `token`, `x-`, `encrypt`, `hmac`)

Required output: target request URL/pattern, initiator trace, suspect
script URLs, and an initial task record under `/workspace/jsrev/`.

## 2. Capture

Minimal-intrusion sampling of the live page:

- Break on XHR/fetch for the target URL first; inspect args, return
  values, and the call stack at pause time
- Evaluate small expressions at the pause site to read closure state
- Only set source-line breakpoints when XHR breaks can't isolate the
  signing function

Capture one clean parameter sample set: inputs, output signature, and
call order.

## 3. Rebuild

Move the evidence into a local Node harness under `/workspace/jsrev/`:

- Extract the signing function and its real dependencies from the
  captured scripts
- Stub `window`/`document`/`navigator`/`crypto`/`storage` ONLY from
  observed values — no invented globals
- One minimal environment patch per iteration

## 4. Patch

Driven by errors and first divergence:

```text
□ Run → read the exact missing global / first wrong value
□ Patch exactly that one thing
□ Re-run immediately
□ Log every patch decision in the task record
```

Done when the local harness reproduces the captured signature for the
captured inputs.

## 5. DeepDive

Only when the algorithm chain must be reused long-term: AST-assisted
deobfuscation (control-flow unflattening, string-array resolution,
JSVMP-style virtualization analysis), then prune to clean business
logic. Skip or downgrade this phase if the engagement only needed a
working signature.

## 6. Record

```
kg_add_node("file", label="js signing chain: <target endpoint>",
  props={"harness": "/workspace/jsrev/", "signature_reproduced": true,
         "obfuscation": "none|cfc|string-array|jsvmp",
         "key": "js-reverse:<host>-<endpoint>"})
```

If the client is a packaged desktop app, pair with
`/skills/standard/reverser/thick-client/SKILL.md`; for WASM or non-JS
artifacts, route back to the binary reversing lane.
