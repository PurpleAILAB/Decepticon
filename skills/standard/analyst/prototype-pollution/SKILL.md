---
name: prototype-pollution
description: Hunt JavaScript prototype pollution (CWE-1321) — the 2023-2026 meta-vulnerability that chains into RCE, auth bypass, and SSRF on most Node.js stacks.
---

# Prototype Pollution Playbook

Prototype pollution is the JavaScript equivalent of a universal gadget:
plant a property on `Object.prototype` and it appears on every object in
the runtime. Worthless in isolation, deadly in chain (`__proto__.isAdmin
= true` → auth bypass; `__proto__.shell = "/bin/bash"` → RCE via `spawn`).

## 1. Sinks — the libraries that still introduce sinks

Keep a running list per engagement. These continue to ship sinks in 2026:

- **Deep-merge:** `lodash.merge`, `deepmerge` (pre-fix), `merge-deep`, `deepExtend`, `hoek.merge`, `mixme`
- **Deep-clone:** `lodash.defaultsDeep`, `lodash.zipObjectDeep`, `set-value` (pre-3.0.3)
- **URL-to-obj:** `qs`, `express-fileupload`, `jquery.extend(true, ...)`
- **Config loaders:** `node-config` recursive merge, `dotenv-extended`, `rc`
- **Template engines:** Handlebars helpers fed from untrusted ctx

```bash
# Every JS/TS project: sweep known-bad versions
jq '.dependencies,.devDependencies | to_entries[] | select(.key | test("merge|lodash|set-value|dot-object|dot-prop|node-pg"))' /workspace/src/package.json
npm ls lodash set-value dot-prop 2>/dev/null | grep -E '[0-9]'
```

## 2. Sources

Any user input deserialized into a nested object:
- JSON body parsers (`body-parser`, `express.json`)
- Query string parsers (`qs` with default config parses `a[b][__proto__][c]=1`)
- YAML uploads
- Form-data / multipart

## 3. Audit workflow

1. Find every deep merge call site.
2. Trace each one backwards — is the right-hand object user-controlled?
3. If yes: check the merge function's prototype-pollution fix version.
4. Even if the merge is fixed, check whether a *copy* (lodash.set,
   dot-path-value, jsonpath.set) creates a pollution path.

## 4. Exploitation gadgets

Poisoning `Object.prototype` doesn't do anything by itself — you need
a gadget that reads a property that didn't exist before.

Classic gadgets:

- **`child_process.spawn(cmd, args, opts)`** — opts has a `shell` option.
  Poison `__proto__.shell = "/bin/bash"` then any subsequent spawn call
  executes through bash and interprets args as shell strings.
- **Express middleware** — most middlewares check `options.someFlag` with
  `if (opts.someFlag)`. Poisoning that flag flips security defaults.
- **Templating** — Handlebars and EJS read `helpers` and `partials` from
  the context object; pollution adds helpers that execute code.
- **`lodash.template`** — if the template source is built from `_.template(tpl, ctx)` you can inject via polluted `escape`/`evaluate` keys.
- **`mongoose`** — polluting `Schema.Types` causes subsequent schema
  definitions to use attacker-controlled types.

## 5. PoC template

```bash
# Classic lodash.merge RCE via child_process.spawn
curl -X POST https://target.com/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"__proto__": {"shell": "/bin/bash", "env": {"PATH": "/tmp:/usr/bin"}}}'

# Second request triggers the gadget
curl https://target.com/api/render-pdf
# → any subsequent child_process.spawn call now runs through /bin/bash
```

## 6. Success signals for `validate_finding`

- Server error with stack trace referencing `Object.prototype`
- Output of injected command reflected in next response
- Admin-only endpoint now returns 200 after poisoning `__proto__.isAdmin`

Negative control: same payload with `proto` (no leading underscores) —
should have no effect. If it does, the endpoint is treating that key
specially and the finding is unrelated.

## 7. Default CVSS

| Variant                               | Vector                                       | Score |
|---------------------------------------|----------------------------------------------|-------|
| DoS (crash Node process)              | AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H          | 7.5   |
| Auth bypass via `isAdmin` pollution   | AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N          | 9.1   |
| RCE via spawn gadget                  | AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H          | 10.0  |

## 8. Chain promotion

Prototype pollution is almost always the *first* hop of a chain. After
validation, add an `enables` edge from the pollution vuln to:
- the spawn / template gadget vuln (RCE chain)
- the auth check vuln (privilege escalation chain)
- the SSRF vuln if the downstream request lib has an options pollution
  surface

Chain weight 0.4 — pollution is cheap once the merge sink is known.
