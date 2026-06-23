# SKILL.md Canonical Schema

This is the authoring contract for every `SKILL.md` file in
`packages/decepticon/decepticon/skills/**`. CI runs
`python -m decepticon.skill_audit` against the tree; any violation listed
below either fails the build (after Phase 0 completes) or surfaces as a
warning (during Phase 0 cleanup).

## Required frontmatter

Every SKILL.md must begin with a YAML frontmatter block:

```yaml
---
name: <slug>                     # required, unique across the corpus
description: |                   # required, one-line
  <one-line skill summary>

metadata:
  subdomain: <canonical>         # required, must be in subdomains.yaml
  when_to_use: |                 # required, comma-separated trigger keywords
    <kw1>, <kw2>, ...
  mitre_attack:                  # required unless the file lives under
    - T1190                      # /skills/*/reporting/ or /skills/*/analyst/
    - T1595.001
  tags:                          # optional, free-form list
    - <tag1>
    - <tag2>

  # Optional raw-preservation fields (graph keeps them as-is).
  aatmf_tactic: [...]            # SnailSploit AATMF v3 mappings
  upstream_ref: <ref>             # external skill reference
---
```

## MITRE ID formats accepted

| Matrix | Format | Example | Phase 1a graph edge? |
|---|---|---|---|
| ATT&CK Enterprise / Mobile | `T\d{4}(\.\d{3})?` | `T1190`, `T1595.001` | Yes (Enterprise only) |
| ATT&CK ICS | `T0\d{3}(\.\d{3})?` | `T0800`, `T0830.001` | No — preserved as raw, edge in Phase 1b |
| MITRE ATLAS | `AML\.T\d{4}(\.\d{3})?` | `AML.T0043` | No — preserved as raw, edge in Phase 1b |

Any other format (free text, `TA\d{4}` tactic IDs, non-matching
strings) is a validator error.

## Subdomain alias map

Some non-canonical subdomain values are silently rewritten during the
graph build. Authors should write the canonical form directly; the alias
map exists only to absorb existing corpus drift.

| Author wrote | Canonical |
|---|---|
| `reverser`, `re` | `reverse-engineering` |
| `contracts` | `smart-contracts` |
| `cloud-native` | `cloud` |
| `ad` | `active-directory` |
| `phish` | `phishing` |
| `ics` | `ics-ot` |
| `c2` | `command-and-control` |
| `post-exploitation` | `post-exploit` |
| `supplychain` | `supply-chain` |
| `api`, `injection`, `client-side`, `authentication`, `authorization`, `redirect`, `cache` | `web-exploitation` (web-attack sub-categories) |
| `infrastructure` | `command-and-control` |
| `cryptanalysis` | `credential-access` |
| `verification` | `analyst` |
| `deconfliction` | `orchestration` |

## Fields explicitly NOT in this schema

The v0.1 design proposed these fields. They are dropped:

- `allowed-tools` — VESTIGIAL. The current production middleware does not
  read it; tool dispatch is not skill-gated.
- `metadata.kind` — DEAD. 4 of 251 files declare it; 0 code paths branch
  on it. "Offensive" vs "non-offensive" is inferred from path
  (`/skills/*/reporting/` and `/skills/*/analyst/` are non-offensive).
- `metadata.safety_critical` — ASPIRATIONAL. 1 file. Re-introduce only
  when gating is a concrete requirement.
- `metadata.gated_by_conops` — ASPIRATIONAL. 1 file. Same disposition.

If a SKILL.md still has any of these fields, the cleanup batch removes
them.

## Validation rules

The validator emits one error per violation, with rule ID:

- **R-missing-required**: `name`, `description`, `metadata.subdomain`, or
  `metadata.when_to_use` is missing.
- **R-bad-subdomain**: `metadata.subdomain` is not in `subdomains.yaml`
  and is not in the alias map.
- **R-bad-mitre-format**: a `metadata.mitre_attack` entry does not match
  any of the three accepted formats.
- **R-no-attribution**: file is "offensive" (path is not under
  `/skills/*/reporting/` or `/skills/*/analyst/`) **and** every
  attribution field is empty (`metadata.mitre_attack`,
  `metadata.aatmf_tactic`, `metadata.upstream_ref`).

R-no-attribution is the path-based replacement for the v0.1 spec's
`kind: offensive` check; it uses concrete data (file path) instead of
the dead `kind` field.

## Authoring workflow

1. Write your SKILL.md with the schema above.
2. Run `make audit-skills` locally. Fix any error before opening a PR.
3. CI runs the validator on every PR. During Phase 0 it warns; after
   Phase 0 completes, it blocks the merge.

See [docs/skill-cleanup-process.md](skill-cleanup-process.md) for how
existing files are being normalized.
