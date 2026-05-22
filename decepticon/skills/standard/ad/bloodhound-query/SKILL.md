---
name: bloodhound-query
description: "BloodHound data collection, ingestion, and common attack path queries"
allowed-tools: Bash
metadata:
  subdomain: active-directory
  mitre_attack: T1087.002, T1069.002
  when_to_use: "bloodhound, sharphound, attack paths, domain enumeration, graph, cypher"
  tags: active-directory, bloodhound, enumeration, attack-paths
---

# BloodHound Query — Collection, Ingestion & Attack Path Analysis

## 1. Data Collection

**bloodhound-python (Linux)**
```bash
# Full collection — generates ZIP for ingestion
bloodhound-python -u '<USER>' -p '<PASS>' -d <DOMAIN> -ns <DC_IP> -c all --zip -o /workspace/

# Pass-the-hash collection
bloodhound-python -u '<USER>' --hashes ':<NT_HASH>' -d <DOMAIN> -ns <DC_IP> -c all --zip -o /workspace/

# DC-only (stealthier, no host enumeration)
bloodhound-python -u '<USER>' -p '<PASS>' -d <DOMAIN> -ns <DC_IP> -c DCOnly --zip -o /workspace/
```

**SharpHound (Windows)**
```powershell
SharpHound.exe -c All --outputdirectory C:\workspace\bloodhound\
SharpHound.exe -c DCOnly   # DC queries only — lowest noise
```

## 2. Ingestion

```python
# Ingest ZIP into KnowledgeGraph
bh_ingest_zip("/workspace/bh.zip")
```

After ingestion, all nodes (users, groups, computers, GPOs, OUs) are queryable via `kg_query`.

## 3. Common Attack Path Queries

### Shortest Path to Domain Admins
```python
kg_query(kind="user")
# Then via Cypher:
```
```bash
neo4j-cypher 'MATCH p=shortestPath((n {owned:true})-[*1..]->(g:Group {name:"DOMAIN ADMINS@<DOMAIN>"})) RETURN p'
```

### Kerberoastable Users
```bash
neo4j-cypher 'MATCH (u:User {hasspn:true}) RETURN u.name, u.serviceprincipalnames'
```

### Kerberoastable Users with Admin Paths
```bash
neo4j-cypher 'MATCH (u:User {hasspn:true})-[*1..5]->(g:Group {highvalue:true}) RETURN u.name, g.name'
```

### AS-REP Roastable Users
```bash
neo4j-cypher 'MATCH (u:User {dontreqpreauth:true}) RETURN u.name, u.description'
```

### Unconstrained Delegation
```bash
neo4j-cypher 'MATCH (c:Computer {unconstraineddelegation:true}) WHERE NOT c.name CONTAINS "DC" RETURN c.name'
```

### Constrained Delegation Targets
```bash
neo4j-cypher 'MATCH (c {allowedtodelegate:true}) RETURN c.name, c.allowedtodelegate'
```

### Principals with DCSync Rights
```bash
neo4j-cypher 'MATCH p=(n)-[:GetChanges|GetChangesAll*1..]->(d:Domain) RETURN n.name, labels(n)'
```

### High-Value Targets
```bash
neo4j-cypher 'MATCH (n {highvalue:true}) RETURN labels(n), n.name ORDER BY labels(n)'
```

### Users with Local Admin Rights
```bash
neo4j-cypher 'MATCH p=(u:User)-[:AdminTo]->(c:Computer) RETURN u.name, c.name'
```

## 4. Decision Gates

| Condition | Action |
|-----------|--------|
| Owned node has path to DA | Follow shortest path — prioritize the fewest hops |
| Kerberoastable user has admin path | Roast first, crack offline, then escalate |
| DCSync rights found | Skip everything else — `dcsync_check()` then `secretsdump.py` |
| Unconstrained delegation on non-DC | Coerce auth via PetitPotam/PrinterBug |

## Anti-Patterns
- Running SharpHound with `-c All` on a red team without prior stealth assessment — use `-c DCOnly` first.
- Collecting data but not ingesting — always call `bh_ingest_zip()` immediately.
- Querying without checking `dcsync_check()` output first — DCSync rights are the fastest path to domain compromise.
