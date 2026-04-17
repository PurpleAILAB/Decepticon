# Knowledge Graph

Decepticon uses [Neo4j](https://neo4j.com/) as a persistent attack graph. Every host, service, vulnerability, credential, and defense action discovered during an engagement becomes a typed node with typed relationships. This is the agent's long-term memory across iterations — not conversation history.

The graph lives on `sandbox-net` and is accessible at:
- **Bolt**: `bolt://localhost:7687` (driver connection)
- **Browser**: `http://localhost:7474` (Neo4j Browser UI)

Default credentials: `neo4j` / `decepticon-graph` (set via `NEO4J_PASSWORD`).

---

## Node Types

| Type | Key Properties | Created By |
|------|---------------|-----------|
| `Host` | `ip`, `hostname`, `os`, `os_version` | Recon, Scanner |
| `Service` | `port`, `protocol`, `name`, `version`, `banner` | Recon, Scanner |
| `Vulnerability` | `cve_id`, `cwe_id`, `cvss_score`, `severity`, `description` | Scanner, Detector, Verifier |
| `Credential` | `username`, `hash_type`, `hash`, `plaintext`, `source` | Post-Exploit, Exploit |
| `Account` | `username`, `domain`, `privileges`, `groups` | Post-Exploit, AD Operator |
| `DefenseAction` | `action_type`, `description`, `applied_at`, `status` | Defender |

---

## Relationship Types

| Relationship | From → To | Meaning |
|-------------|----------|---------|
| `RUNS_ON` | Service → Host | Service runs on a host |
| `AFFECTS` | Vulnerability → Service | Vulnerability exists in a service |
| `EXPLOITS` | Objective/Finding → Vulnerability | This attack exploits this vuln |
| `REQUIRES` | Vulnerability → Vulnerability | Exploit chain dependency |
| `USES` | Attack → Credential | Attack uses a credential |
| `OWNS` | Account → Host | Account has access to host |
| `MITIGATES` | DefenseAction → Vulnerability | Defense addresses this vuln |
| `DEFENDS` | DefenseAction → Service | Defense hardens this service |
| `RESPONDS_TO` | DefenseAction → Attack | Defense responds to this attack |

---

## Research Tools

Agents interact with the graph via tools defined in `decepticon/tools/research/tools.py`:

### Graph Mutations

| Tool | Description |
|------|-------------|
| `kg_create_node(type, properties)` | Create a new node (Host, Service, Vulnerability, etc.) |
| `kg_create_edge(from_id, to_id, relationship)` | Link two nodes with a typed relationship |

### Graph Queries

| Tool | Description |
|------|-------------|
| `kg_query_nodes(type, filters)` | Search nodes by type and property filters |
| `kg_query_paths(start_id, end_id)` | Find all paths between two nodes (attack chain discovery) |
| `kg_get_severity_score(node_id)` | Calculate aggregate severity score for a node |

### Attack Chain Planning

| Tool | Description |
|------|-------------|
| `plan_attack_chains()` | Generate ranked multi-hop exploit paths using weighted shortest-path |
| `critical_path_score(chain)` | Score a chain by combined severity and complexity |
| `promote_chain(chain_id)` | Promote a promising chain to the active OPPLAN |

### Artifact Ingestion

| Tool | Description |
|------|-------------|
| `ingest_sarif(path)` | Parse a SARIF static analysis report and lift findings into the graph |
| `ingest_scan_output(tool, path)` | Parse nmap XML, nuclei JSON, or similar scan output |

---

## Health Diagnostics

```bash
decepticon kg-health
```

Runs `decepticon.tools.research.health:main` and reports:
- Neo4j connectivity status
- Node and edge counts by type
- Index health
- Graph size on disk

---

## Querying Directly

You can query the graph directly with Cypher via Neo4j Browser (`http://localhost:7474`) or the Bolt driver.

**Find all high-severity vulnerabilities:**
```cypher
MATCH (v:Vulnerability)
WHERE v.cvss_score >= 7.0
RETURN v.cve_id, v.severity, v.cvss_score
ORDER BY v.cvss_score DESC
```

**Find multi-hop attack paths to a host:**
```cypher
MATCH path = (start:Service)-[:AFFECTS|EXPLOITS|REQUIRES*1..4]->(end:Host {ip: "10.0.0.1"})
RETURN path
```

**List credentials discovered during the engagement:**
```cypher
MATCH (c:Credential)
RETURN c.username, c.hash_type, c.source
```

**Show all defense actions applied:**
```cypher
MATCH (d:DefenseAction)-[:MITIGATES]->(v:Vulnerability)
RETURN d.action_type, d.description, v.cve_id, d.status
```
