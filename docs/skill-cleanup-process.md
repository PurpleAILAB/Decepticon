# SKILL.md Corpus Cleanup — Phase 0 Process

Phase 0 of the Skillogy redesign normalizes 251 `SKILL.md` files against
the canonical schema documented in
[docs/skill-schema.md](skill-schema.md). The cleanup runs as a series of
co-design PR batches grouped by subdomain.

## Why batched

`make audit-skills` returns dozens of violations across the corpus, but
not all are equal: a missing `mitre_attack` field needs a domain-aware
mapping decision (which MITRE technique actually fits this skill?), and
a tactic-as-technique misuse needs the same. Batching by subdomain keeps
each PR small enough for one human to review and small enough for the
sub-agent to hold context for.

## The loop

For each subdomain batch (e.g. `reconnaissance`, then `web-exploitation`,
then `active-directory`, …):

1. **Scope the batch.** A maintainer picks a subdomain and asks the
   cleanup sub-agent for a fix proposal:

   ```
   /agent skill-cleanup-batch subdomain=reconnaissance
   ```

   The sub-agent reads every SKILL.md under that subdomain
   (canonical-form check + alias-resolved path), runs the body through
   the rule audit, and emits a per-file proposal.

2. **Sub-agent proposes.** For each file with violations, the proposal
   contains:
   - The current frontmatter block.
   - The proposed normalized frontmatter block.
   - Reasoning: which MITRE techniques fit the body's described actions,
     why an alias was rewritten, why a deprecated field was dropped.
   - **Body audit notes** (flag-suspicious only): description-vs-body
     mismatches, stale techniques, broken references, misplaced
     skills. These are noted but **not** rewritten in this PR — body
     rewrites are out of scope for Phase 0.

3. **User reviews the PR.** Accept / modify / reject per file. The
   maintainer pushes the agreed patch.

4. **CI runs `make audit-skills`** in warn mode. The PR may still have
   pending violations from other subdomains — that is expected, the
   batch only fixes its own.

5. **Merge and move to the next batch.**

## Where each batch's progress is tracked

A running checklist lives in `docs/skill-cleanup-progress.md` (created
on first batch). Each subdomain has a row: pending / in-progress / done,
with PR number. The maintainer updates it per merge.

## When Phase 0 ends

When `make audit-skills-strict` exits 0 on the whole corpus, Phase 0
is structurally complete:

1. Open the final PR that flips CI from `make audit-skills` to
   `make audit-skills-strict`. Now every future SKILL.md change is
   gated by the schema.
2. Annotate `docs/skill-cleanup-progress.md` as complete.
3. Phase 1a (graph builder) is unblocked.

## Body-rewrite work (out of scope for Phase 0)

The `flag-suspicious` notes accumulated through Phase 0 batches are
collected into follow-up issues labelled `skill-body-audit`. Those PRs
happen against the cleaned-up frontmatter and are not gated by this
plan.
