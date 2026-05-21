---
name: ad-overview
description: Active Directory attack lane — BloodHound ingestion, Kerberoasting, ADCS ESC scanning, DCSync, LAPS extraction.
---

# AD Operator Skill Catalog

## Playbooks
| Skill | Use for |
|---|---|
| `/skills/standard/ad/bloodhound-query/SKILL.md` | Ingest + common Cypher queries |
| `/skills/standard/ad/kerberoasting/SKILL.md`    | Roast SPN users, crack with hashcat |
| `/skills/standard/ad/asrep-roasting/SKILL.md`   | dontreqpreauth users |
| `/skills/standard/ad/adcs-esc1/SKILL.md`        | ESC1 template abuse → domain admin |
| `/skills/standard/ad/dcsync/SKILL.md`           | Replication rights → krbtgt dump |
| `/skills/standard/ad/laps/SKILL.md`             | LAPS local admin password extraction |

## Workflow
1. Collect: `bash("bloodhound-python -u user -p pass -d DOMAIN -c all --zip")`
2. `bh_ingest_zip("/workspace/bh.zip")`
3. `dcsync_check` — if any principal, that's instant domain compromise
4. `kg_query(kind="user")` and filter for `hasspn=true` → Kerberoast queue
5. `kg_query(kind="user")` and filter for `dontreqpreauth=true` → AS-REP roast
6. ADCS: `bash("certipy find -u user -p pass -dc-ip X -json")` then `adcs_audit`
7. `plan_attack_chains` to see graph-computed domain compromise paths

## Crown jewels to add
```
kg_add_node(kind="crown_jewel", label="Domain Admins group")
kg_add_node(kind="crown_jewel", label="krbtgt account")
kg_add_node(kind="crown_jewel", label="DC: DC01.corp.local")
```
