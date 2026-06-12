# RoE Machine Enforcement

> How the machine-readable Rules of Engagement block out-of-scope and
> forbidden tool calls at the moment the agent tries to run them.

## TL;DR

The human-readable RoE (`in_scope`, `out_of_scope`, `prohibited_actions`)
that Soundwave authors during planning is for the operator's review. A
separate, OPTIONAL `machine_enforcement` block inside the same
`roe.json` drives the **RoE-enforcement middleware**, which evaluates
every gated tool call against allowlist + denylist + forbidden-command
rules at tool-call time.

The block lives at `<workspace>/plan/roe.json`. When it is **absent**,
the middleware runs in audit-only mode: every gated tool call is logged
to the [audit ledger](./audit-ledger.md) but nothing is ever refused.

Source of record:
[`types/roe.py`](../../packages/decepticon-core/decepticon_core/types/roe.py)
(schema + evaluator) and
[`middleware/roe.py`](../../packages/decepticon/decepticon/middleware/roe.py)
(the gate).

## Enforcement modes

`mode` is one of three values; the default is `audit` for backward
compatibility (an engagement that never opts in keeps running).

| Mode | Behavior on a refused call |
|------|----------------------------|
| `audit` | Logged, allowed to proceed. **Default.** |
| `warn` | Logged; a `[ROE_WARN]` `ToolMessage` is prepended to the tool's output so the model sees it failed RoE, but the call still executes. |
| `enforce` | Logged; the call short-circuits with a `[ROE_REFUSED]` `ToolMessage`. No bytes leave the sandbox. |

The mode parses case-insensitively; an unrecognized string falls back to
`audit` rather than erroring.

## The `machine_enforcement` block

Fields and defaults (`MachineEnforcement`):

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `mode` | `audit` \| `warn` \| `enforce` | `audit` | Enforcement mode (above). |
| `in_scope` | list of scope rules | empty | Allowlist. When non-empty, a target must match one entry. |
| `out_of_scope` | list of scope rules | empty | Denylist. Takes precedence over `in_scope`. |
| `forbidden_destinations` | list of strings | empty | Extra denied hosts/IPs/CIDRs, merged with the default IMDS list. |
| `forbidden_command_patterns` | list of regex strings | empty | Commands matching any pattern are refused. |
| `allow_cloud_metadata` | bool | `false` | When `false`, the default cloud-metadata denylist is appended. |
| `max_concurrent_connections` | int or null | `null` | Carried in the schema; advisory. |
| `min_inter_request_delay_ms` | int | `0` | Carried in the schema; advisory. |

`from_dict` reads the block; each scope list is parsed by `_parse_rules`,
which accepts **either** a bare string (`"*.acme.com"`) **or** an object
(`{"target": "10.0.0.0/24", "type": "cidr"}`). Any other shape is
skipped.

### Scope rules and `resolved_kind`

A `ScopeRule` has a `pattern` and a `kind` (default `"auto"`). When the
kind is `"auto"`, `resolved_kind()` infers it from the pattern shape:

- parses as an IP network → `cidr`
- contains `*` or `?` → `domain-glob` (`*` matches one label, `?` matches
  one character)
- a bare IP literal → `ip`
- otherwise → `host` (literal, case-insensitive match)

### Cloud-metadata defaults

When `allow_cloud_metadata` is `false` (the default), five IMDS endpoints
are appended to the forbidden-destinations list:

```
169.254.169.254
fd00:ec2::254
metadata.google.internal
metadata.azure.com
100.100.100.200
```

Setting `allow_cloud_metadata: true` drops these defaults and leaves only
the operator's explicit `forbidden_destinations`.

## How a target is evaluated

`evaluate_target` runs in this precedence order (denylist wins):

1. **Forbidden destinations** (operator list + IMDS defaults) → refuse
   with `FORBIDDEN_DESTINATION`.
2. **Out-of-scope** entries → refuse with `OUT_OF_SCOPE`.
3. **In-scope** entries (only checked when `in_scope` is non-empty):
   - a match → allow with `IN_SCOPE`;
   - no match → refuse with `NOT_IN_SCOPE` (risk `medium`).
4. When `in_scope` is empty, an unmatched target is allowed by default.

### Trailing-dot normalization

A trailing dot is DNS-equivalent (`host.` resolves identically to
`host`). The matcher strips a trailing dot from **both** the rule pattern
and the target before comparing. Without this, the FQDN form
(`metadata.google.internal.`) or the IMDS IP written as
`169.254.169.254.` slipped past the forbidden-destination and
out-of-scope checks — a verified scope bypass that enabled
cloud-credential exfil in enforce mode.

## How a command is evaluated

`evaluate_command` runs each `forbidden_command_patterns` regex against
the literal command string with `re.search`. A match refuses with
`FORBIDDEN_COMMAND`. Patterns that fail to compile are skipped (the
evaluator never raises on a bad regex). Patterns are matched against the
command string, not the full tool-arguments dict.

## What gets gated

The middleware only evaluates tool calls whose name is in
`GATED_TOOL_NAMES` (`decepticon/middleware/roe.py`):

```
bash
bash_output
bash_kill
http_request
proxy_send_request
browser_action
```

Any other tool call passes through as an allow-default and is not
recorded. For a gated call, the middleware reads the engagement RoE from
`state["workspace_path"]/plan/roe.json` **per iteration**, so an
operator can hot-edit the RoE without restarting the run. It extracts the
intended targets from the command text (best-effort regex extraction over
~30 kill-chain tools), evaluates the command regexes first, then each
target, and records the decision regardless of mode.

If `workspace_path` is unset, the RoE fails open to a default
`MachineEnforcement()` — i.e. audit-only, no rules — and a malformed or
unreadable `roe.json` logs a warning and degrades the same way.

## Worked example — enforce mode

`<workspace>/plan/roe.json`:

```json
{
  "in_scope": ["*.acme.com", "10.10.0.0/24"],
  "out_of_scope": ["billing.acme.com"],
  "machine_enforcement": {
    "mode": "enforce",
    "in_scope": ["*.acme.com", "10.10.0.0/24"],
    "out_of_scope": ["billing.acme.com"],
    "forbidden_command_patterns": ["\\bhydra\\s.*-t\\s*[5-9]\\d+"]
  }
}
```

With this in place:

- `curl https://app.acme.com/` → **allow** (`IN_SCOPE`, matches
  `*.acme.com`).
- `curl https://billing.acme.com/` → **refuse** (`OUT_OF_SCOPE`); the
  out-of-scope denylist wins over the in-scope glob.
- `curl http://169.254.169.254/latest/meta-data/` → **refuse**
  (`FORBIDDEN_DESTINATION`); the IMDS IP is on the default denylist
  because `allow_cloud_metadata` defaults to `false`.
- `nmap 192.0.2.10` → **refuse** (`NOT_IN_SCOPE`); a target outside the
  allowlist, while `in_scope` is non-empty.
- `hydra -t 64 ssh://app.acme.com` → **refuse** (`FORBIDDEN_COMMAND`);
  the command matches the >50-thread Hydra pattern before any target is
  evaluated.

In each refusal the agent receives a `[ROE_REFUSED]` `ToolMessage`
explaining the block and is told to change target/technique rather than
re-issue the command. The PASS for `app.acme.com` and every refusal above
are written to the audit ledger.

## Two enforcement points

RoE enforcement is layered (defense-in-depth), and the names reflect it:

1. **RoE Guardrail Middleware** (parser, this document) — reads the
   literal command text, extracts the target hosts, and refuses early in
   `enforce` mode. This is a **fast-fail UX signal**: it tells the model
   before a wasted round-trip with a clear `[ROE_REFUSED]` reason. It is
   a guardrail, not the authoritative boundary — a determined agent can
   hide a target behind variable indirection (`H=evil; ping "$H"`),
   command substitution, encodings, or out-of-band DNS the parser never
   sees.
2. **RoE Egress Guardrail** (network) — compiles the *same*
   `machine_enforcement` block into a sandbox nftables connect-allowlist
   + DNS allowlist (`decepticon.middleware.egress` →
   `decepticon.sandbox_kernel.egress`). A packet to an out-of-scope host
   cannot leave the sandbox even when the parser missed the target. One
   scope definition, two enforcement points. **On by default** for
   `enforce` mode — no extra config; the operator can opt out with
   `DECEPTICON_EGRESS_DISABLE=1`. The sandbox discovers its own
   management subnet locally (from `/proc/net/route`, needing no `ip`
   binary) so a scope rule can never sever the agent↔management (Neo4j /
   daemon) link.

The parser's `[ROE_REFUSED]` short-circuit happens before the tool
handler runs, so in the common case no bytes leave the sandbox. The
guarantee that they *cannot* leave for an out-of-scope destination is
the egress layer's job.

## Limitations

- Target extraction in the parser layer is fail-closed but best-effort:
  any host/IP/CIDR-shaped command token is treated as a candidate target
  unless it is a known non-target, so it errs toward **more** targets
  than the command reaches (spurious target → refused, operator-
  overridable), never toward dropping a real one. The authoritative
  boundary for what a packet can actually reach is the egress layer
  above, not the command parse.
- `max_concurrent_connections` and `min_inter_request_delay_ms` are
  carried in the schema but are advisory — they are not throttled by this
  middleware.
- Enforcement covers the six `GATED_TOOL_NAMES` tools by default — the three
  bash tools plus `http_request`, `proxy_send_request`, and `browser_action`.
  A caller may pass a custom `gated_tools` set to the middleware to narrow or
  extend that list; any tool name outside the active set passes through as an
  allow-default and is not recorded.

## See also

- [Audit Ledger](./audit-ledger.md) — where every RoE decision is
  recorded and how to verify the chain.
- [Security Controls](./security-controls.md) — the full runtime-guard
  knob/default table.
- [HITL Approval](./hitl-approval.md) — the operator-approval gate that
  sits above RoE; operator approval cannot override an RoE refusal.
- [Threat Model](./decepticon-threat-model.md) — Decepticon's own attack
  surface.
- [Engagement Workflow](../engagement-workflow.md) — where `plan/roe.json`
  comes from.
