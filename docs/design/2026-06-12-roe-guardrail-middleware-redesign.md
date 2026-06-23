# RoE Guardrail Middleware — root cause + redesign

> Status: **implemented** (Layer 1 + Layer 2 + rename landed)
> Date: 2026-06-12
>
> Implementation notes (2026-06-12):
> - **Layer 1** (parser fail-closed) shipped: `_extract_token_hosts` in
>   [`_command_targets.py`](../../packages/decepticon/decepticon/middleware/_command_targets.py)
>   runs as the `not matched_tool` fallback; the bare-hostname matrix
>   below is covered by `test_command_targets_scope_bypass.py`.
> - **Rename** shipped: `RoEEnforcementMiddleware` →
>   `RoEGuardrailMiddleware`, slot `ROE_ENFORCEMENT` → `ROE_GUARDRAIL`
>   (`roe-guardrail`), factory `_make_roe_guardrail`. Old names kept as
>   compat aliases (class + enum alias) until 2.0.0.
> - **Layer 2** (egress) shipped as the authoritative boundary:
>   `middleware/egress.py` (`compile_egress_policy`) +
>   `sandbox_kernel/egress.py` (renderer + applier) + `/provision_egress`
>   endpoint + `HTTPSandbox.provision_egress` + a once-per-workspace hook
>   in the guardrail middleware. **On by default** for `enforce` mode
>   (opt out with `DECEPTICON_EGRESS_DISABLE`); in-sandbox nftables
>   (NET_ADMIN already granted), management subnet discovered sandbox-side
>   from `/proc/net/route` (the OSS sandbox image ships no `ip` binary) so
>   a scope rule can't sever the agent↔management link.
> - **Live-verified** in a Kali sandbox container on `sandbox-net`:
>   out-of-scope `ping 8.8.8.8` dropped by nftables, in-scope `1.1.1.1`
>   and the management gateway both still reachable; the parser layer
>   refuses out-of-scope `ping`/`nc`/`traceroute` with `[ROE_REFUSED]`
>   before the handler runs. The live run also caught + fixed the
>   missing-`ip`-binary management-discovery gap.
> Author note: discovered while live-verifying a downstream `recon`-derived
> subagent, which reuses the OSS `recon` role whole —
> including the `ROE_ENFORCEMENT` slot — as its scope backstop.

## TL;DR

The RoE middleware's scope gate decides whether a `bash` command is
in-scope by **extracting target hosts/IPs from the command string with
regexes**, then evaluating each extracted target against the allowlist /
denylist. That extraction depends on a **hardcoded verb allowlist**
(`_HOSTNAME_AFTER_VERB_RE` in
[`_command_targets.py`](../../packages/decepticon/decepticon/middleware/_command_targets.py)).
Any network tool **not** on that list, invoked with a **bare hostname**,
extracts **zero targets** — so the scope check has nothing to evaluate
and the command is **allowed by default**.

This is a **fail-open** scope bypass. It directly contradicts the
invariant stated in
[`roe-machine-enforcement.md`](../security/roe-machine-enforcement.md#limitations):

> Target extraction is regex-based and best-effort; it errs toward **more
> targets** than the command would actually reach (false-positive-safe),
> not fewer.

For bare-hostname commands on unrecognized verbs the opposite is true: it
errs toward **fewer** targets (a false **negative**), which is the unsafe
direction for an allowlist enforcer.

The fix is **not** "add more verbs" — that is whack-a-mole and string
parsing is the wrong layer for a hard guarantee. The fix is two layers:

1. **Parser (tactical):** invert the default to **fail-closed** — every
   host/IP-shaped token is a candidate target unless it is a known
   non-target. Removes the verb-allowlist dependency.
2. **Egress (strategic, authoritative):** enforce scope at the **network
   boundary** of the sandbox (DNS allowlist + nftables / egress proxy),
   so the packet cannot leave even if the parser misses the target. The
   parser becomes a fast-fail UX layer; the network layer is the real
   gate.

As part of (2), rename the component from **RoE *Enforcement*
Middleware** to **RoE *Guardrail* Middleware** to reflect a
defense-in-depth posture (advisory parse + authoritative egress) rather
than a single string-parse gate that the name currently over-promises.

## How target extraction works today

`extract_targets(command)` returns the union of three things:

1. **Tool-specific extractors** (`_TOOL_EXTRACTORS`) — only when the
   command's leading token is `nmap | masscan | rustscan | naabu | ssh |
   scp | sftp | impacket-* | GetUserSPNs | …`. These shlex-tokenize and
   precisely skip option *values* (`-oA out.txt`, `-i key.pem`).
2. **IP / CIDR literals** — any dotted-quad / `x.x.x.x/yy` anywhere in
   the string (`_IP_RE`, `_CIDR_RE`).
3. **Generic host scrape** (`_extract_generic`):
   - hosts after `scheme://` (`_URL_AUTHORITY_RE`), and
   - **hosts immediately after a hardcoded verb** (`_HOSTNAME_AFTER_VERB_RE`:
     `curl | wget | httpx | nmap | dig | host | nuclei | …`, ~30 verbs).

The gap is in (3): a hostname is only recognized as a target if it
follows `://` **or** one of the allowlisted verbs. A bare hostname
argument to any other command is invisible to the extractor.

## Evidence (measured 2026-06-12)

Seeded a realistic HackerOne scope through the **production path** —
a downstream plugin's real `_machine_enforcement_from_scopes` adapter + the sidecar
`{target,type}` serializer → `plan/roe.json` (`mode: enforce`) — and
drove the real `RoEEnforcementMiddleware.wrap_tool_call`. The `handler`
(sandbox stand-in) was instrumented to prove it never runs on a refusal.

Out-of-scope target, every command **emitted by the agent**:

| Command | `extract_targets` | RoE result |
|---|---|---|
| `nmap -sV scanme.nmap.org` | `{scanme.nmap.org}` | **REFUSE** ✓ |
| `curl https://evil-oos.example/` | `{evil-oos.example}` | **REFUSE** ✓ |
| `dig evil-oos.example` / `host …` / `nslookup …` | `{evil-oos.example}` | **REFUSE** ✓ |
| any command with an **IP literal** (`ping 8.8.8.8`) | `{8.8.8.8}` | **REFUSE** ✓ |
| `ping -c 3 evil-oos.example` | **`{}`** | **ALLOW** ✗ |
| `traceroute evil-oos.example` | **`{}`** | **ALLOW** ✗ |
| `mtr evil-oos.example` | **`{}`** | **ALLOW** ✗ |
| `nc -vz evil-oos.example 443` | **`{}`** | **ALLOW** ✗ |
| `ncat evil-oos.example 80` | **`{}`** | **ALLOW** ✗ |
| `telnet evil-oos.example 22` | **`{}`** | **ALLOW** ✗ |
| `openssl s_client -connect evil-oos.example:443` | **`{}`** | **ALLOW** ✗ |
| `hping3 evil-oos.example` / `fping evil-oos.example` | **`{}`** | **ALLOW** ✗ |

So the IP form of `ping`/`nc`/etc. is blocked (IP regex), but the
**hostname** form escapes. The boundary is exactly "is the verb on the
allowlist," which is the brittle thing.

The rest of the gate is sound: enforce-mode REFUSE short-circuits before
the handler, in-scope (host / wildcard / CIDR) passes, and every PASS /
REFUSE lands in the audit ledger. The bug is purely in *what counts as a
target*.

## Why string parsing is the wrong layer

Even a perfect verb list does not close this. The extractor parses
*intent* from literal command text, which a determined (or simply
capable) agent defeats trivially:

- variable indirection — `H=evil.example; ping -c1 "$H"`
- command substitution — `ping "$(cat /tmp/h)"`, `curl "$(gethost)"`
- encodings — base64 / hex / packed-integer IPs (some, not all, are
  normalized today by `_canon_host`)
- DNS indirection — resolving out-of-band, then connecting by IP that
  was never in the command text

The middleware docstring promises *"No bytes leave the sandbox"* in
enforce mode. Today that guarantee is only as strong as a regex over the
command string. That is acceptable for an **advisory / fast-fail** signal
to the model, but it cannot be the authoritative boundary.

## Proposed redesign

### Layer 1 — parser: fail-closed, verb-agnostic (tactical, contained)

Invert the default. Instead of "extract a host only after a known verb,"
treat **every shell token that validates as a host / IP / CIDR** as a
candidate target. Keep the precise tool-specific extractors for the tools
that have them (so the engineered `-oA out.txt` / `-i key.pem`
false-positive exclusions are preserved); add the greedy token scan as a
**fallback for commands that matched no tool-specific extractor** — which
is exactly where the fail-open gap lives.

Sketch:

```python
def _extract_token_hosts(command: str) -> set[str]:
    """Verb-agnostic fail-closed scrape: any host/IP-shaped token is a
    target unless it is a known non-target (flag, path, file extension)."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()        # malformed → still surface hosts
    found: set[str] = set()
    for tok in tokens:
        if not tok or tok.startswith("-"):
            continue
        if "@" in tok:                  # strip userinfo: user@host → host
            tok = tok.rsplit("@", 1)[1]
        pieces = tok.split(":") if (":" in tok and not _looks_ipv6(tok)) else [tok]
        for p in pieces:
            c = _canon_host(p)
            if c and _is_valid_target(c):
                found.add(c)
    return found

# in extract_targets(): run only when no _TOOL_EXTRACTORS matched
if not matched_tool:
    targets.update(_extract_token_hosts(command))
```

Properties:

- **Closes the whole class** of "network tool not on the verb list" —
  ping / nc / telnet / traceroute / custom `./exploit host` all now yield
  their target.
- **Fail-closed:** the failure mode flips from "missed target → allowed"
  to "spurious target → refused (operator-overridable)," which matches
  the allowlist posture the docs already claim.
- **No precision regression for known tools:** nmap / ssh / impacket keep
  their exact extractors (gated on `not matched_tool`), so existing
  exclusion tests stay green.
- Existing `_is_valid_target` already rejects flags, absolute paths, and
  `_NON_TARGET_EXTENSIONS`, so most non-target tokens are filtered.

Residual cost: more false positives on host-shaped non-targets in
unrecognized commands (e.g. `git clone git@github.com:…` surfaces
`github.com` — which is in fact a real connect target). Acceptable and
operator-overridable; tighten `_is_valid_target` (reject all-numeric
non-IP labels, version strings) if noise shows up in practice.

This layer is a contained OSS change with pure-logic unit tests
(extend `tests/unit/middleware/test_command_targets_scope_bypass.py`):
add the bare-hostname matrix above as failing cases, then implement.

### Layer 2 — egress: authoritative network boundary (strategic)

Enforce scope where it cannot be parsed around: the sandbox's network
egress.

- **DNS allowlist** — the sandbox resolver only answers for in-scope
  hostnames / wildcards; everything else `NXDOMAIN`.
- **Connect allowlist** — nftables (or an egress proxy) permits outbound
  only to in-scope IPs / CIDRs, denies the rest, and denies the
  cloud-metadata / sensitive ranges already in
  `effective_forbidden_destinations()`.
- Source of truth stays `plan/roe.json:machine_enforcement` — the same
  `in_scope` / `out_of_scope` rules compile into firewall/DNS config when
  the engagement workspace is provisioned, so there is one scope
  definition, two enforcement points.

With this, the parser stays as the **fast-fail UX layer** (tells the
model early, before a wasted round-trip, with a clear `[ROE_REFUSED]`
reason), and the network layer is the boundary the threat model can
actually lean on.

### Rename — "RoE Guardrail Middleware"

Today the class is `RoEEnforcementMiddleware` (slot
`MiddlewareSlot.ROE_ENFORCEMENT`). Once enforcement is genuinely layered,
the parser-in-the-middleware is one guardrail among several, not *the*
enforcement. Rename to **RoE Guardrail Middleware** to set the right
expectation (defense-in-depth, advisory + authoritative) and avoid the
current name implying the string parse is a hard gate.

Touch points for the rename (do it with the egress work, not before):
class name, `MiddlewareSlot.ROE_ENFORCEMENT` →
`ROE_GUARDRAIL` (keep `SAFETY_CRITICAL_SLOTS` membership), the
`_make_roe_enforcement` factory, and the docs below.

## Affected code / docs

| Path | Change |
|---|---|
| `packages/decepticon/decepticon/middleware/_command_targets.py` | Layer 1 — add `_extract_token_hosts`, wire as `not matched_tool` fallback in `extract_targets`. |
| `packages/decepticon/tests/unit/middleware/test_command_targets_scope_bypass.py` | Add the bare-hostname fail-open matrix; assert fail-closed. |
| `packages/decepticon/decepticon/middleware/roe.py` | Layer 2 — class rename; integrate egress provisioning hook. |
| `packages/decepticon-core/decepticon_core/contracts/slots.py` | `ROE_ENFORCEMENT` → `ROE_GUARDRAIL` (keep safety-critical). |
| sandbox backend / workspace provisioning | Layer 2 — compile `machine_enforcement` → DNS + nftables/proxy config. |
| `docs/security/roe-machine-enforcement.md` | Correct the "false-positive-safe" claim; document the two enforcement points. |

## Sequencing

1. **Layer 1 first** — independent, low-risk, unit-tested; immediately
   removes the obvious fail-open class. Ships via the normal OSS release,
   downstream plugins pick it up on the next version pin bump.
2. **Layer 2 + rename** — larger, sandbox-infra; the rename rides along
   so the name changes exactly when the posture does.

## Open questions

- Parser false-positive tolerance: is auto-refuse-then-override
  acceptable, or do we want a `WARN`-on-ambiguous-token middle path?
- Egress mechanism: in-sandbox nftables vs. a sidecar egress proxy vs.
  DNS-allowlist-only — what fits the current sandbox backend?
- Dynamic scope: wildcard `*.acme.com` → how does the DNS/connect
  allowlist handle hosts discovered mid-engagement (recon expands scope)?
- Do we keep the parser's `forbidden_command_patterns` (e.g. Hydra
  thread caps) in the middleware regardless, since those are about
  *technique*, not *destination*, and have no egress equivalent? (Yes —
  technique limits stay in the parser layer.)

## Reproducer

The measured matrix above came from driving the real middleware with a
downstream-serialized `plan/roe.json`. To re-derive: build a
`MachineEnforcement(mode=enforce, in_scope=…)`, write it to
`<ws>/plan/roe.json` in the `{target,type}` rule shape, then call
`RoEEnforcementMiddleware().wrap_tool_call(request, handler)` with a
`bash` request per command and assert `handler` did not run for the
out-of-scope cases. `extract_targets(cmd)` alone reproduces the
empty-set rows without any middleware.
