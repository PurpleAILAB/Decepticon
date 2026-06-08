# 0009. Migrate HITL to LangGraph-native `interrupt()` + explicit-policy sets

- **Status:** Proposed
- **Date:** 2026-06-06
- **Deciders:** @PurpleCHOIms
- **Related:** [ADR-0001](0001-record-architecture-decisions.md) (the
  "Docker-socket-exec sandbox → HTTP-daemon sandbox" pivot whose
  *outside-the-LLM-trust-boundary* principle this ADR extends to the
  HITL surface); [ADR-0006](0006-agent-driven-container-lifecycle.md)
  (also requires the canonical HITL surface for `ops_start` /
  `ops_stop` gating); PR #459 (Defender agent — closed pending this
  migration); existing `HumanInTheLoopMiddleware` (Decepticon
  `middleware/hitl.py`) and the file-backed `requests.jsonl` /
  `decisions.jsonl` web bridge

## Context

Decepticon's current HITL surface — `HITLApprovalMiddleware`
(`packages/decepticon/decepticon/middleware/hitl.py`) — predates a
clean read of the LangChain `HumanInTheLoopMiddleware` and the
LangGraph `interrupt()` / `Command(resume=...)` primitives and ended
up implementing its own pause/resume machinery on top of a file-backed
transport (`FileBackedApprovalTransport`, `InProcessApprovalTransport`).
The web dashboard (`clients/web/src/app/api/engagements/[id]/approvals/route.ts`)
reads `requests.jsonl` and writes `decisions.jsonl`; the middleware
blocks the agent thread inside `wait_for_decision` polling that file
every 250ms.

That shape works — it is currently in production behind
`DECEPTICON_HITL__ENABLED=true` — but on detailed review against the
official LangChain/LangGraph contracts and the threat model the
approval gate exists to defend, four primitives are misaligned:

1. **Regex `tool_pattern` matching is implicit.** `ApprovalPolicyRule`
   carries a `tool_pattern: str | None` field that is evaluated against
   the called tool name via `re.search` (`hitl.py:349`). The current
   `DEFAULT_HIGH_IMPACT_POLICY` includes
   `tool_pattern=r"^(sigma_to|yara_to)_"` and
   `tool_pattern=r"^(sliver_implant|sliver_generate|c2_deploy)"`. The
   policy is correct today but the primitive is fragile: a tool added
   under a name that happens to match the regex is silently gated; a
   tool added under a name that fails to match is silently ungated.
   "Which tools are gated by which rule?" is not a `grep`able question.
   LangChain's canonical `HumanInTheLoopMiddleware` keys explicitly per
   tool name (`interrupt_on={"send_email": {...}}`), which is the
   right shape for a security-critical surface.

2. **Custom transport bypasses LangGraph's native pause/resume.**
   `FileBackedApprovalTransport.submit` writes one JSONL line;
   `wait_for_decision` polls the decisions file. The agent thread is
   *blocking* the whole time the operator is deciding. LangGraph's
   `interrupt(value)` surfaces the value to the runtime and yields
   control to the caller (the LangGraph server / SDK consumer);
   `Command(resume=value)` resumes from the saved checkpoint. The
   `interrupt()` path is the contract every LangGraph hosting layer
   (`langgraph dev`, `langgraph up`, LangGraph Platform / Cloud) is
   already wired to surface through `__interrupt__` in the run result
   and through the SDK's `threads.getState` / `runs.create({command:
   {resume: ...}})`. Decepticon currently ships its own transport
   layer that re-implements the surfacing.

3. **No checkpointer means no time-travel, no replay, no durable
   resume.** LangGraph HITL requires a checkpointer
   (`InMemorySaver` / `PostgresSaver`) so the paused state survives
   process restarts, so `get_state_history` can list the points where
   the agent paused for review, and so an operator can fork a decision
   ("what would have happened if I had approved instead of denied?").
   Decepticon's current HITL middleware works without one because it
   blocks the thread, but the price is that none of those native
   capabilities are reachable. The LangGraph Platform runtime already
   provisions a `PostgresSaver` automatically; *not* using it leaves
   that infrastructure stranded.

4. **MITRE-technique gating is correct in spirit but coupled to a
   regex policy data model.** `ApprovalPolicyRule.technique_tag`
   (e.g. `T1003` for Credential Dumping) is the right primitive — it
   gates by the semantic nature of the operation, not by the tool's
   name, so renaming a tool cannot bypass the gate. But it lives
   alongside the regex `tool_pattern` field in the same dataclass and
   inherits the implicit-matching idiom (`_match_rule` does
   `rule.technique_tag == technique` AND `re.search(rule.tool_pattern,
   tool_name)` against the same rule list).

Plus a fifth issue, exposed by PR #459 review: the
`DECEPTICON_HITL__ENABLED` env flag silently disables the slot
(`middleware_slots.py:_make_hitl` returns `None`) so the role
declares the slot but the gate isn't wired. Agent prompts that
advertise *"this will pause for HITL approval"* are factually wrong on
a default install. That's a configuration bug, but it surfaces because
the gating contract is entirely *inside* the agent process; the
LangGraph runtime does not enforce it.

The threat model this gate exists for has not changed: an
LLM-driven write to a customer's production SIEM / EDR, a C2 implant
deployment, or a credential-dumping operation must require a human
decision. The fix is to use the LangGraph-native pause/resume
primitive, with an explicit policy data model that audit and `grep`
can resolve.

## Decision

We migrate `HITLApprovalMiddleware` to a LangGraph-native shape with
explicit, audit-friendly policy primitives. Four sub-decisions:

1. **Adopt `interrupt(value)` + `Command(resume=value)` as the
   pause/resume mechanism.** `HITLApprovalMiddleware.wrap_tool_call`
   builds the approval payload, calls `interrupt(payload)`, and uses
   the returned decision dict. Removes
   `FileBackedApprovalTransport` and `InProcessApprovalTransport`. The
   agent thread no longer blocks: control yields to the LangGraph
   runtime, the run result carries the pending approval in
   `__interrupt__`, and the caller (web dashboard / SDK consumer)
   reads it from `threads.getState`. Resume is a single
   `runs.create({command: {resume: <decision>}})` call from the
   dashboard. Decision payload shape mirrors LangChain canonical:

   ```python
   {
     "action": "approve" | "deny" | "edit",
     "edited_args": {...} if action == "edit" else None,
     "operator_note": str,
   }
   ```

2. **Replace regex `tool_pattern` with an explicit
   `frozenset[str]`.** New policy data model:

   ```python
   @dataclass(frozen=True)
   class ApprovalPolicy:
       tools: frozenset[str] = frozenset()       # explicit tool names
       techniques: frozenset[str] = frozenset()  # MITRE technique tags
       timeout_seconds: float = 300.0
       default_on_timeout: Literal["allow", "deny"] = "deny"
       reason: str = ""
   ```

   `DEFAULT_HIGH_IMPACT_POLICY` is rewritten with every gated tool
   listed by name; the regex idiom disappears from the codebase. A
   `grep -F sigma_to_splunk_savedsearch policy.py` resolves to the
   exact policy line that gates it. Adding a new push tool requires
   adding it to the set — that is the intended UX, the bar for new
   gated tools is *explicit consent at policy definition time*.

   Tool-name and technique-tag matching are independent paths in
   `wrap_tool_call`: either match triggers the interrupt. Both are
   explicit sets; neither is a regex.

3. **Compile every agent graph with a checkpointer; thread_id flows
   from the engagement.** The standard agent factories accept
   `checkpointer=None` and pass it through to `create_agent`; the
   LangGraph server runtime (Platform / Cloud / `langgraph dev` /
   `langgraph up`) supplies a `PostgresSaver` automatically.
   Engagement-level callers thread `thread_id` through `config.configurable`
   from the existing `engagement_name` slug; thread IDs are stable
   per-engagement so `get_state_history` lists every paused approval
   for that engagement. Local pytest paths use `InMemorySaver`.
   `langgraph.json` already declares `"multitask_strategy":
   "interrupt"`, which is the correct setting for the new
   pause/resume shape (a follow-on `invoke` cancels the in-flight run
   and pre-empts the pending interrupt; an operator decision goes
   through `Command(resume=...)` instead).

4. **Web dashboard migrates from file polling to the LangGraph SDK
   wire format.** `clients/web/src/app/api/engagements/[id]/approvals/route.ts`
   drops its `requests.jsonl` / `decisions.jsonl` reader/writer and
   takes a dependency on `@langchain/langgraph-sdk`:

   ```typescript
   // GET — list pending approvals
   const state = await client.threads.getState({ thread_id });
   return Response.json({ pending: state.values?.__interrupt__ ?? [] });

   // POST — submit operator decision
   await client.runs.create(thread_id, {
     command: { resume: { action, edited_args, operator_note } },
   });
   ```

   Old wire format (`requests.jsonl` / `decisions.jsonl`) is
   removed in the same release; there is no compatibility shim
   because the format was internal and not part of the public
   contract.

### External validation

The migration target matches four independently authoritative
sources:

- **LangChain `HumanInTheLoopMiddleware`** [1] — keys explicitly per
  tool name (`interrupt_on={"send_email": {"allowed_decisions":
  [...]}}`), supports `approve` / `edit` / `reject` decisions, requires
  a checkpointer, resumes via `Command(resume={"decisions": [...]})`.
  Sub-decision #1 + #2 + #3 align with this canonical pattern.
- **LangGraph `interrupt()` + `Command(resume=...)`** [2] — surfaces
  the interrupt payload via the LangGraph runtime, persists state via
  the checkpointer, supports time-travel through `get_state_history`,
  cleanly composes with parallel branches via interrupt-id-keyed resume
  maps. Sub-decision #1 + #3 reflect this contract directly.
- **NIST SP 800-190 §4.3.1** [3] — *"orchestrators should use a least
  privilege access model in which users are only granted the ability
  to perform the specific actions on the specific hosts, containers,
  and images their job roles require"*. The `(workload, lifecycle_op)`
  / `(tool_name)` / `(technique_tag)` tuple shape adopted in
  sub-decision #2 is the canonical instance of this scoping
  prescription; the regex `tool_pattern` is not, because "which
  specific tools are gated" is implicit rather than explicit in the
  policy text.
- **OWASP LLM06:2025 Excessive Agency** [4] — *"Avoid the use of
  open-ended extensions where possible (e.g., run a shell command,
  fetch a URL, etc.) and use extensions with more granular
  functionality"*. Explicit per-tool gating with an explicit allowlist
  is the granular form; regex matching against tool names is the
  open-ended form (the regex defines a *family* of tools, including
  unknown future names, so the gate is implicit on additions).

[1] https://docs.langchain.com/oss/python/integrations/middleware/human_in_the_loop_middleware
[2] https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
[3] https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-190.pdf
[4] https://genai.owasp.org/llmrisk/llm062025-excessive-agency/

### CLAUDE.md / docs updates

`docs/security/hitl-approval.md` (added in PR #488) is rewritten to
document the new shape:

- Pause/resume primitive: `interrupt()` + `Command(resume=...)`
- Policy primitives: explicit `tools: frozenset[str]` +
  `techniques: frozenset[str]`; no regex
- Web wire format: LangGraph SDK (`threads.getState`,
  `runs.create({command: {resume: ...}})`)
- Checkpointer requirement: `PostgresSaver` on the server,
  `InMemorySaver` in pytest

The previous version's references to `requests.jsonl` /
`decisions.jsonl` / `FileBackedApprovalTransport` are removed.

## Consequences

- **Easier**
  - LangGraph time-travel and replay become reachable for paused
    approvals — operators can fork on a hypothetical "what if I had
    edited the rule before approving" without re-running the
    engagement.
  - The custom transport layer goes away (~150 lines removed). The
    middleware becomes ~150 lines instead of ~500.
  - `grep <tool_name> policy.py` resolves to the exact policy line
    that gates it. Audit and onboarding both improve.
  - Adding a new gated tool is an *explicit* code change to the
    policy set — implicit silent-gating bugs (a new tool name that
    happens to match `^(sigma_to|yara_to)_`) cannot occur.
  - LangChain ecosystem alignment: third-party tools and middleware
    that assume the canonical `interrupt_on={...}` shape work without
    Decepticon-specific adapters.
- **Harder**
  - The web dashboard takes a runtime dependency on
    `@langchain/langgraph-sdk` and the LangGraph server URL.
    Operationally this is the same network reach the dashboard
    already has (LangGraph and the dashboard are co-deployed); it's
    new code, not a new network hop.
  - All agent graphs need to compile with a checkpointer. In server
    deployments (`langgraph dev` / `langgraph up`) this happens
    automatically; in library / pytest paths the test fixtures must
    pass `compile(checkpointer=InMemorySaver())`.
  - The `thread_id` mapping (engagement slug ↔ LangGraph thread)
    becomes load-bearing. The mapping is straightforward (one thread
    per engagement) but it has to be plumbed consistently.
- **Given up**
  - The file-backed transport's audit trail (`requests.jsonl` /
    `decisions.jsonl`). Replaced by the LangGraph checkpoint history,
    which carries the same information plus replay capability.
  - Backwards compatibility with the old wire format. Migration is
    atomic: backend and frontend cut over together in the same
    release.
- **Migration timeline**
  - **Sprint 1**: this ADR.
  - **Sprint 2 (PR A — substrate)**: rewrite `middleware/hitl.py`
    against the canonical primitives; update
    `agents/middleware_slots.py:_make_hitl`; rewrite
    `tests/unit/middleware/test_hitl.py` against the
    `interrupt()`-mocking pattern; migrate
    `clients/web/src/app/api/engagements/[id]/approvals/route.ts` to
    the LangGraph SDK; bump `@langchain/langgraph-sdk` in the web
    workspace; ensure all agent factories thread `checkpointer`
    consistently. Rewrite `docs/security/hitl-approval.md`.
  - **Sprint 3 (PR B — Defender agent re-do)**: ship the Defender
    agent under the new substrate (PR #459 closed and is reopened on
    the canonical substrate); move `DefenseAction` upsert from the
    LLM prompt into the `sigma_to_*` / `yara_to_*` push tools so the
    rule_id is the single source of truth; tighten the test from
    *"the tool name matches a regex in the policy"* to *"the tool name
    is in the policy's `tools` set"*.
  - **Sprint 4 (Blue Cell stack remainder)**: PR #460 (Defense Brief)
    and PR #461 (adaptive feedback) land on the new substrate.
  - **Sprint 5 (PR C — policy mop-up)**: remaining custom rules
    (`sliver_implant` / `sliver_generate` / `c2_deploy` / informational
    `bash` audit) move from their regex forms into the explicit
    `tools` set; the `tool_pattern` field is removed from
    `ApprovalPolicy` entirely.

## Alternatives considered

- **(M1) Keep the current custom middleware + regex policy; add
  startup warnings when `HITL_APPROVAL` slot is declared but
  `DECEPTICON_HITL__ENABLED` is unset.** Rejected. Addresses the
  fifth issue (advertising mismatch) but leaves the four
  architectural issues (regex, custom transport, no checkpointer,
  data-model coupling) intact. Also keeps Decepticon out of the
  LangChain/LangGraph ecosystem.

- **(M2) Replace the regex with explicit tool-name sets but keep the
  custom file-backed transport.** Rejected. Half-migration that
  improves audit but leaves the LangGraph-native pause/resume
  primitive unused, leaves time-travel unreachable, and keeps the
  blocking-thread transport. The web dashboard work would have to be
  redone twice — once to consume the new policy shape, then again to
  switch to the SDK. Atomic migration is cheaper.

- **(M3) Keep the file-backed transport for the web dashboard, but
  emit `interrupt()` on the LangGraph side and bridge the two with a
  long-running poller that translates between file format and SDK
  payloads.** Rejected. Adds a third moving part (the bridge) without
  removing either of the two it sits between. Strictly more code than
  the canonical migration, and the bridge becomes a second source of
  truth for which approvals are pending.

- **(M4) Keep the custom transport and migrate the *only the policy
  data model* (regex → explicit sets), deferring the pause/resume
  refactor indefinitely.** Rejected. The pause/resume mechanism is
  the load-bearing piece — the checkpointer requirement, the
  time-travel capability, the LangChain ecosystem alignment all flow
  from `interrupt()` adoption. Deferring it leaves Decepticon at risk
  of further divergence as LangChain canonical evolves.

- **(M5) Move HITL out of the agent process entirely — implement it
  as a separate "approver" agent that the orchestrator delegates to
  via `task()`.** Rejected. Conceptually appealing (HITL as a
  first-class agent in the multi-agent system) but introduces a
  second prompt-injection surface (the approver agent's prompt is now
  also LLM-driven), violates the separation of trust planes (operator
  decisions should not flow through any LLM), and the LangGraph
  primitives already give the right shape without this layering.
