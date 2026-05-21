---
name: pattern-exhaustion
description: Systematic pattern exhaustion methodology. Load after finding any confirmed vulnerability to search for all instances of the same root cause pattern across the codebase.
---

# Pattern Exhaustion

When you find a vulnerability, you have found a PATTERN. The same developer
who wrote one broken auth check likely wrote twenty. The same framework that
misses one guard has a systemic design gap. One root cause → multiple CVEs.

Real-world examples:
- Parse Server: 4 advisories from guard bypass patterns (prototype chain,
  falsy-value guard, protected-field bypass, complexity validator)
- zrok: 3 advisories from access control (symlink traversal, broken ownership,
  reflected XSS in callback)
- AVideo: 3 advisories from deployment config (SSRF, exposed installer,
  memcached session leak)

## The Exhaustion Loop

### 1. Classify the root cause

After confirming a vulnerability, classify its root cause pattern:

| Root Cause | Search Pattern |
|---|---|
| Missing auth/authz check | `grep -rn 'def handle_\|router\.\(get\|post\|put\|delete\)' \| grep -v 'auth\|permission\|require\|middleware'` |
| Unvalidated path parameter | `grep -rn 'req\.params\|request\.args\|ctx\.params' \| grep -v 'sanitize\|validate\|path\.resolve\|path\.normalize'` |
| SQL string interpolation | `grep -rn 'f"SELECT\|f"INSERT\|f"UPDATE\|query(.*\+.*\|query(.*\$\{' --include='*.py' --include='*.ts' --include='*.js'` |
| shell: true with user input | `grep -rn 'shell:\s*true\|shell=True\|os\.system\|subprocess\.call.*shell' --include='*.py' --include='*.ts' --include='*.js'` |
| Missing ownership validation | `grep -rn 'delete\|update\|modify' --include='*.py' --include='*.ts' \| grep -v 'owner\|author\|created_by\|user_id.*=='` |
| Default-open feature flag | `grep -rn 'enabled.*=.*false\|feature.*disabled\|trust.*=.*true' --include='*.ts' --include='*.py'` |
| Unsafe deserialization | `grep -rn 'pickle\.loads\|yaml\.load\|yaml\.unsafe\|unserialize\|JSON\.parse.*reviver\|eval(' --include='*.py' --include='*.js' --include='*.php'` |
| Type confusion in guard | `grep -rn 'typeof.*==\|instanceof\|is_array\|Array\.isArray' --include='*.ts' --include='*.js' --include='*.php'` |
| Missing CSRF/state check | `grep -rn 'state=\|csrf\|nonce' --include='*.py' --include='*.ts' \| grep -v 'verify\|validate\|check'` |
| Prototype pollution | `grep -rn 'Object\.assign\|merge(\|extend(\|deepMerge\|_.merge\|lodash' --include='*.js' --include='*.ts'` |

For semgrep (when installed):
```bash
# Generic: user input reaching dangerous sink without sanitization
semgrep --config auto --severity ERROR /workspace/target/src/ --sarif -o /workspace/exhaustion.sarif
kg_ingest_sarif("/workspace/exhaustion.sarif", "pattern-exhaustion")
```

### 2. Enumerate all instances

Run the search. For EACH hit:
1. Check: is this the SAME pattern as the confirmed vuln?
2. Check: is there a mitigation the original instance lacked?
3. Check: is this in test/fixture/example code? (reject if so)
4. If potentially exploitable, create a HYPOTHESIS node:

```
kg_add_node("hypothesis", "Missing ownership check in DELETE /api/v2/unaccess",
  props={"pattern": "missing_ownership_validation", "file": "api/routes.py",
  "line": 87, "related_finding": "<original_finding_id>",
  "key": "api/routes.py:handle_unaccess:missing_ownership"})
```

Link to the original vulnerability:
```
kg_add_edge(new_hypothesis_id, original_vuln_id, "chains_to", weight=0.3)
```

### 3. Prioritize by impact

Not all instances are equal. Prioritize:
- **Unauthenticated endpoints** over authenticated ones
- **Write/delete operations** over read-only
- **Production code paths** over admin/debug routes
- **External-facing** over internal-only

### 4. Verify each instance

Feed the top candidates to the verifier via `validate_finding`. Each
confirmed instance becomes a separate FINDING node.

### 5. Exhaustion criteria

Stop the pattern search when:
- All instances have been checked (grep returns no unchecked matches)
- Remaining instances have proper mitigations in place
- The pattern no longer applies (different framework version, different code path)
- You've hit 10+ findings from the same pattern (diminishing returns on signal)

Record the exhaustion state:
```
kg_add_node("hypothesis", "pattern exhaustion complete: missing_ownership",
  props={"pattern": "missing_ownership_validation", "status": "exhausted",
  "total_instances": 15, "confirmed": 4, "rejected": 11})
```

## Graph Structure

After exhaustion, the graph should show:
```
VULNERABILITY (original finding)
  ← chains_to ← FINDING (variant 1)
  ← chains_to ← FINDING (variant 2)
  ← chains_to ← FINDING (variant 3)
  ← chains_to ← HYPOTHESIS (rejected variant, status=rejected)
```

This makes it easy for the report generator to group related findings
under a single root cause narrative.
