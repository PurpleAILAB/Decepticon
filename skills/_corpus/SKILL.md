---
name: corpus-overview
description: Vendored knowledge-base corpus root. Pinned external references that decepticon agents can read directly when domain skills under skills/<area>/ don't cover a vuln class in enough depth.
when_to_use: "payloadsallthethings reference cheatsheet bypass list canonical"
---

# Corpus — Vendored Knowledge Bases

This directory hosts pinned upstream knowledge bases. They are **read-only
reference material**, not first-class Decepticon skills. Agents should:

1. Try the domain-specific skill first (e.g. `skills/exploit/web/ssrf/SKILL.md`).
2. If the domain skill lacks payload variants, encoding bypasses, or
   tool-specific syntax → cross-reference the corresponding upstream README
   under this directory.
3. Findings derived from corpus content must still be evidence-validated by
   the verifier agent. Corpus payloads are starting points, not proof.

## Available corpora

### `payloads/` — PayloadsAllTheThings (swisskyrepo, MIT)

77.8k⭐, 64+ vuln-class READMEs, pinned via git submodule. The canonical
public payload catalog. Run `git submodule update --remote skills/_corpus/payloads`
to refresh to upstream HEAD.

When a Decepticon domain leaf references a payload class, the SKILL.md
should cite the corresponding `payloads/<class>/README.md` path so agents
can drill down for additional variants.

#### High-frequency cross-references

| Decepticon leaf | Corpus path |
|---|---|
| `skills/exploit/web/ssrf/` | `payloads/Server Side Request Forgery/` |
| `skills/exploit/web/sqli/` | `payloads/SQL Injection/` |
| `skills/exploit/web/xss/` | `payloads/XSS Injection/` |
| `skills/exploit/web/jwt/` | `payloads/JSON Web Token/` |
| `skills/exploit/web/oauth/` | `payloads/OAuth Misconfiguration/` |
| `skills/exploit/web/saml/` | `payloads/SAML Injection/` |
| `skills/exploit/web/cache-deception/` | `payloads/Web Cache Deception/` |
| `skills/exploit/web/smuggling/` | `payloads/Request Smuggling/` |
| `skills/exploit/web/race-condition/` | `payloads/Race Condition/` |
| `skills/exploit/web/file-upload/` | `payloads/Upload Insecure Files/` |
| `skills/exploit/supplychain/dep-confusion/` | `payloads/Dependency Confusion/` |

### Refresh protocol

```bash
# Pull upstream payload updates
git submodule update --remote skills/_corpus/payloads

# Detect new vuln-class directories that don't have a Decepticon leaf mapping
python3 scripts/ingest_corpus.py --report
```

The ingest script writes `skills/_corpus/.manifest.json` mapping each upstream
class to its Decepticon leaf (or `NEW` if no leaf maps yet). CI emits a
warning on drift; weekly cron opens a GH issue listing new classes.

## License

PayloadsAllTheThings is MIT-licensed. Redistribution within Decepticon
preserves the upstream `LICENSE` file inside the submodule. See
`THIRD_PARTY_LICENSES.md` at repo root for the full attribution.
