# Audit Ledger

> The HMAC-chained, append-only record of every RoE decision — the legal
> artifact for paid and regulated engagement out-briefs.

## TL;DR

Every RoE evaluation (PASS as well as REFUSE) emits one record to an
append-only JSON Lines ledger. Each record is hash-chained to its
predecessor and optionally bound to an operator-held HMAC secret, so
tampering with record N invalidates every record after N.

The ledger lives at `<workspace>/audit/roe-decisions.jsonl`. It is the
key artifact for "what the agent tried, what was approved, what was
blocked."

Source of record:
[`middleware/_audit_sink.py`](../../packages/decepticon/decepticon/middleware/_audit_sink.py)
(the sink + verifier) and
[`middleware/roe.py`](../../packages/decepticon/decepticon/middleware/roe.py)
(the writer).

## Record shape

The RoE middleware builds the per-decision fields; the sink stamps the
chain fields on append.

### Decision fields (written by the middleware)

| Field | Meaning |
|-------|---------|
| `ts` | Wall-clock timestamp (`time.time()`). |
| `engagement` | Engagement name from state, else `"unknown-engagement"`. |
| `objective_id` | Active objective id from state, else `""`. |
| `tool` | Gated tool name (`bash`, `bash_output`, `bash_kill`). |
| `decision` | `"allow"` or `"refuse"`. |
| `reason_code` | RoE outcome code (`OK`, `IN_SCOPE`, `OUT_OF_SCOPE`, `NOT_IN_SCOPE`, `FORBIDDEN_DESTINATION`, `FORBIDDEN_COMMAND`). |
| `reason_detail` | Human-readable explanation of the decision. |
| `risk` | `low` / `medium` / `high`. |
| `matched_targets` | List of the rule patterns or destinations that matched. |
| `mode` | The enforcement mode in effect (`audit` / `warn` / `enforce`). |
| `command_excerpt` | The command text, truncated to 512 characters. |

The audit write is wrapped so an audit-sink failure logs an error but
never breaks tool execution.

### Chain fields (stamped by the sink on append)

| Field | Meaning |
|-------|---------|
| `seq` | Monotonic per-ledger counter, starting at 1. |
| `prev_hash` | SHA-256 of the previous record's canonical encoding, or 64 zero hex digits (`"0" * 64`) for the first record. |
| `hash` | SHA-256 over this record's canonical fields **plus** `prev_hash`. |
| `hmac` | HMAC-SHA-256 of `hash` under the operator secret, or `""` when no key is set. |

Canonical encoding is `json.dumps` with `sort_keys=True` and tight
separators, so the hash is stable regardless of field insertion order.

## The HMAC binder

The `hmac` field binds the chain to an operator-held secret read from
`DECEPTICON_AUDIT_HMAC_KEY` (UTF-8 encoded). When the key is set, a party
that tampers with the file can recompute the hash chain but cannot forge
a valid `hmac` without the secret. When the key is unset, the `hmac`
field stays `""` and integrity rests only on the hash chain.

## Verification

`verify_ledger(path, hmac_key=None)` walks the file end-to-end and
returns a `VerifyResult`:

| Field | Meaning |
|-------|---------|
| `ok` | `True` if the whole ledger verifies. |
| `records_checked` | Number of records walked. |
| `first_bad_seq` | The sequence number of the first failing record, or `None`. |
| `reason` | Explanation of the first failure. |

It checks, per record: the `seq` is the expected next value (catches gaps
and duplicates), `prev_hash` matches the running chain head, the
recomputed `hash` matches the stored `hash`, and — when an `hmac_key` is
supplied — the `hmac` matches under constant-time comparison. A missing
file verifies as `ok` with zero records checked.

`iter_records(path)` yields decoded records without verifying integrity —
useful for reporting and analytics. It skips blank and malformed lines
silently.

## Configuration

| Knob | Effect |
|------|--------|
| `DECEPTICON_ROE_AUDIT_PATH` | Pins the ledger to a deterministic path. When unset, the default sink writes to `<workspace>/audit/roe-decisions.jsonl`; with no workspace yet, the sink is `None` (no-op). |
| `DECEPTICON_AUDIT_HMAC_KEY` | The HMAC secret. Set it to bind the chain to an operator-held key. |

## Limitations

- **Local file only** in this implementation. Remote shipping (S3,
  syslog, Loki over mTLS) is a follow-up; the local file is the primary
  integrity boundary.
- **Single writer per file.** The runtime guarantees this because the
  LangGraph orchestrator runs one event loop per engagement workspace;
  the append-then-fsync is atomic per record on POSIX append-only files,
  and on Windows for buffer sizes under 4096 bytes.
- The **`decepticon audit verify` CLI hook is a TODO** — call
  `verify_ledger` directly until it lands.

## See also

- [RoE Machine Enforcement](./roe-machine-enforcement.md) — what produces
  these records and the decision codes they carry.
- [Security Controls](./security-controls.md) — the runtime-guard
  knob/default table, including the audit env vars.
- [Threat Model](./decepticon-threat-model.md) — the ledger as the
  repudiation control for the sandbox and orchestrator assets.
