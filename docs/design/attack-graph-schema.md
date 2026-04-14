# Attack Graph Schema — Neo4j Native Design

## 1. What is an Attack Graph?

An attack graph is a directed graph that models all possible attack paths through a target environment. Each node represents a **state** (asset, vulnerability, credential, or technique), and each edge represents a **transition** an attacker can take to move from one state to another. The graph serves as the agent's operational map — answering "where am I, what can I reach, and what's the cheapest path to the crown jewel?"

### Red Team Context

In professional red team operations, attack graphs model the **kill chain progression**:

1. **Reconnaissance** — discover hosts, services, endpoints
2. **Weaponization** — identify vulnerabilities and misconfigurations
3. **Delivery/Exploitation** — exploit vulnerabilities for initial access
4. **Privilege Escalation** — elevate from user to admin/root
5. **Lateral Movement** — pivot to adjacent hosts using credentials
6. **Collection/Exfiltration** — reach crown jewels (databases, secrets, domain admin)

The graph encodes these progressions as weighted paths, where edge weight represents **exploitation difficulty** (lower = easier).

### Reference Implementations

- **BloodHound CE**: Neo4j-based AD attack path analysis. Uses individual node labels (Computer, User, Group, Domain, GPO) with relationship types (MemberOf, AdminTo, HasSession, CanRDP, GenericAll). Gold standard for AD path visualization.
- **BRON**: Links ATT&CK tactics → techniques → CVEs → CWEs → CAPEC patterns in a unified graph.
- **MITRE ATT&CK Navigator**: Tactic → technique mapping, but not a graph DB.

### Decepticon's Extension

Decepticon extends BloodHound's proven approach beyond AD to cover:
- Web application vulnerabilities (SSRF, SQLi, IDOR, SSTI, XSS)
- Cloud infrastructure (AWS IAM, K8s RBAC, Terraform state)
- Smart contracts (reentrancy, oracle manipulation, flash loan)
- Binary exploitation (ROP, format strings, heap overflow)
- General CVE/vulnerability management

All unified in **one graph** that the agent queries for attack path reasoning.

---

## 2. Node Labels (Neo4j Native)

Each node type gets its own Neo4j label for native indexing and constraint enforcement. All nodes also carry a shared `:Asset` or `:Finding` meta-label for polymorphic queries.

### Infrastructure Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:Host` | Physical/virtual machine, container | `ip`, `hostname`, `os`, `explored: bool`, `compromised: bool`, `domain` |
| `:Network` | Network segment / CIDR | `cidr`, `name`, `vlan` |
| `:Domain` | DNS domain or AD domain | `fqdn`, `type: {dns, ad}`, `forest` |
| `:Service` | Running service on a host | `port`, `protocol`, `product`, `version`, `state`, `banner` |
| `:URL` | Web endpoint | `url`, `method`, `status_code`, `tech_stack` |
| `:CloudResource` | AWS/GCP/Azure resource | `provider`, `arn`, `resource_type`, `region`, `account_id` |
| `:Container` | Docker/K8s container | `image`, `namespace`, `pod`, `privileged: bool` |

### Identity Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:User` | Human or service account | `username`, `sid`, `enabled: bool`, `admin: bool`, `domain` |
| `:Group` | AD group, IAM role, K8s RBAC role | `name`, `sid`, `scope`, `type: {security, distribution}` |
| `:Credential` | Obtained credential | `type: {password, hash, ticket, token, key, cookie}`, `hash_type`, `cracked: bool`, `value_redacted` |
| `:Secret` | Exposed secret (API key, cert, etc.) | `kind`, `source`, `sensitivity` |
| `:Session` | Active session (RDP, SSH, web) | `type`, `source_host`, `target_host`, `user` |

### Vulnerability Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:Vulnerability` | Discovered weakness | `vuln_class`, `severity`, `cvss`, `description`, `validated: bool`, `exploited: bool` |
| `:CVE` | Known CVE entry | `cve_id`, `cvss`, `epss`, `kev: bool`, `description`, `affected_product` |
| `:Misconfiguration` | Security misconfiguration | `type`, `severity`, `description`, `remediation` |
| `:Weakness` | CWE weakness class | `cwe_id`, `name`, `description` |

### Code Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:Repository` | Source code repo | `url`, `language`, `branch` |
| `:SourceFile` | File in a repo | `path`, `language`, `lines` |
| `:CodeLocation` | Specific code point (line range) | `file`, `start_line`, `end_line`, `function`, `snippet` |
| `:Contract` | Smart contract | `address`, `network`, `compiler`, `verified: bool` |

### Attack Progression Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:Technique` | MITRE ATT&CK technique | `technique_id`, `tactic`, `name`, `description` |
| `:Entrypoint` | Initial access vector | `type`, `description`, `confidence` |
| `:CrownJewel` | High-value target | `type`, `description`, `business_impact` |
| `:AttackPath` | Computed multi-hop attack chain | `total_cost`, `length`, `validated: bool`, `description` |
| `:Finding` | Verified, reportable finding | `title`, `severity`, `cvss`, `status: {confirmed, reported, remediated}` |

### Analysis Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:Candidate` | Scanner-emitted suspect location | `suspicion_score`, `source_tool`, `status: {pending, promoted, rejected}` |
| `:Hypothesis` | Unverified theory about a vulnerability | `confidence`, `evidence`, `status: {active, confirmed, rejected}` |
| `:Patch` | Proposed/applied fix | `diff`, `verified: bool`, `poc_still_works: bool` |

### Defense Layer

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `:DefenseAction` | Executed defensive measure | `action_type`, `target`, `parameters: map`, `status: {pending, applied, rolled_back, failed}`, `executed_at`, `rollback_command`, `finding_ref` |

---

## 3. Relationship Types

### Topology (Infrastructure Discovery)

| Relationship | Direction | Description | Weight |
|-------------|-----------|-------------|--------|
| `HOSTS` | Host → Service | Host runs this service | - |
| `RESOLVES_TO` | Domain → Host | DNS resolution | - |
| `CONTAINS` | Network → Host | Network segment membership | - |
| `EXPOSES` | Service → URL | Service exposes this endpoint | - |
| `ROUTES_TO` | Network → Network | Reachability between segments | - |
| `PART_OF` | Container → Host | Container runs on host | - |
| `MANAGES` | CloudResource → CloudResource | IAM/control plane relationship | - |

### Access & Authentication

| Relationship | Direction | Description | Weight |
|-------------|-----------|-------------|--------|
| `AUTHENTICATES_TO` | Credential → User | Credential grants identity | 0.1 |
| `HAS_SESSION` | User → Host | Active session exists | 0.2 |
| `MEMBER_OF` | User → Group | Group membership (AD/IAM) | - |
| `CAN_ACCESS` | User → Service/Host | Authorized access | 0.3 |
| `ADMIN_TO` | User → Host | Administrative access | 0.1 |
| `OWNS` | User → CloudResource | Cloud resource ownership | - |

### Exploitation

| Relationship | Direction | Description | Weight |
|-------------|-----------|-------------|--------|
| `AFFECTS` | CVE → Service/Product | CVE affects this target | - |
| `HAS_VULN` | Service/URL/SourceFile → Vulnerability | Vulnerability exists here | - |
| `EXPLOITS` | Technique → Vulnerability | Technique exploits this vuln | cost |
| `ENABLES` | Vulnerability → Vulnerability | Exploiting A unlocks B | cost |
| `LEAKS` | Vulnerability → Credential/Secret | Exploitation leaks credential | cost |
| `LEADS_TO` | Vulnerability → User/Host | Exploitation grants access | cost |
| `DEFINED_IN` | Vulnerability → CodeLocation | Vuln exists at this code location | - |
| `INSTANCE_OF` | Vulnerability → Weakness(CWE) | Vuln is instance of weakness class | - |

### Kill Chain Progression

| Relationship | Direction | Description | Weight |
|-------------|-----------|-------------|--------|
| `PIVOTS_TO` | Host → Host | Lateral movement via credential/session | cost |
| `ESCALATES_TO` | User → User | Privilege escalation path | cost |
| `REACHES` | AttackPath → CrownJewel | Path reaches high-value target | - |
| `STARTS_AT` | AttackPath → Entrypoint | Path begins here | - |
| `STEP` | AttackPath → Finding | Path includes this finding | `{order: N}` |
| `USES` | Finding → Technique | Finding uses ATT&CK technique | - |

### Validation & Remediation

| Relationship | Direction | Description | Weight |
|-------------|-----------|-------------|--------|
| `VALIDATES` | Finding → Vulnerability | PoC confirms vulnerability | - |
| `DERIVED_FROM` | Vulnerability → Candidate | Promoted from candidate | - |
| `PATCHES` | Patch → Vulnerability | Fix for this vulnerability | - |
| `MAPS_TO` | Finding → CVE | Finding corresponds to known CVE | - |

### Defense

| Relationship | Direction | Description | Weight |
|-------------|-----------|-------------|--------|
| `MITIGATES` | DefenseAction → Vulnerability | Defense action addresses this vulnerability | - |
| `DEFENDS` | DefenseAction → Host/Service | Defense action protects this asset | - |
| `RESPONDS_TO` | DefenseAction → Finding | Defense action responds to this finding | - |

---

## 4. Weight / Cost Model

Edge weights encode **exploitation difficulty** for path-finding algorithms:

```
cost = base_weight × severity_multiplier × validation_discount

severity_multiplier:
  critical: 0.4  (easiest to exploit — known working exploits)
  high:     0.6
  medium:   1.0
  low:      1.6
  info:     2.5

validation_discount:
  validated PoC exists: ×0.5
  no PoC:               ×1.0
```

Relationships carrying `cost` property are traversable by path-finding. Relationships without `cost` are structural (topology, membership) and don't contribute to attack path calculation.

---

## 5. Constraints & Indexes

```cypher
// ── Uniqueness Constraints ──────────────────────────────────────────
CREATE CONSTRAINT host_ip IF NOT EXISTS FOR (h:Host) REQUIRE h.ip IS UNIQUE;
CREATE CONSTRAINT domain_fqdn IF NOT EXISTS FOR (d:Domain) REQUIRE d.fqdn IS UNIQUE;
CREATE CONSTRAINT network_cidr IF NOT EXISTS FOR (n:Network) REQUIRE n.cidr IS UNIQUE;
CREATE CONSTRAINT service_key IF NOT EXISTS FOR (s:Service) REQUIRE s.key IS UNIQUE;
CREATE CONSTRAINT url_normalized IF NOT EXISTS FOR (u:URL) REQUIRE u.url IS UNIQUE;
CREATE CONSTRAINT user_key IF NOT EXISTS FOR (u:User) REQUIRE u.key IS UNIQUE;
CREATE CONSTRAINT cve_id IF NOT EXISTS FOR (c:CVE) REQUIRE c.cve_id IS UNIQUE;
CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (w:Weakness) REQUIRE w.cwe_id IS UNIQUE;
CREATE CONSTRAINT technique_id IF NOT EXISTS FOR (t:Technique) REQUIRE t.technique_id IS UNIQUE;
CREATE CONSTRAINT vuln_key IF NOT EXISTS FOR (v:Vulnerability) REQUIRE v.key IS UNIQUE;
CREATE CONSTRAINT finding_key IF NOT EXISTS FOR (f:Finding) REQUIRE f.key IS UNIQUE;
CREATE CONSTRAINT credential_key IF NOT EXISTS FOR (c:Credential) REQUIRE c.key IS UNIQUE;
CREATE CONSTRAINT cloud_arn IF NOT EXISTS FOR (cr:CloudResource) REQUIRE cr.arn IS UNIQUE;
CREATE CONSTRAINT contract_addr IF NOT EXISTS FOR (c:Contract) REQUIRE c.address IS UNIQUE;
CREATE CONSTRAINT attack_path_key IF NOT EXISTS FOR (ap:AttackPath) REQUIRE ap.key IS UNIQUE;

// ── Performance Indexes ─────────────────────────────────────────────
CREATE INDEX host_explored IF NOT EXISTS FOR (h:Host) ON (h.explored);
CREATE INDEX host_compromised IF NOT EXISTS FOR (h:Host) ON (h.compromised);
CREATE INDEX service_product IF NOT EXISTS FOR (s:Service) ON (s.product, s.version);
CREATE INDEX vuln_severity IF NOT EXISTS FOR (v:Vulnerability) ON (v.severity);
CREATE INDEX vuln_validated IF NOT EXISTS FOR (v:Vulnerability) ON (v.validated);
CREATE INDEX vuln_class IF NOT EXISTS FOR (v:Vulnerability) ON (v.vuln_class);
CREATE INDEX finding_status IF NOT EXISTS FOR (f:Finding) ON (f.status);
CREATE INDEX candidate_status IF NOT EXISTS FOR (c:Candidate) ON (c.status);
CREATE INDEX credential_cracked IF NOT EXISTS FOR (c:Credential) ON (c.cracked);
CREATE INDEX technique_tactic IF NOT EXISTS FOR (t:Technique) ON (t.tactic);
CREATE INDEX user_admin IF NOT EXISTS FOR (u:User) ON (u.admin);

// ── Full-Text Search ────────────────────────────────────────────────
CALL db.index.fulltext.createNodeIndex("vuln_search", ["Vulnerability", "Finding"], ["description", "title"]);
```

---

## 6. Core Cypher Query Patterns

### Q1. Shortest Attack Path (Entry → Crown Jewel)

```cypher
// Find cheapest attack path from any Entrypoint to any CrownJewel
MATCH (entry:Entrypoint), (crown:CrownJewel)
CALL apoc.algo.dijkstra(entry, crown, 'EXPLOITS|ENABLES|LEAKS|LEADS_TO|PIVOTS_TO|ESCALATES_TO', 'cost')
YIELD path, weight
RETURN entry.description AS entry,
       crown.description AS target,
       weight AS total_cost,
       [n IN nodes(path) | labels(n)[0] + ': ' + coalesce(n.label, n.ip, n.username, n.title, '')] AS path_labels
ORDER BY weight ASC
LIMIT 5
```

### Q2. Unexplored Attack Surface

```cypher
// Hosts with services that have no vulnerability analysis yet
MATCH (h:Host)-[:HOSTS]->(s:Service)
WHERE NOT (s)-[:HAS_VULN]->()
  AND h.explored = false
RETURN h.ip, h.hostname, collect(s.port + '/' + s.product) AS open_services
ORDER BY size(collect(s.port)) DESC
```

### Q3. Credential Reachability (Pass-the-Hash / Credential Reuse)

```cypher
// From a cracked credential, what hosts/services are reachable?
MATCH (cred:Credential {cracked: true})-[:AUTHENTICATES_TO]->(u:User)
OPTIONAL MATCH (u)-[:CAN_ACCESS|ADMIN_TO]->(target)
OPTIONAL MATCH (u)-[:HAS_SESSION]->(session_host:Host)
RETURN cred.type AS cred_type,
       u.username AS identity,
       collect(DISTINCT labels(target)[0] + ': ' + coalesce(target.ip, target.name, '')) AS accessible_targets,
       collect(DISTINCT session_host.ip) AS active_sessions
```

### Q4. Impact Analysis (What does compromising X enable?)

```cypher
// If we exploit vulnerability V, what becomes reachable?
MATCH (v:Vulnerability {key: $vuln_key})
CALL apoc.path.expandConfig(v, {
  relationshipFilter: 'ENABLES>|LEAKS>|LEADS_TO>|PIVOTS_TO>|ESCALATES_TO>',
  maxLevel: 4,
  uniqueness: 'NODE_GLOBAL'
})
YIELD path
WITH last(nodes(path)) AS reachable, length(path) AS depth
RETURN labels(reachable)[0] AS type,
       coalesce(reachable.label, reachable.ip, reachable.username, reachable.title) AS name,
       depth
ORDER BY depth ASC
```

### Q5. Lateral Movement Paths (Host-to-Host Pivoting)

```cypher
// All lateral movement paths from compromised host to target host
MATCH (src:Host {compromised: true}), (dst:Host {ip: $target_ip})
MATCH path = shortestPath((src)-[:PIVOTS_TO|ESCALATES_TO*..6]->(dst))
RETURN [n IN nodes(path) | n.ip + ' (' + coalesce(n.hostname, '') + ')'] AS pivot_chain,
       length(path) AS hops,
       reduce(cost = 0.0, r IN relationships(path) | cost + coalesce(r.cost, 1.0)) AS total_cost
ORDER BY total_cost ASC
LIMIT 10
```

### Q6. Kill Chain Coverage Assessment

```cypher
// Which ATT&CK tactics have confirmed findings?
MATCH (f:Finding)-[:USES]->(t:Technique)
RETURN t.tactic AS tactic,
       count(DISTINCT f) AS findings_count,
       collect(DISTINCT t.name) AS techniques_used
ORDER BY CASE t.tactic
  WHEN 'initial-access' THEN 1
  WHEN 'execution' THEN 2
  WHEN 'persistence' THEN 3
  WHEN 'privilege-escalation' THEN 4
  WHEN 'credential-access' THEN 5
  WHEN 'lateral-movement' THEN 6
  WHEN 'collection' THEN 7
  WHEN 'exfiltration' THEN 8
  WHEN 'impact' THEN 9
  ELSE 10
END
```

### Q7. Crown Jewel Risk Score

```cypher
// Score each crown jewel by number of viable attack paths
MATCH (crown:CrownJewel)
OPTIONAL MATCH path = (entry:Entrypoint)-[:EXPLOITS|ENABLES|LEAKS|LEADS_TO|PIVOTS_TO|ESCALATES_TO*..8]->(crown)
WITH crown, count(path) AS path_count,
     min(reduce(c = 0.0, r IN relationships(path) | c + coalesce(r.cost, 1.0))) AS min_cost
RETURN crown.description AS target,
       crown.business_impact AS impact,
       path_count AS viable_paths,
       round(min_cost * 100) / 100 AS cheapest_path_cost
ORDER BY path_count DESC, min_cost ASC
```

### Q8. Defense Coverage Assessment

```cypher
// Which findings have been mitigated vs still open?
MATCH (f:Finding)
OPTIONAL MATCH (da:DefenseAction)-[:RESPONDS_TO]->(f)
WITH f, collect(da) AS defenses,
     CASE WHEN size(collect(da)) > 0 THEN 'mitigated' ELSE 'open' END AS status
RETURN f.title AS finding,
       f.severity AS severity,
       status,
       [d IN defenses | d.action_type + ' → ' + d.target] AS defense_actions
ORDER BY CASE f.severity
  WHEN 'critical' THEN 1
  WHEN 'high' THEN 2
  WHEN 'medium' THEN 3
  WHEN 'low' THEN 4
  ELSE 5
END
```

---

## 7. Migration from Current Schema

### Current → New Mapping

| Current (KGNode) | New (Individual Label) |
|-------------------|----------------------|
| `NodeKind.HOST` | `:Host` |
| `NodeKind.SERVICE` | `:Service` |
| `NodeKind.URL` | `:URL` |
| `NodeKind.REPO` | `:Repository` |
| `NodeKind.FILE` | `:SourceFile` |
| `NodeKind.CODE_LOCATION` | `:CodeLocation` |
| `NodeKind.VULNERABILITY` | `:Vulnerability` |
| `NodeKind.CVE` | `:CVE` |
| `NodeKind.FINDING` | `:Finding` |
| `NodeKind.CREDENTIAL` | `:Credential` |
| `NodeKind.SECRET` | `:Secret` |
| `NodeKind.USER` | `:User` |
| `NodeKind.ENTRYPOINT` | `:Entrypoint` |
| `NodeKind.CROWN_JEWEL` | `:CrownJewel` |
| `NodeKind.CHAIN` | `:AttackPath` |
| `NodeKind.HYPOTHESIS` | `:Hypothesis` |
| `NodeKind.CANDIDATE` | `:Candidate` |
| `NodeKind.PATCH` | `:Patch` |

### New Node Types (added)

| Label | Reason |
|-------|--------|
| `:Network` | Network segmentation for lateral movement reasoning |
| `:Domain` | DNS/AD domain for domain-level attacks |
| `:CloudResource` | AWS/GCP/Azure resources for cloud attack paths |
| `:Container` | Docker/K8s for container escape paths |
| `:Group` | AD groups / IAM roles for permission chain analysis |
| `:Session` | Active sessions for session hijacking / pass-the-hash |
| `:Misconfiguration` | Non-CVE security issues (open S3, default creds) |
| `:Weakness` | CWE mapping for vulnerability classification |
| `:Technique` | MITRE ATT&CK technique mapping |
| `:Contract` | Smart contract for DeFi attack graphs |
| `:DefenseAction` | Defensive measures for the offensive vaccine feedback loop |

### Relationship Mapping

| Current (KG_EDGE) | New (Native Relationship) |
|--------------------|--------------------------|
| `runs_on` | `HOSTS` (reversed: Host → Service) |
| `exposes` | `EXPOSES` |
| `has_vuln` | `HAS_VULN` |
| `defined_in` | `DEFINED_IN` |
| `located_at` | → merged into `DEFINED_IN` |
| `affected_by` | `AFFECTS` (reversed: CVE → Service) |
| `mapped_to` | `MAPS_TO` |
| `auth_as` | `AUTHENTICATES_TO` |
| `grants` | `CAN_ACCESS` |
| `leaks` | `LEAKS` |
| `enables` | `ENABLES` |
| `chains_to` | `STEP` (with `order` property) |
| `reaches` | `REACHES` |
| `starts_at` | `STARTS_AT` |
| `contains` | `STEP` |
| `validates` | `VALIDATES` |
| `derived_from` | `DERIVED_FROM` |
| `patches` | `PATCHES` |

### New Relationships (added)

| Relationship | Reason |
|-------------|--------|
| `RESOLVES_TO` | DNS → Host for recon chain |
| `ROUTES_TO` | Network → Network for segmentation |
| `MEMBER_OF` | User → Group for permission chains |
| `HAS_SESSION` | User → Host for session-based attacks |
| `ADMIN_TO` | User → Host for admin path analysis |
| `OWNS` | User → CloudResource for cloud privilege |
| `PIVOTS_TO` | Host → Host for lateral movement |
| `ESCALATES_TO` | User → User for privilege escalation |
| `LEADS_TO` | Vulnerability → User/Host for exploitation outcome |
| `EXPLOITS` | Technique → Vulnerability for ATT&CK mapping |
| `USES` | Finding → Technique for kill chain coverage |
| `INSTANCE_OF` | Vulnerability → Weakness for CWE classification |
| `MANAGES` | CloudResource → CloudResource for cloud control plane |
| `PART_OF` | Container → Host for container topology |
| `MITIGATES` | DefenseAction → Vulnerability for defense tracking |
| `DEFENDS` | DefenseAction → Host/Service for asset protection |
| `RESPONDS_TO` | DefenseAction → Finding for finding-to-defense mapping |
