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
from concurrent.futures import ThreadPoolExecutor, as_completed
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

Task: NAME the real-world entity that was the TARGET of this engagement — the
organization, client, person, or host being tested. Put it in "entity".

You must produce a name, not a suspicion. "Some organization is masked here" is
not a name — a <TYPE_n> placeholder is already de-identified and tells you
nothing. Set "identifying": false with an empty "entity" unless you can write
down a real entity a reader could look up AND it is the thing under test.

TARGET (flag these):
- the client or organization being assessed, however it is referred to
- a person, handle, or account belonging to the target
- an unmasked domain, host, or bug-bounty program of the target

NOT the target (never flag, no matter how specific):
- tools and scanners the operator ran: nmap, semgrep, ffuf, sqlmap, BloodHound
- software the target happens to run: Redis, nginx, MySQL, ADFS, Active Directory
- threat actors and adversary profiles being emulated: APT28, Sandworm, FIN7
- the AI vendor, model, or CLI running the engagement
- techniques, CVEs, ATT&CK ids, vulnerability detail, generic product categories
- that a red-team engagement happened, or how it was run

If the only names you can find are tools, platforms, or emulated actors, the
text is not identifying. Say so.

Return JSON and nothing else. "entity" and "reason" must be single short lines
with no newlines or quote characters:
{"identifying": true|false, "entity": "<target name or empty>", "reason": "<how>"}\
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


_IS_PLACEHOLDER_NAME = re.compile(r"<?[A-Z]+_\d+>?")


def _chat(system: str, user: str, cfg: dict[str, str], _retry: bool = True) -> dict[str, Any]:
    """One JSON-returning chat completion through the LiteLLM proxy.

    Retries once on a malformed reply: models occasionally emit unescaped
    content inside the JSON, and a fail-closed pipeline turns every such blip
    into a discarded trajectory.
    """
    try:
        return _chat_once(system, user, cfg)
    except (json.JSONDecodeError, KeyError, IndexError):
        if not _retry:
            raise
        return _chat_once(system, user + "\n\n(Return strictly valid JSON.)", cfg)


def _chat_once(system: str, user: str, cfg: dict[str, str]) -> dict[str, Any]:
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


def text_windows(steps: list[dict[str, Any]], size: int = 24_000) -> list[str]:
    """Slice a trajectory's free text into windows that fit one LLM call.

    Detection does not need the step structure — it needs text to read, and
    replacement is applied globally by substring afterwards. So a 6.8M-character
    trajectory (the largest in the corpus) becomes a few hundred windows rather
    than one impossible request.
    """
    windows: list[str] = []
    buf: list[str] = []
    used = 0
    for step in steps:
        for field in TEXT_FIELDS:
            value = str(step.get(field) or "")
            while value:
                room = size - used
                if room <= 0:
                    windows.append("\n".join(buf))
                    buf, used = [], 0
                    room = size
                head, value = value[:room], value[room:]
                buf.append(head)
                used += len(head)
    if buf:
        windows.append("\n".join(buf))
    return windows


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


def _map_windows(system: str, windows: list[str], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one prompt over every window concurrently, preserving order."""
    from concurrent.futures import ThreadPoolExecutor

    workers = max(1, min(int(cfg.get("window_workers", 4)), len(windows)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda w: _chat(system, w, cfg), windows))


def redact_trajectory(traj: dict[str, Any], cfg: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return ``(trajectory, verdict)`` where verdict is ``clean`` or a reason.

    Never raises: a trajectory that cannot be processed is quarantined, not
    passed through. Fail-closed.
    """
    steps = traj.get("steps") or []
    size = int(cfg.get("window", 24_000))
    windows = text_windows(steps, size)
    if not windows or not any(w.strip() for w in windows):
        return traj, "empty"
    try:
        found: list[dict[str, str]] = []
        for reply in _map_windows(REDACT_SYSTEM, windows, cfg):
            items = reply.get("identifiers")
            if isinstance(items, list):
                found.extend(i for i in items if isinstance(i, dict))
        out = dict(traj)
        out["steps"], _ = apply_identifiers(steps, found)
        verdicts = _map_windows(VERIFY_SYSTEM, text_windows(out["steps"], size), cfg)
    except Exception as exc:  # noqa: BLE001 — any failure quarantines, never passes
        return traj, f"error: {type(exc).__name__}: {str(exc)[:120]}"
    for verdict in verdicts:
        # A flag without a named entity is the verifier restating that masking
        # happened — measured at 49% of quarantines before it had to name one.
        entity = str(verdict.get("entity") or "").strip()
        # A placeholder is not a name. Naming "<ORG_1>" is the verifier restating
        # that masking happened — the failure mode that was 49% of quarantines.
        if _IS_PLACEHOLDER_NAME.fullmatch(entity):
            entity = ""
        if verdict.get("identifying") and entity:
            return out, f"verifier[{entity[:60]}]: {str(verdict.get('reason', ''))[:160]}"
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
    windows = text_windows(_SELF_TEST_STEPS, size=10_000)
    assert len(windows) == 1 and "CodeAnt" in windows[0] and "12 rows" in windows[0]
    # A trajectory far larger than one request splits rather than failing.
    big = [{"text": "x" * 100_000}]
    assert len(text_windows(big, size=24_000)) == 5, len(text_windows(big, size=24_000))
    assert sum(len(w) for w in text_windows(big, size=24_000)) == 100_000, "no text lost"

    applied, n = apply_identifiers(_SELF_TEST_STEPS, [{"value": "CodeAnt", "type": "ORG"}])
    assert applied[0]["text"] == "Objective: test the <ORG_1> portal at <IP_1>", applied[0]
    assert n == 1
    assert _SELF_TEST_STEPS[0]["text"].startswith("Objective: test the CodeAnt"), "must not mutate"
    assert applied[1]["text"] == _SELF_TEST_STEPS[1]["text"], "untouched steps stay identical"

    # Numbering continues past placeholders the client masker already emitted.
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

    # Model replies arrive fenced on some proxy paths.
    assert _parse_json('```json\n{"text": "ok"}\n```') == {"text": "ok"}
    assert _parse_json('here you go: {"text": "ok"} done') == {"text": "ok"}
    print("self-test OK: windows split without loss; replacements apply deterministically")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--in", dest="src", default="-", help="corpus JSONL from export_corpus.py")
    ap.add_argument("--out", default="-", help="redacted JSONL (training input)")
    ap.add_argument("--quarantine", default=None, help="JSONL for trajectories that failed verify")
    ap.add_argument("--limit", type=int, default=None, help="process at most N trajectories")
    ap.add_argument("--workers", type=int, default=4, help="trajectories in flight")
    ap.add_argument(
        "--window-workers", type=int, default=4, help="windows in flight per trajectory"
    )
    ap.add_argument("--window", type=int, default=24_000, help="characters per LLM window")
    ap.add_argument("--self-test", action="store_true", help="run offline checks and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    cfg: dict[str, Any] = {
        "url": os.environ.get("DECEPTICON_LLM__PROXY_URL", ""),
        "key": os.environ.get("DECEPTICON_LLM__PROXY_API_KEY", ""),
        "model": os.environ.get("REDACT_MODEL", "auth/claude-haiku-4-5"),
        "window": args.window,
        "window_workers": args.window_workers,
    }
    if not cfg["url"] or not cfg["key"]:
        print(
            "error: set DECEPTICON_LLM__PROXY_URL and DECEPTICON_LLM__PROXY_API_KEY.",
            file=sys.stderr,
        )
        return 2

    src = sys.stdin if args.src == "-" else open(args.src, encoding="utf-8")  # noqa: SIM115
    try:
        trajectories = [json.loads(line) for line in src if line.strip()]
    finally:
        if src is not sys.stdin:
            src.close()
    if args.limit is not None:
        trajectories = trajectories[: args.limit]

    out = sys.stdout if args.out == "-" else open(args.out, "w", encoding="utf-8")  # noqa: SIM115
    quarantine = open(args.quarantine, "w", encoding="utf-8") if args.quarantine else None  # noqa: SIM115

    kept = dropped = 0
    reasons: dict[str, int] = {}
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(redact_trajectory, traj, cfg): traj for traj in trajectories}
            for done, fut in enumerate(as_completed(futures), 1):
                redacted, verdict = fut.result()
                if verdict == "clean":
                    out.write(json.dumps(redacted, ensure_ascii=False) + "\n")
                    kept += 1
                else:
                    dropped += 1
                    reasons[verdict.split(":")[0]] = reasons.get(verdict.split(":")[0], 0) + 1
                    if quarantine:
                        quarantine.write(
                            json.dumps(
                                {**redacted, "_quarantine_reason": verdict}, ensure_ascii=False
                            )
                            + "\n"
                        )
                out.flush()
                if quarantine:
                    quarantine.flush()
                if done % 10 == 0 or done == len(trajectories):
                    print(
                        f"  {done}/{len(trajectories)} — {kept} kept / {dropped} quarantined",
                        file=sys.stderr,
                        flush=True,
                    )
    finally:
        for fh in (out, quarantine):
            if fh and fh is not sys.stdout:
                fh.close()

    total = kept + dropped
    rate = (100 * dropped / total) if total else 0
    print(f"{kept} kept, {dropped} quarantined ({rate:.1f}%) of {total}", file=sys.stderr)
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
