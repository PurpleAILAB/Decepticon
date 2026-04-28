---
name: structured-questions
description: "When and how to use ask_user_question — structured multiple-choice prompts vs. free-text prose during the engagement interview."
allowed-tools: Read Write
metadata:
  subdomain: planning
  when_to_use: "interview the operator, ask a yes/no, pick engagement type, choose attack class, scope window, posture choice, multi-select kill-chain phases"
  tags: interview, ask_user_question, picker, multiple-choice
  mitre_attack: []
---

# Structured Operator Questions (`ask_user_question`)

The Soundwave interview has two question channels:

- `ask_user_question` — structured multiple-choice picker rendered in the CLI
- Plain prose — free-form question asked in chat, the operator types a reply

Pick the right channel for each round.

## When to call `ask_user_question`

EVERY operator-facing question. There is no prose-question path. Provide
2–5 best-guess options for the dimension and always set `allow_other=true`
so the operator can override with a custom answer when none of your
predefined options fit.

Typical dimensions:
- **Engagement type**: External / Internal / Hybrid / Assumed-breach / Physical
- **Attack class**: Web / Cloud / AD / Mixed
- **Scope window**: Business hours / 24x7 / Custom
- **Posture choices**: OPSEC level (Loud / Quiet / Stealth)
- **Confirmations**: Two-option Yes / No after a derived assumption
- **Phase selection**: Multi-select over kill-chain phases (set `multi_select=true`)
- **Free-form fields** (organization / IP range / contact): still use the tool —
  list 2–4 plausible guesses + `allow_other=true`, the operator types the
  actual value via the Other fallback if your guesses miss.

The tool pauses the run while the operator picks, then resumes with the
chosen `label` (or list of labels for multi-select, or free text when the
operator chose `Other`). Treat the returned value as authoritative.

## Habits (the typed tool signature already encodes the schema)

- Mark the most common option with a trailing ` (Recommended)` on its `label`
- **Never invent an `Other` option yourself** — set `allow_other=true` and
  the picker appends a free-text fallback that returns the operator's text
  verbatim
- For multi-select questions, set `multi_select=true`; the tool returns the
  list of chosen labels (in selection order)

## Examples

### Single-select, with recommendation
```python
ask_user_question(
    question="What is the operator's posture for this engagement?",
    header="OPSEC",
    options=[
        {"label": "Quiet (Recommended)", "description": "Minimize detection signals; rate-limited recon"},
        {"label": "Loud",                "description": "Speed over stealth; full-rate scans permitted"},
        {"label": "Stealth",             "description": "Avoid detection at all costs; manual cadence"},
    ],
)
```

### Confirmation with `allow_other` for custom note
```python
ask_user_question(
    question="Is the testing window strictly business hours (09:00–18:00, client TZ)?",
    header="Window",
    options=[
        {"label": "Yes", "description": "Business hours only"},
        {"label": "No",  "description": "24x7 testing permitted"},
    ],
    allow_other=True,  # operator can type a custom window if neither fits
)
```

### Multi-select for kill-chain phases
```python
ask_user_question(
    question="Which kill-chain phases are in scope?",
    header="Phases",
    options=[
        {"label": "Recon",        "description": "Passive + active enumeration"},
        {"label": "Exploitation", "description": "Initial access via discovered weaknesses"},
        {"label": "Post-exploit", "description": "Privilege escalation, lateral movement, C2"},
        {"label": "Exfiltration", "description": "Crown-jewel retrieval simulation"},
    ],
    multi_select=True,
)
```

## Anti-patterns

- Asking `ask_user_question("What is the client organization name?", ...)` —
  this is a free-form name; use prose instead
- Adding an `"Other"` entry to `options` manually — set `allow_other=true`
- Header longer than 12 chars (`"Engagement Type"` → use `"Eng. type"`)
- Re-asking the same dimension after the operator already answered — the
  returned value is authoritative; record it and move to the next dimension
