# skillogy: load_skill by name 404s when find_skill ranking is polluted

**Date:** 2026-06-12
**Component:** `decepticon/skillogy/server/` (`app.py` load endpoint + `neo4j_backend.load_skill`)
**Severity:** high — agents cannot load known skills by name; breaks orchestrator skill-routing

## Symptom

`load_skill("oauth")` and `load_skill("ssrf")` return 404 ("no Skill with name
or path matching …") even though a `:Skill` node with `name="oauth"` exists,
while `load_skill("sqli")` / `load_skill("idor")` / `load_skill("xss")` succeed.
The failures are non-deterministic per skill name and depend on the rest of the
ingested corpus.

Live impact (bugclaw orchestrator skill-routing, 8x8-bounty engagement): the
orchestrator classified recon's surface, called `find_skill` + `load_skill`
~20×, every `load_skill` failed (by name AND by guessed path), and it never
dispatched a hunting `task()` — the pipeline stalled at skill selection.

## Root cause — name resolution goes through a polluted keyword search

The `/v1/skills:load` endpoint resolved a NAME (anything not starting with
`/skills/`) by running `find_skill(query=name, limit=10)` and filtering its hits
for an exact-`name` match:

```python
hits = backend.find_skill(query=target, limit=10, allowed_path_prefixes=allowed)
exact = [h for h in hits if h.get("name") == target]
if not exact:
    raise HTTPException(404, …)
```

`find_skill`'s `query` is a substring/keyword search over `name` /
`description` / `when_to_use`. In a graph that ingests BOTH the standard web
playbooks AND keyword-rich adversary-emulation (APT) skills, a query like
`"oauth"` matches the APT skills (apt28/apt29 descriptions mention OAuth token
theft, device-code phishing, etc.) and they **outrank the web `oauth` skill**,
pushing it past `limit=10` → `exact` is empty → 404. `"sqli"` happens to have no
high-ranking APT collisions, so it resolves. The behaviour is therefore a
function of corpus pollution, not of whether the skill exists.

`neo4j_backend.load_skill` itself only matched by canonical **path**
(`MATCH (s:Skill {path: $path})`), so it could not be used for a name directly,
and its `allowed_path_prefixes` ACL gated the *input* string — which rejects
every bare name (a name is not under `/skills/…`).

## Fix

Resolve a name with a direct, exact graph lookup instead of a ranked keyword
search.

1. `neo4j_backend.load_skill` now matches **path OR exact name** (path
   preferred) and applies the path-prefix ACL to the **resolved** skill's path,
   not the input:

   ```cypher
   MATCH (s:Skill) WHERE s.path = $arg OR s.name = $arg
   RETURN properties(s) AS props
   ORDER BY CASE WHEN s.path = $arg THEN 0 ELSE 1 END
   LIMIT 1
   ```

2. The `/v1/skills:load` endpoint calls `backend.load_skill(target)` directly
   for both path and name inputs (the find_skill-resolution dance is removed) —
   unambiguous and pollution-proof, with the ACL still enforced on the resolved
   path.

## Verification

Post-fix, every web playbook loads by bare name, with and without an ACL
prefix set:

```
name        bare    acl
oauth       LOAD    LOAD
ssrf        LOAD    LOAD
sqli/idor/xss/jwt/saml/xxe/bfla   LOAD   LOAD
```

## Follow-up (separate, lower severity)

`find_skill(query=…)` ranking is still polluted by APT skills for *discovery*
(unscoped `find_skill("oauth")` surfaces apt29 above the web oauth skill).
Callers should scope with `subdomain="web-exploitation"`; a ranking that
prefers exact-name / same-subdomain matches would make discovery robust too.
