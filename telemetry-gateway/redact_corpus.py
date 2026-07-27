#!/usr/bin/env python3
"""Layer 2 — the semantic redaction gate in front of training.

`export_corpus.py` reconstructs trajectories from PostHog. Those trajectories
have passed the *client* masker, which is pattern-based and therefore bounded:
it reliably strips structured identifiers (IPs, emails, keys) and whatever the
engagement declared, and it structurally cannot strip a company name typed into
free prose, a credential phrased in a language the patterns do not cover, or a
distinctive description of an asset. Reading 538k live events found all three.

This script is the layer that can. It runs **after** collection and **before**
the corpus is used for training, where latency stops mattering and correctness
starts — the placement OpenTelemetry prescribes (redact at the collector, not
the SDK) and the lifecycle stage ISO/IEC 27559 asks for ("internal reuse").

    export_corpus.py  ->  redact_corpus.py  ->  training set
                              |
                              +-> quarantine.jsonl  (never reaches training)

Two passes per trajectory, both LLM:

1. **Redact** — mask any residual target identifier with the same `<TYPE_n>`
   placeholders, preserving the reasoning verbatim. Technique names, tool names,
   CVEs and ATT&CK ids are explicitly kept; they are the signal.
2. **Verify** — an independent prompt, no memory of pass 1, asked only "does
   anything here still identify a real organization, person, or host?" A
   trajectory that fails is quarantined rather than shipped. Fail-closed, same
   posture as the Tier-C scanner.

A model can memorize its training data, so anything that survives this gate is
effectively permanent. Quarantining a usable trajectory costs one trajectory;
letting one through costs a target's data, forever.

Usage:
    set -a; . ~/.decepticon/telemetry-deploy.env; set +a
    python export_corpus.py --out corpus.jsonl
    python redact_corpus.py --in corpus.jsonl --out corpus.clean.jsonl \\
        --quarantine corpus.quarantine.jsonl
    python redact_corpus.py --self-test        # offline logic check

Env: DECEPTICON_LLM__PROXY_URL, DECEPTICON_LLM__PROXY_API_KEY, REDACT_MODEL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from typing import Any

# Fields carrying free text. Everything else in a step is a slug or an int.
TEXT_FIELDS = ("text", "args_text", "observation")

# A placeholder the client masker already produced. Pass 1 must reuse this shape
# so a trajectory stays internally consistent.
PLACEHOLDER = re.compile(r"<[A-Z]+_\d+>")

REDACT_SYSTEM = """\
You find identifiers in red-team engagement transcripts destined for a training
corpus. You do NOT rewrite the text — you only report what must be masked, and
code applies the replacements.

Report every remaining identifier of a REAL target. Types: ORG, PERSON, HOST, \
IP, URL, DOMAIN, CRED, EMAIL, PATH.

Report:
- organization, product, client and bug-bounty program names
- personal names, usernames, email addresses
- hostnames, domains, IPs, URLs, and file paths that identify a target
- credentials, keys and tokens in ANY language or syntax, including command-line
  flags (-p, --password) and natural phrasings

Keep EXACTLY as written — these are the signal, not identifiers:
- the reasoning, hypotheses, and rationale
- technique names, tool names, CVE ids, MITRE ATT&CK ids, CWE ids
- generic infrastructure words (nginx, mysql, Active Directory, ESXi)
- existing <TYPE_n> placeholders

Return the exact substrings to replace, copied verbatim from the input so they
can be matched literally. Report each distinct value once; every occurrence is
replaced. Report nothing if there is nothing to mask.

Return JSON and nothing else:
{"identifiers": [{"value": "<exact substring>", "type": "<TYPE>"}]}\
"""

VERIFY_SYSTEM = """\
You audit de-identified red-team text before it is used to train a model.

Answer one question: could a reader identify a real organization, person, or \
host from this text? Consider indirect evidence — a product name, a bug-bounty \
program, a distinctive asset description, or an unusual combination of details \
— not only explicit identifiers. <TYPE_n> placeholders are already masked and \
are not identifying.

Be strict. A model memorizes its training data, so a miss is permanent.

Return JSON: {"identifying": true|false, "reason": "<short reason>"}\
"""


def _post(url: str, body: dict[str, Any], api_key: str, timeout: int = 120) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator-configured
        return json.loads(resp.read())


def _chat(system: str, user: str, cfg: dict[str, str]) -> dict[str, Any]:
    """One JSON-returning chat completion through the LiteLLM proxy."""
    out = _post(
        f"{cfg['url'].rstrip('/')}/v1/chat/completions",
        {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 8000,
        },
        cfg["key"],
    )
    return _parse_json(out["choices"][0]["message"]["content"])


def _parse_json(content: str) -> dict[str, Any]:
    """Parse a model's JSON reply, tolerating a markdown fence around it.

    ``response_format={"type": "json_object"}`` is advisory on some proxy paths —
    the Anthropic-via-OAuth route returns ```` ```json … ``` ```` — so a strict
    ``json.loads`` quarantined every trajectory.
    """
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.rstrip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def steps_to_prompt(steps: list[dict[str, Any]]) -> str:
    """Render a trajectory as numbered text units for one LLM call.

    The whole trajectory goes in one prompt on purpose: whether a token is an
    identifier is only decidable from surrounding turns.
    """
    lines: list[str] = []
    for i, step in enumerate(steps):
        for field in TEXT_FIELDS:
            value = step.get(field)
            if value:
                lines.append(f"[{i}.{field}]\n{value}")
    return "\n\n".join(lines)


def apply_redacted_units(
    steps: list[dict[str, Any]], units: dict[str, str]
) -> list[dict[str, Any]]:
    """Write redacted text back onto a copy of ``steps`` by ``i.field`` key."""
    out = [dict(s) for s in steps]
    for key, value in units.items():
        idx, _, field = key.partition(".")
        if not idx.isdigit() or field not in TEXT_FIELDS:
            continue
        i = int(idx)
        if 0 <= i < len(out) and out[i].get(field):
            out[i][field] = value
    return out


def parse_units(text: str) -> dict[str, str]:
    """Parse the `[i.field]` blocks back out of a model response."""
    units: dict[str, str] = {}
    for match in re.finditer(
        r"^\[(\d+\.(?:text|args_text|observation))\]\n(.*?)(?=^\[\d+\.|\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    ):
        units[match.group(1)] = match.group(2).rstrip("\n")
    return units


def apply_identifiers(
    steps: list[dict[str, Any]], identifiers: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], int]:
    """Replace reported identifiers across every text field. Pure, deterministic.

    The model reports WHAT to mask; this does the masking. That split matters:
    asking a model to echo a whole trajectory back risks truncation and silent
    rewriting of the reasoning, which is the one thing the corpus exists to keep.

    Longest value first so a substring never eats its container. Numbering
    continues past the placeholders the client masker already emitted.
    """
    counters: dict[str, int] = {}
    for step in steps:
        for field in TEXT_FIELDS:
            for m in PLACEHOLDER.finditer(str(step.get(field) or "")):
                ptype, _, num = m.group(0)[1:-1].rpartition("_")
                if num.isdigit():
                    counters[ptype] = max(counters.get(ptype, 0), int(num))

    mapping: dict[str, str] = {}
    for item in sorted(identifiers, key=lambda i: len(str(i.get("value", ""))), reverse=True):
        value = str(item.get("value") or "")
        ptype = re.sub(r"[^A-Z]", "", str(item.get("type") or "").upper()) or "ORG"
        # Never mask an existing placeholder, and never mask a fragment so short
        # it would match everywhere.
        if len(value) < 3 or PLACEHOLDER.fullmatch(value) or value in mapping:
            continue
        counters[ptype] = counters.get(ptype, 0) + 1
        mapping[value] = f"<{ptype}_{counters[ptype]}>"

    out = [dict(s) for s in steps]
    applied = 0
    for step in out:
        for field in TEXT_FIELDS:
            text = step.get(field)
            if not text:
                continue
            for value, token in mapping.items():
                if value in text:
                    text = text.replace(value, token)
                    applied += 1
            step[field] = text
    return out, applied


def redact_trajectory(traj: dict[str, Any], cfg: dict[str, str]) -> tuple[dict[str, Any], str]:
    """Return ``(trajectory, verdict)`` where verdict is ``clean`` or a reason.

    Never raises: a trajectory that cannot be processed is quarantined, not
    passed through. Fail-closed.
    """
    steps = traj.get("steps") or []
    prompt = steps_to_prompt(steps)
    if not prompt.strip():
        return traj, "empty"
    try:
        found = _chat(REDACT_SYSTEM, prompt, cfg).get("identifiers") or []
        if not isinstance(found, list):
            return traj, "redaction returned a malformed identifier list"
        out = dict(traj)
        out["steps"], _ = apply_identifiers(steps, [i for i in found if isinstance(i, dict)])
        verdict = _chat(VERIFY_SYSTEM, steps_to_prompt(out["steps"]), cfg)
    except Exception as exc:  # noqa: BLE001 — any failure quarantines, never passes
        return traj, f"error: {type(exc).__name__}"
    if verdict.get("identifying"):
        return out, f"verifier: {str(verdict.get('reason', ''))[:200]}"
    return out, "clean"


# ── offline checks ───────────────────────────────────────────────────────────

_SELF_TEST_STEPS = [
    {"step": 0, "role": "human", "text": "Objective: test the CodeAnt portal at <IP_1>"},
    {"step": 1, "role": "agent", "text": "SQLi on the login looks promising"},
    {
        "step": 2,
        "role": "tool",
        "tool": "bash",
        "args_text": "sqlmap -u <URL_1>",
        "observation": "12 rows",
    },
]


def _self_test() -> int:
    prompt = steps_to_prompt(_SELF_TEST_STEPS)
    assert "[0.text]" in prompt and "[2.args_text]" in prompt and "[2.observation]" in prompt
    assert "[1.args_text]" not in prompt, "absent fields must not be emitted"

    round_tripped = parse_units(prompt)
    assert round_tripped["0.text"] == _SELF_TEST_STEPS[0]["text"], round_tripped
    assert round_tripped["2.observation"] == "12 rows"

    applied, n = apply_identifiers(_SELF_TEST_STEPS, [{"value": "CodeAnt", "type": "ORG"}])
    assert applied[0]["text"] == "Objective: test the <ORG_1> portal at <IP_1>", applied[0]
    assert n == 1
    assert _SELF_TEST_STEPS[0]["text"].startswith("Objective: test the CodeAnt"), "must not mutate"
    assert applied[1]["text"] == _SELF_TEST_STEPS[1]["text"], "untouched steps stay identical"

    # Numbering continues past placeholders the client masker already emitted,
    # so <IP_1> is never reused for a different entity.
    bumped, _ = apply_identifiers(
        [{"text": "<IP_1> and <IP_2> and 10.0.0.9"}], [{"value": "10.0.0.9", "type": "IP"}]
    )
    assert bumped[0]["text"] == "<IP_1> and <IP_2> and <IP_3>", bumped

    # Longest first, so a substring never eats its container.
    nested, _ = apply_identifiers(
        [{"text": "corp and corp-internal"}],
        [{"value": "corp", "type": "ORG"}, {"value": "corp-internal", "type": "ORG"}],
    )
    assert nested[0]["text"] == "<ORG_2> and <ORG_1>", nested

    # An existing placeholder is never re-masked, and fragments are ignored.
    safe, _ = apply_identifiers(
        [{"text": "<ORG_1> x"}],
        [{"value": "<ORG_1>", "type": "ORG"}, {"value": "x", "type": "ORG"}],
    )
    assert safe[0]["text"] == "<ORG_1> x", safe
    assert applied[1]["text"] == _SELF_TEST_STEPS[1]["text"], "untouched steps stay identical"

    # A bogus key must never write outside the trajectory.
    assert apply_redacted_units(_SELF_TEST_STEPS, {"99.text": "x", "0.bogus": "y"})[0][
        "text"
    ].startswith("Objective: test the CodeAnt")

    # Model replies arrive fenced on some proxy paths; a strict json.loads
    # quarantined every trajectory until this tolerated them.
    assert _parse_json('```json\n{"text": "ok"}\n```') == {"text": "ok"}
    assert _parse_json('{"identifying": false}') == {"identifying": False}
    assert _parse_json('here you go: {"text": "ok"} done') == {"text": "ok"}
    print("self-test OK: units render, round-trip, and apply without mutating the input")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--in", dest="src", default="-", help="corpus JSONL from export_corpus.py")
    ap.add_argument("--out", default="-", help="redacted JSONL (training input)")
    ap.add_argument("--quarantine", default=None, help="JSONL for trajectories that failed verify")
    ap.add_argument("--limit", type=int, default=None, help="process at most N trajectories")
    ap.add_argument("--self-test", action="store_true", help="run offline checks and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    cfg = {
        "url": os.environ.get("DECEPTICON_LLM__PROXY_URL", ""),
        "key": os.environ.get("DECEPTICON_LLM__PROXY_API_KEY", ""),
        "model": os.environ.get("REDACT_MODEL", "auth/claude-haiku-4-5"),
    }
    if not cfg["url"] or not cfg["key"]:
        print(
            "error: set DECEPTICON_LLM__PROXY_URL and DECEPTICON_LLM__PROXY_API_KEY.",
            file=sys.stderr,
        )
        return 2

    src = sys.stdin if args.src == "-" else open(args.src, encoding="utf-8")  # noqa: SIM115
    out = sys.stdout if args.out == "-" else open(args.out, "w", encoding="utf-8")  # noqa: SIM115
    quarantine = open(args.quarantine, "w", encoding="utf-8") if args.quarantine else None  # noqa: SIM115

    kept = dropped = 0
    try:
        for n, line in enumerate(src):
            if args.limit is not None and n >= args.limit:
                break
            line = line.strip()
            if not line:
                continue
            traj = json.loads(line)
            redacted, verdict = redact_trajectory(traj, cfg)
            if verdict == "clean":
                out.write(json.dumps(redacted, ensure_ascii=False) + "\n")
                kept += 1
            else:
                dropped += 1
                if quarantine:
                    quarantine.write(
                        json.dumps({**redacted, "_quarantine_reason": verdict}, ensure_ascii=False)
                        + "\n"
                    )
            if (kept + dropped) % 25 == 0:
                print(f"  {kept} kept / {dropped} quarantined", file=sys.stderr)
    finally:
        for fh in (src, out, quarantine):
            if fh and fh not in (sys.stdin, sys.stdout):
                fh.close()

    total = kept + dropped
    rate = (100 * dropped / total) if total else 0
    print(f"{kept} kept, {dropped} quarantined ({rate:.1f}%) of {total}", file=sys.stderr)
    if not args.quarantine and dropped:
        print(
            "note: pass --quarantine to keep the rejected trajectories for review.", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
