# The 100% Quality Bar

> **If you cannot meet this bar, close the PR.** Shipping at 80% is
> shipping a bug we agreed to write. There is no AI-slop tax: a
> contribution drafted by a tool is held to exactly the same standard
> as one hand-written by a senior engineer, because merging it implies
> the same trust.

This document is the closed contract. The [Karpathy Four](#the-karpathy-four)
are the philosophy; the rules below are the operational consequence.
[ADR-0004](adr/0004-zero-ai-slop-policy.md) records why this bar exists.

To change the bar, open an ADR. No branch rule enforces that — see
[ADR-0012](adr/0012-retire-codeowners-merge-gate.md) — so it is on you.

---

## The Karpathy Four

These four principles are the default behavioral contract for **every**
Decepticon contribution, trivial or complex. They override any habit
toward speed, breadth, or overcomplication. Bias: **caution over speed**.

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- No new dependencies without a clear, stated need.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Don't rename variables, move files, or change comments unless required.
- If you notice unrelated dead code or bugs, **mention them** —
  don't delete or fix them opportunistically.
- Every changed line must trace directly to the stated request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

| Instead of...    | Transform to...                                            |
|------------------|------------------------------------------------------------|
| "Add validation" | "Write tests for invalid inputs, then make them pass"       |
| "Fix the bug"    | "Write a test that reproduces it, then make it pass"        |
| "Refactor X"     | "Ensure tests pass before and after"                        |

Before declaring a task complete, **run the verification you said you
would**. If you cannot verify, say so explicitly — never claim done
without evidence.

---

## Hard limits

A PR that exceeds these without explicit owner approval (`large-diff-approved`
label, applied by `@PurpleCHOIms`) will be closed or split. The budget is
on **runtime code** — `docs/**`, `tests/**`, `.github/**`, `.semgrep/**`,
and pure boilerplate (license headers, generated lockfiles) do **not**
count.

| Dimension                       | Default cap                          |
|---------------------------------|--------------------------------------|
| Runtime-code lines changed      | ≤ 400                                |
| Files touched                   | ≤ 10                                 |
| Logical concerns in one PR      | 1                                    |
| New top-level dependencies      | 0 (justify in PR body if proposing)  |
| New public API surface          | 0 (lift via ADR + plugin-contract review) |
| Cyclomatic complexity per func  | ≤ 10                                 |
| Function length                 | ≤ 50 lines (anything larger needs a reason in the PR body) |

If you cannot fit your work under the cap, **the work is two PRs**.
Split it. Land each piece independently, behind a flag if needed.


## Wired end-to-end, locally verified — no exceptions

**"Compiles" is not "works." "Tests pass" is not "wired." "CI is
green" is not "I ran it."** Before you open the PR, every code path
you touched has been **executed on your machine** at least once and
produced the behavior you claim. There is no exception for "small
changes," "obvious refactors," "docs-only" touching runtime code, or
"the test suite covers it." If you did not run it, you do not know.

### What "wired" means concretely

1. **You executed the new or changed code path on your machine.** Not
   imported. Not unit-tested in isolation. Actually called, in the
   actual runtime, against the actual surrounding system. If your
   change is in `packages/decepticon/decepticon/agents/`, you ran an
   engagement that exercised the agent. If it is a CLI command, you
   ran the command. If it is an HTTP route, you hit the route. If it
   is a skill, you triggered the skill from an agent that loads it.
2. **You followed the change through every layer it crosses.** A new
   config flag means: you set it, watched the loader pick it up,
   watched the consumer behave differently, and watched the *opposite*
   value still work. A new function signature means: you ran every
   updated caller, not just the one in the unit test. A new
   `docker-compose.yml` field means: you ran `make dev` (or `docker
   compose up`) and watched the stack come healthy with your change.
3. **You verified the failure mode, not just the happy path.** Pass
   bad input. Pass `None`. Pull the network. Confirm the failure
   surfaces — not silently swallowed, not turned into a `None`
   downstream. If you cannot describe what happens on failure, you
   have not tested the change.
4. **You ran the integration the change is part of.** If your PR
   changes an OPPLAN tool, you ran the orchestrator and watched it
   call the tool. If it changes a middleware, you ran an agent through
   the middleware stack. Unit tests on the middleware in isolation
   are necessary, not sufficient.
5. **You ran `make smoke` (or the matching lane) for any change that
   crosses the stack.** "CI will catch it" is not local verification.
   CI is a backstop. A green CI run on a PR you have not exercised
   locally is still rejected.
6. **If you genuinely cannot run something locally** (no GPU, no AWS
   account, the target requires a paid Sliver license, the C2 traffic
   needs an external responder, etc.) — say so **explicitly** in the
   PR body, name what you did instead (a focused mock, a stand-in
   target, a recorded transcript), and label the unverified surface so
   the reviewer knows where to look. Honest "I could not exercise X
   end-to-end because Y; I verified Z instead" is acceptable.
   Pretending you ran something you did not is not.

### What "wired" forbids

- Adding a new code path without a runtime exercise of it — even if a
  unit test covers the function in isolation.
- Adding a new config flag / env var / option without flipping it on
  your machine and watching the behavior change.
- Changing a public function signature without grep-confirming (or
  LSP-confirming) every caller is updated and exercised.
- Adding or removing a dependency without importing it under the
  actual runtime path and watching it load.
- Adding a new CLI command, HTTP route, agent prompt, or skill
  without invoking it once.
- Touching `docker-compose.yml`, `containers/*.Dockerfile`, or
  `config/litellm.yaml` without bringing the stack up locally and
  watching it pass healthchecks.
- Saying "should work," "should be fine," "I think this is right," or
  "this is straightforward" in a PR body, a commit message, or a
  review comment. If it is true, prove it. If you cannot, do not
  claim it.
- "Verified in CI only" without an explicit reason you could not run
  it locally. CI is necessary, not sufficient.

### What "wired" requires in the PR body

Every PR has a one-paragraph **End-to-end verification statement**
naming the exact commands you ran and the exact behavior you
observed. Examples that meet the bar:

> Brought the stack up with `make dev`, ran `make cli`, executed an
> engagement with `target=10.0.2.4` and `profile=AUTOBANK`. The new
> `c2_tier=short_haul` field on `obj-002` propagated through to the
> Sliver implant generation (verified via `sliver-client implants` —
> output attached). Confirmed `c2_tier=long_haul` produces a DNS
> implant on the same target. `make smoke` healthy on a clean
> volume.

> Ran `pytest packages/decepticon/tests/unit/middleware/test_safe_command.py::test_rejects_out_of_scope_host -x`
> twice: once on the parent commit (failed as expected: the new
> CIDR-overlap check did not exist), once on this branch (passed).
> Also ran `make ci-lint` and the full `pytest tests/`. Did **not**
> run `make smoke` because no compose change; declaring the gap so
> the reviewer knows.

Examples that **do not** meet the bar:

> Tested locally.

> All tests pass.

> Should work.

The bar is on the *evidence*, not the *claim*.

---

## Banned patterns — PR closed on sight

Each pattern is closed without further review when found. Several are
already enforced by `.semgrep/decepticon-rules.yml`; the rest are
enforced by the maintainer reviewing the diff. There is no "I didn't
know" exception once this document exists.

### Error handling

```python
# BANNED
try:
    risky()
except Exception:
    pass

# BANNED — bare except
try:
    risky()
except:
    pass

# BANNED — swallow then continue
try:
    result = call_llm()
except Exception:
    result = None  # silent failure on a load-bearing call

# REQUIRED
try:
    result = call_llm()
except RateLimitError as exc:
    raise OPPLANExecutionFailed("LLM rate-limited") from exc
```

The exception is what you say it is. Catch the **specific** class, do
something **meaningful**, and `raise ... from exc` so the trace is
preserved.

### Type-safety escape hatches

```python
# BANNED (also semgrep: decepticon-no-blanket-type-ignore)
x = call()  # type: ignore
y = other()  # pyright: ignore

# REQUIRED — scoped suppression with justification
x: int = call_returning_str_that_is_actually_int()  # type: ignore[assignment]  # legacy API, tracked in #NNN
```

Same rule for `# noqa` — always with a code, ideally with a one-line
justification.

### Logging in production

```python
# BANNED in packages/decepticon/**, packages/decepticon-core/**
print(f"got result {result}")

# REQUIRED
from decepticon.core.logging import get_logger
log = get_logger("agents.recon.scanner")
log.info("recon scan complete", extra={"host_count": len(hosts)})
```

`print` is for `clients/cli` and `scripts/` only. Everywhere else,
use the project logger so output is structured and routable.

### Suppressed return values

```python
# BANNED
_ = something_that_returns_a_value()

# REQUIRED — use it, or don't call it
result = something_that_returns_a_value()
process(result)
```

If you don't need the value, the function probably shouldn't be called.
If you do, name it.

### Dead capabilities and stubs

- `TODO` without an issue link → not allowed.
- `FIXME` in production code → not allowed.
- `raise NotImplementedError` in a delivered feature → not allowed.
- Functions defined but called from nowhere → not allowed.

### Mutable defaults and wildcard imports

```python
# BANNED
def f(x, items=[]):  # shared across calls — classic bug
    ...

from somemodule import *  # imports unknown surface
```

### Cosmetic drive-bys

- Reordering imports outside your changed files.
- Reflowing strings, normalizing whitespace, or "fixing" comment style
  on files your PR did not need to touch.
- Mass-renaming variables for "consistency" without an ADR.
- Reformatting an entire file because your editor saved it.

Revert these before pushing. If the project formatter wants them,
land them as a separate, formatter-only PR.

### Test anti-patterns

```python
# BANNED — asserts on the call shape, not on behavior
def test_save_user():
    db = Mock()
    save_user(db, "alice")
    db.execute.assert_called_with("INSERT INTO users ...")

# BANNED — vague test names
def test_function_works(): ...
def test_happy_path(): ...
def test_basic_functionality(): ...

# BANNED — testing the mock you defined
def test_recon_returns_hosts():
    backend = Mock()
    backend.scan.return_value = ["1.1.1.1"]
    assert recon(backend) == ["1.1.1.1"]  # tautological

# REQUIRED — name describes behavior, asserts the observable outcome
def test_kerberoast_skill_rejects_realm_outside_roe():
    skill = KerberoastSkill(roe=ROE(realms={"CORP.LOCAL"}))
    with pytest.raises(OutOfScopeError):
        skill.run(target_realm="OTHER.LOCAL")
```

Also banned:

- `pytest.mark.skip` without a tracking issue.
- `@pytest.mark.flaky` — flakes get fixed, not annotated.
- `# pragma: no cover` to chase a coverage number.
- Tests that mock the function under test.
- Tests that pass without exercising the new code path. (Verify the
  test fails before your change.)

### Dependency hygiene

- New top-level dependency without an explicit "this is the smallest
  acceptable solution because X" paragraph in the PR body → closed.
- Pinning new deps via `requirements*.txt` instead of `uv add` →
  closed. The project uses `uv` and `pyproject.toml` is the source of
  truth.
- Vendoring code without a license review note → closed.

---

## AI-slop signatures

These are the **tells**. They are not rare; they appear in essentially
every long AI-generated diff that has not been edited down. The first
revision pass should be deleting them. If they survive into a PR, the
PR will be closed with a single comment pointing at this section.

### Prose / comment slop

| Tell                                                                   | Fix                                                              |
|------------------------------------------------------------------------|------------------------------------------------------------------|
| Em-dashes salad in code comments / docstrings                          | Use plain prose. One em-dash per paragraph is fine; six is slop. |
| "This module provides …" / "This function is responsible for …"        | Delete. The signature already says what it is. Say *why*.        |
| "We leverage X to robustly handle Y in a comprehensive manner"         | "X parses Y." Words like *leverage / robust / comprehensive / elegant / utilize / seamlessly* are flag words. |
| Comments that translate the next line into English (`# increment i`)   | Delete.                                                          |
| Docstrings that restate the parameter list                             | Delete the restating; keep only the contract/invariants/why.     |
| Section banners (`# ==== Helpers ====`) inside one-screen modules      | Delete. If the module needs banners, split the module.           |
| Sentences ending with "ensuring optimal performance"                   | Delete.                                                          |

### Code slop

| Tell                                                                                                       | Fix                                                              |
|------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| `if x is not None:` chains where the type system already proves it isn't None                              | Remove the check. Trust the types.                               |
| Defensive `try/except` wrapping every call "just to log and re-raise"                                      | Let exceptions propagate. Log at the boundary, not at each step. |
| One-line `_helper()` functions called from exactly one place                                               | Inline.                                                          |
| Speculative `**kwargs` or `Optional[…] = None` parameters "for future extensibility"                       | Remove. Add it when the second caller arrives.                   |
| `result = {}; result["a"] = …; result["b"] = …; return result`                                             | Use a dataclass / NamedTuple / TypedDict. Or return a tuple.     |
| Wrapping a stdlib call in a function that adds nothing                                                     | Inline.                                                          |
| Identical try/except blocks copy-pasted across N call sites                                                | Extract a context manager.                                       |
| Variables named `data`, `info`, `obj`, `item`, `result` in non-trivial functions                           | Rename to describe the thing.                                    |
| `if cond: return True\nelse: return False`                                                                 | `return cond`. (Or `return bool(cond)` if the type matters.)     |
| Stacked single-line conditionals expanded into 8 lines for "readability"                                   | One ternary or a guard clause. Read the surrounding code style.  |

### Diff slop

| Tell                                                                              | Fix                                                          |
|-----------------------------------------------------------------------------------|--------------------------------------------------------------|
| 30 files changed, 28 of them whitespace                                           | Revert the whitespace. Land the substantive change only.     |
| "Cleanup" commit alongside the feature commit                                     | Separate PR.                                                 |
| New file added that just re-exports existing names                                | Don't.                                                       |
| Multiple `# pragma: no cover` to hit a coverage target                            | Write the test or delete the unreachable branch.             |
| New skill / agent / middleware that wasn't in any issue or ADR                    | Open the ADR first.                                          |
| `from X import *` "to keep imports clean"                                         | Explicit imports.                                            |
| Migration of working code from `requests` to `httpx` (or similar) inside a fix PR | Separate PR with its own ADR.                                |

---

## Required positive patterns

The complement of the banned list. The reviewer is looking for these:

- **Every public function has explicit type annotations**, including
  return type. `-> None` when nothing is returned.
- **Every exception raised is a named class** that subclasses a
  Decepticon base error (`DecepticonError` or a domain-specific child).
- **Every fix PR's branch has a failing-test commit followed by a
  passing-test commit.** Don't squash locally; the maintainer wants
  to see the bug reproduced. CI will squash on merge.
- **Every magic number / string has a named constant or an inline
  one-line justification.** `timeout=300` is not OK; `LITELLM_BOOT_TIMEOUT_S = 300  # measured 136s on cold prisma + LLM-routing load` is.
- **Every TODO links to an issue.** `# TODO(#NNN): unblock once Sliver mTLS rotation lands`.
- **Every new module starts with a docstring naming the module's job in
  one sentence.** Not "this module provides utilities for…"; just the
  one sentence.
- **Every new dependency justifies its existence** in the PR body. Smaller
  is better. Stdlib > a 100-line library > a 10MB library.

---

## Test quality bar

A test that always passes is not a test; it is noise. The bar:

1. **You watched it fail before your change.** Otherwise the test
   isn't testing what you think it is.
2. **The test name describes the behavior**, not the function.
3. **The test asserts an observable outcome**, not the call shape of
   a mock.
4. **The test does not mock the system under test.** Mock the
   *environment* (network, clock, LLM provider), never the function
   you are testing.
5. **The test exercises a branch or a boundary**, not the default
   path of a configuration setting. Changing the default should never
   break the test.
6. **One logical assertion per test.** If a test name has "and" in
   it, split it.
7. **No `pytest.mark.skip` without a linked issue. No `xfail` for "we
   know this is broken." Fix it or delete it.**

---

## Self-review standard

Before you request review, your honest answer to all of these is yes:

- [ ] I would merge this PR if a stranger opened it.
- [ ] A maintainer reading the diff will not have to ask "why" anywhere.
- [ ] The PR title alone tells a future maintainer what changed.
- [ ] The commit messages explain **why**; the code shows **what**.
- [ ] Every changed line is here because the stated intent required it.
- [ ] I read the diff in full. I can defend every line on demand.
- [ ] I ran the verification I claim to have run.
- [ ] **I executed every new or changed code path on my own machine —
  not just "tests pass." The PR body's End-to-end verification
  statement names the commands I ran and the behavior I observed.**
- [ ] No banned pattern is present.
- [ ] No AI-slop signature is present.
- [ ] If I were tired and reviewing this at the end of a long day, I
      would still merge it.

If any answer is no, do not request review. Fix it first.

---

## Escalation

There are exactly three escape valves for the rules above. Each is
explicit; none can be invoked silently.

1. **ADR.** A design decision the rules do not anticipate? Open an
   ADR (`docs/adr/template.md`). Land the ADR first; the code follows.
2. **`large-diff-approved` label.** Diff genuinely cannot be split?
   Justify it in the PR body and request the label from `@PurpleCHOIms`.
   Refusal is the default.
3. **Documented exception in this file.** A rule needs a permanent
   carve-out? Open a PR against this file with an ADR — the carve-out
   and its reasoning land together, or neither lands.

The rules are not democratic. They are how the project survives a
contribution stream that scales faster than review can.

---

## What "100%" actually means

It does not mean:

- 100% code coverage. (Coverage is a side effect of good testing,
  not the target.)
- Zero bugs forever. (Bugs happen. Bug fixes that ship a regression
  test are how we learn.)
- Every PR is perfect on the first push. (Iteration is fine.
  Iteration is *good*. The bar is on what merges, not on what is
  drafted.)

It does mean:

- Every line that lands on `main` was deliberate.
- Every line on `main` was reviewed by a human who could defend it.
- Every line on `main` traces to an intent that was written down
  somewhere — issue, ADR, or release-blocker.
- No line on `main` exists because "the AI suggested it" or "the
  test was passing and the diff was small."

That is the bar. It is high on purpose. It is the only way a
single-owner project survives the AI-contribution era with its
architecture intact.
