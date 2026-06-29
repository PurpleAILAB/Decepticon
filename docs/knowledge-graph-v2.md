# Knowledge Graph v2

Decepticon's Knowledge Graph (KG) is a Neo4j-backed attack graph that serves as the agent's persistent operational memory. v2 extends the original schema with six new node types — **Domain**, **CloudResource**, **NetworkSegment**, **Session**, **Finding**, and **Campaign** — enabling multi-domain, multi-cloud, and campaign-scoped attack-path reasoning.

**Connection details:**

| Endpoint | URL |
|----------|-----|
| Bolt | `bolt://localhost:7687` |
| Browser | `http://localhost:7474` |
| Credentials | `neo4j` / `decepticon-graph` (`NEO4J_PASSWORD`) |

---

## 1. Schema Overview

### 1.1 Node Label Taxonomy

All nodes belong to one of five layers. Every node carries at least one Neo4j label; many also carry a meta-label (`:Asset` or `:Finding`) for polymorphic queries.

```
Infrastructure ─┬─ Host
                ├─ Service
                ├─ Domain          ← v2
                ├─ CloudResource   ← v2
                ├─ NetworkSegment  ← v2
                ├─ Container
                └─ URL

Identity ───────┬─ User
                ├─ Group
                ├─ Credential
                ├─ Secret
                └─ Session         ← v2

Vulnerability ──┬─ Vulnerability
                ├─ CVE
                ├─ Misconfiguration
                └─ Weakness (CWE)

Progression ────┬─ Technique (ATT&CK)
                ├─ Entrypoint
                ├─ CrownJewel
                ├─ AttackPath
                ├─ Finding         ← v2
                └─ Campaign        ← v2

Analysis ───────┬─ Candidate
                ├─ Hypothesis
                └─ Patch
```

### 1.2 v2 Node Definitions

#### Domain

Represents a DNS domain, Active Directory domain, or cloud identity domain (Entra ID tenant).

| Property | Type | Description |
|----------|------|-------------|
| `fqdn` | string | **Unique key.** Fully-qualified domain name |
| `type` | enum | `ad` \| `dns` \| `cloud` |
| `forest` | string | Parent AD forest FQDN (null for DNS/cloud) |
| `functional_level` | string | AD functional level (e.g. `Windows2016Domain`) |
| `trust_direction` | enum | `inbound` \| `outbound` \| `bidirectional` |
| `dc_count` | int | Number of discovered domain controllers |
| `discovered_at` | datetime | First discovery timestamp |
| `notes` | string | Free-form operator notes |

**Key relationships:**

| Relationship | Direction | Target | Meaning |
|-------------|-----------|--------|---------|
| `CONTAINS` | Domain → Host | Host is joined to this domain |
| `TRUSTS` | Domain → Domain | AD trust relationship |
| `MANAGES` | Domain → Group | Domain-scoped security group |
| `HAS_POLICY` | Domain → GPO | Group policy linkage |

#### CloudResource

Represents an AWS, GCP, or Azure cloud resource (EC2 instance, S3 bucket, IAM role, Lambda, RDS, K8s pod, etc.).

| Property | Type | Description |
|----------|------|-------------|
| `arn` | string | **Unique key.** AWS ARN, GCP resource path, or Azure resource ID |
| `provider` | enum | `aws` \| `gcp` \| `azure` |
| `resource_type` | string | Resource kind (`ec2`, `s3`, `iam-role`, `lambda`, `rds`, `k8s-pod`, etc.) |
| `region` | string | Cloud region |
| `account_id` | string | Cloud account / project / subscription ID |
| `tags` | string | JSON-encoded resource tags |
| `public_access` | bool | Whether the resource is publicly accessible |
| `encryption` | string | Encryption scheme (`aes-256`, `kms`, `none`) |
| `discovered_at` | datetime | First discovery timestamp |
| `notes` | string | Free-form operator notes |

**Key relationships:**

| Relationship | Direction | Target | Meaning |
|-------------|-----------|--------|---------|
| `HOSTED_IN` | CloudResource → Region | Cloud region placement |
| `ATTACHED_TO` | CloudResource → CloudResource | Attachment (EBS→EC2, ENI→EC2) |
| `ASSUMES` | CloudResource → CloudResource | IAM role assumption chain |
| `EXPOSES` | CloudResource → Service | Publicly exposed service/port |
| `STORES` | CloudResource → Secret | Secrets in S3, SSM, Vault |
| `PART_OF` | CloudResource → NetworkSegment | VPC/subnet membership |

#### NetworkSegment

Represents a VLAN, subnet, VPC, or logical network zone used for segmentation-aware attack-path reasoning.

| Property | Type | Description |
|----------|------|-------------|
| `cidr` | string | **Unique key.** CIDR notation (`10.0.1.0/24`) |
| `name` | string | Human-friendly label (`corp-lan`, `dmz`, `ot-scada`) |
| `vlan_id` | int | 802.1Q VLAN identifier |
| `zone` | enum | `internal` \| `dmz` \| `external` \| `ot` \| `mgmt` |
| `gateway` | string | Default gateway IP |
| `provider` | string | `on-prem` \| `aws-vpc` \| `azure-vnet` \| `gcp-vpc` |
| `vpc_id` | string | Cloud VPC/VNet identifier |
| `acl_policy` | string | JSON-encoded ACL summary |
| `discovered_at` | datetime | First discovery timestamp |
| `notes` | string | Free-form operator notes |

**Key relationships:**

| Relationship | Direction | Target | Meaning |
|-------------|-----------|--------|---------|
| `CONTAINS` | NetworkSegment → Host | Host resides in this segment |
| `PEERS_WITH` | NetworkSegment → NetworkSegment | Routed/peered segments |
| `FILTERED_BY` | NetworkSegment → Host | Firewall/ACL appliance boundary |
| `PART_OF` | NetworkSegment → Domain | Segment belongs to a domain |

#### Session

Represents an active or captured authentication session (SSH, RDP, web, Kerberos TGT, NTLM, VPN).

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | string | **Unique key.** Opaque session identifier |
| `type` | enum | `ssh` \| `rdp` \| `web` \| `kerberos` \| `ntlm` \| `vpn` |
| `source_ip` | string | Originating IP |
| `target_ip` | string | Destination IP |
| `username` | string | Authenticated identity |
| `elevated` | bool | Session runs as admin/root |
| `created_at` | datetime | Session establishment time |
| `expires_at` | datetime | Expiry / ticket lifetime |
| `token` | string | Redacted auth token / ticket hash |
| `hijacked` | bool | Whether the session was hijacked by the operator |
| `notes` | string | Free-form operator notes |

**Key relationships:**

| Relationship | Direction | Target | Meaning |
|-------------|-----------|--------|---------|
| `ORIGINATES_FROM` | Session → Host | Source host |
| `TARGETS` | Session → Host | Destination host |
| `AUTHENTICATED_AS` | Session → User | Identity behind session |
| `USES_CREDENTIAL` | Session → Credential | Credential used to establish |
| `ESTABLISHED_VIA` | Session → Service | Service (SSH, RDP port) |

#### Finding

Represents a verified, reportable security finding — the unit of output in an engagement report.

| Property | Type | Description |
|----------|------|-------------|
| `finding_id` | string | **Unique key.** Deterministic ID |
| `title` | string | Human-readable finding title |
| `severity` | enum | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `cvss` | float | CVSS 3.1 base score |
| `status` | enum | `confirmed` \| `reported` \| `remediated` \| `accepted_risk` |
| `description` | string | Detailed description |
| `evidence` | string | Path to proof artifact / artifact URI |
| `remediation` | string | Recommended fix |
| `cwe_id` | string | Associated CWE identifier |
| `discovered_at` | datetime | Discovery timestamp |
| `reported_at` | datetime | Report submission timestamp |
| `notes` | string | Free-form operator notes |

**Key relationships:**

| Relationship | Direction | Target | Meaning |
|-------------|-----------|--------|---------|
| `AFFECTS` | Finding → Host/Service | Impacted asset |
| `EXPLOITS` | Finding → Vulnerability/CVE | Vulnerability exploited |
| `DISCOVERED_IN` | Finding → NetworkSegment | Network context |
| `PART_OF` | Finding → Campaign | Parent campaign |
| `EVIDENCED_BY` | Finding → Artifact | Proof artifacts (screenshots, logs) |

#### Campaign

Represents a red-team engagement, pentest campaign, or adversary-emulation operation.

| Property | Type | Description |
|----------|------|-------------|
| `campaign_id` | string | **Unique key.** Engagement identifier |
| `name` | string | Campaign name |
| `status` | enum | `planning` \| `active` \| `paused` \| `completed` \| `aborted` |
| `type` | enum | `red-team` \| `pentest` \| `bug-bounty` \| `purple-team` \| `threat-hunt` |
| `scope` | string | JSON-encoded scope definition |
| `roe` | string | Rules of engagement summary |
| `start_date` | date | Engagement start |
| `end_date` | date | Engagement end |
| `lead` | string | Operator handle |
| `objectives` | string | JSON array of objective strings |
| `notes` | string | Free-form operator notes |

**Key relationships:**

| Relationship | Direction | Target | Meaning |
|-------------|-----------|--------|---------|
| `TARGETS` | Campaign → Domain/NetworkSegment/CloudResource | Scoped targets |
| `PRODUCED` | Campaign → Finding | Findings from this campaign |
| `USED_TECHNIQUE` | Campaign → Technique | ATT&CK techniques employed |
| `ATTRIBUTED_TO` | Campaign → ThreatActor | Adversary emulation attribution |
| `HAS_OBJECTIVE` | Campaign → CrownJewel | Campaign crown jewels |

---

## 2. Full Relationship Catalog

All relationships in the KG v2 schema, alphabetically:

| Relationship | From | To | Layer |
|-------------|------|-----|-------|
| `AFFECTS` | Vulnerability/Finding | Host/Service | vuln → infra |
| `ASSUMES` | CloudResource | CloudResource | cloud IAM |
| `ATTACHED_TO` | CloudResource | CloudResource | cloud topology |
| `AUTHENTICATED_AS` | Session | User | identity |
| `ATTRIBUTED_TO` | Campaign | ThreatActor | intel |
| `CONTAINS` | Domain/NetworkSegment | Host | topology |
| `COUNTERED_BY` | Technique | Technique | defense |
| `DISCOVERED_IN` | Finding | NetworkSegment | context |
| `ESTABLISHED_VIA` | Session | Service | session |
| `EVIDENCED_BY` | Finding | Artifact | proof |
| `EXPLOITS` | Finding/AttackPath | Vulnerability/CVE | attack |
| `EXPOSES` | CloudResource | Service | exposure |
| `FILTERED_BY` | NetworkSegment | Host | firewall |
| `HAS_OBJECTIVE` | Campaign | CrownJewel | scope |
| `HAS_POLICY` | Domain | GPO | AD |
| `HOSTED_IN` | CloudResource | Region | cloud |
| `MANAGES` | Domain | Group | AD |
| `MEMBER_OF` | User | Group | identity |
| `ORIGINATES_FROM` | Session | Host | session |
| `OWNS` | Account | Host | access |
| `PART_OF` | CloudResource/NetworkSegment/Finding | NetworkSegment/Domain/Campaign | hierarchy |
| `PEERS_WITH` | NetworkSegment | NetworkSegment | topology |
| `PRODUCED` | Campaign | Finding | output |
| `REQUIRES` | Vulnerability | Vulnerability | chain |
| `RUNS_ON` | Service | Host | infra |
| `STORES` | CloudResource | Secret | data |
| `TARGETS` | Session/Campaign | Host/Domain/NetworkSegment/CloudResource | scope |
| `TRUSTS` | Domain | Domain | AD trust |
| `USED_TECHNIQUE` | Campaign | Technique | TTP |
| `USES` | Attack | Credential | access |
| `USES_CREDENTIAL` | Session | Credential | auth |

---

## 3. Cypher Schema Bootstrap

The full v2 schema extension is defined in:

```
packages/decepticon/decepticon/skills/.graph/kg-schema-extensions.cypher
```

Run it idempotently against a running Neo4j instance:

```bash
# Via cypher-shell
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" < \
  packages/decepticon/decepticon/skills/.graph/kg-schema-extensions.cypher

# Via decepticon CLI
decepticon kg-bootstrap --schema v2
```

The script creates:
- 6 uniqueness constraints (one per v2 node type's key property)
- 4 performance indexes (Domain.type, CloudResource.provider, Finding.severity, Campaign.status)
- Template sentinel nodes for each type (removable via the commented cleanup block)

---

## 4. Multi-Hop Attack Path Queries

### 4.1 Cross-Domain Lateral Movement

Find paths from an external-facing host through an AD trust to a domain controller:

```cypher
MATCH path = (entry:Host)-[:RUNS_ON|AFFECTS|EXPLOITS*1..3]->(pivot:Host)
  -[:CONTAINS*0..1]-(d:Domain)-[:TRUSTS]->(d2:Domain)
  -[:CONTAINS]->(dc:Host)
WHERE entry.compromised = true
  AND dc.hostname CONTAINS 'DC'
RETURN path, length(path) AS hops
ORDER BY hops ASC
LIMIT 10
```

### 4.2 Cloud Privilege Escalation Chain

Trace IAM role assumption chains to reach a sensitive resource:

```cypher
MATCH path = (start:CloudResource)-[:ASSUMES*1..5]->(target:CloudResource)
WHERE start.resource_type = 'ec2'
  AND target.resource_type = 'iam-role'
  AND target.tags CONTAINS '"admin"'
RETURN path, length(path) AS depth
ORDER BY depth ASC
```

### 4.3 Session Hijack to Crown Jewel

Find paths from a hijacked session to a crown jewel through lateral pivots:

```cypher
MATCH (s:Session {hijacked: true})-[:TARGETS]->(h:Host)
MATCH path = (h)-[:RUNS_ON|AFFECTS|EXPLOITS|CONTAINS*1..4]->(cj:CrownJewel)
RETURN s.session_id, cj.description, path
```

### 4.4 Campaign Findings Roll-Up

Aggregate findings by severity for a campaign:

```cypher
MATCH (c:Campaign {campaign_id: $cid})-[:PRODUCED]->(f:Finding)
RETURN f.severity, count(f) AS count, collect(f.title) AS titles
ORDER BY CASE f.severity
  WHEN 'critical' THEN 0
  WHEN 'high' THEN 1
  WHEN 'medium' THEN 2
  WHEN 'low' THEN 3
  ELSE 4
END
```

### 4.5 Network Segmentation Audit

Find hosts reachable across segment boundaries (potential segmentation failures):

```cypher
MATCH (ns1:NetworkSegment)-[:PEERS_WITH]->(ns2:NetworkSegment)
MATCH (ns1)-[:CONTAINS]->(h1:Host)-[:RUNS_ON]-(svc:Service)
MATCH (ns2)-[:CONTAINS]->(h2:Host)
WHERE ns1.zone <> ns2.zone
RETURN ns1.name AS source_zone, ns2.name AS target_zone,
       h1.ip AS source, svc.port AS port, h2.ip AS target
ORDER BY ns1.zone, ns2.zone
```

### 4.6 Finding → CVE → ThreatActor Intelligence Join

Link findings back to known threat actors via CVE exploitation history:

```cypher
MATCH (f:Finding)-[:EXPLOITS]->(cve:CVE)<-[:EXPLOITS]-(ta:ThreatActor)
RETURN f.title, cve.cve_id, ta.name, ta.attribution
ORDER BY f.severity DESC
```

---

## 5. Agent Tool Integration

### 5.1 Graph Mutation Tools

| Tool | Description |
|------|-------------|
| `kg_create_node(type, properties)` | Create a typed node (all v1 + v2 types) |
| `kg_create_edge(from_id, to_id, relationship)` | Link two nodes with a typed relationship |
| `kg_upsert_node(type, key, properties)` | Idempotent MERGE by key property |
| `kg_bulk_ingest(nodes, edges)` | Batch create nodes and edges |

### 5.2 Graph Query Tools

| Tool | Description |
|------|-------------|
| `kg_query_nodes(type, filters)` | Search nodes by type and property filters |
| `kg_query_paths(start_id, end_id, max_depth)` | Find all paths between two nodes |
| `kg_get_severity_score(node_id)` | Aggregate severity score for a node |
| `kg_shortest_path(start_id, end_id, cost_property)` | Dijkstra weighted shortest path |

### 5.3 Campaign & Finding Tools

| Tool | Description |
|------|-------------|
| `kg_create_campaign(name, type, scope, roe)` | Initialize a new campaign node |
| `kg_add_finding(campaign_id, finding)` | Create a Finding and link to Campaign |
| `kg_campaign_summary(campaign_id)` | Roll up findings, techniques, and coverage |
| `kg_export_findings(campaign_id, format)` | Export findings as JSON, CSV, or SARIF |

### 5.4 Artifact Ingestion

| Tool | Description |
|------|-------------|
| `ingest_sarif(path)` | Parse SARIF report → Finding + CVE nodes |
| `ingest_scan_output(tool, path)` | Parse nmap XML, nuclei JSON, Nessus CSV |
| `ingest_bloodhound(path)` | Import BloodHound JSON → Domain, User, Group, Session nodes |
| `ingest_cloud_inventory(provider, path)` | Import cloud asset inventory → CloudResource nodes |

---

## 6. Health & Diagnostics

```bash
# Full health check
decepticon kg-health

# v2 schema validation
decepticon kg-health --check-schema v2

# Node/edge statistics
decepticon kg-stats
```

Output includes:
- Neo4j connectivity and version
- Node counts by label (v1 + v2)
- Edge counts by type
- Constraint and index health
- Graph size on disk
- Orphan detection (nodes with zero edges)

---

## 7. Migration from v1

The v2 schema is purely additive — no v1 nodes or relationships are modified. To adopt v2:

1. **Run the schema extension script** (Section 3). This creates constraints, indexes, and template nodes.
2. **Update tool calls** to use the new node types. Existing `Host`, `Service`, `Vulnerability`, `Credential`, and `Account` nodes continue to work unchanged.
3. **Link existing nodes** to v2 types as discovered:
   - Join hosts to Domains: `MERGE (d:Domain {fqdn: $fqdn})-[:CONTAINS]->(h:Host {hostname: $host})`
   - Place hosts in NetworkSegments: `MERGE (ns:NetworkSegment {cidr: $cidr})-[:CONTAINS]->(h:Host {ip: $ip})`
   - Create Campaign for the engagement and link Findings.

No destructive migration required. v1 queries remain valid.

---

## 8. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate `Finding` from `Vulnerability` | A Finding is a validated, reportable instance; a Vulnerability is a catalog entry. One CVE may produce many Findings across hosts. |
| `Campaign` as a first-class node | Scopes all operational data to an engagement. Enables multi-campaign history, OPSEC isolation, and per-campaign reporting. |
| `NetworkSegment` with CIDR key | CIDR is the natural unique identifier. Enables segmentation-aware pathfinding — the agent can reason about firewall boundaries. |
| `Session` separate from `Credential` | A session is a runtime artifact with lifetime; a credential is a static secret. Sessions can be hijacked independently of credential compromise. |
| `CloudResource` with ARN key | ARN/resource-path is universally unique across providers. Tags stored as JSON for schema flexibility. |
| `Domain` with FQDN key | Aligns with BloodHound CE conventions. Trust relationships are first-class edges for cross-domain attack paths. |
| MERGE-only Cypher | All schema scripts use `MERGE` (never bare `CREATE`) for idempotent, re-runnable bootstrap. |
