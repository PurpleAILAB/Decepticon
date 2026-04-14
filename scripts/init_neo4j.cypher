// Decepticon Attack Graph — Neo4j Schema Init
// Run once after Neo4j starts: cypher-shell < scripts/init_neo4j.cypher
//
// Schema follows docs/design/attack-graph-schema.md

// ── Uniqueness Constraints ──────────────────────────────────────────────

// Infrastructure
CREATE CONSTRAINT host_ip IF NOT EXISTS FOR (h:Host) REQUIRE h.ip IS UNIQUE;
CREATE CONSTRAINT network_cidr IF NOT EXISTS FOR (n:Network) REQUIRE n.cidr IS UNIQUE;
CREATE CONSTRAINT domain_fqdn IF NOT EXISTS FOR (d:Domain) REQUIRE d.fqdn IS UNIQUE;
CREATE CONSTRAINT service_key IF NOT EXISTS FOR (s:Service) REQUIRE s.key IS UNIQUE;
CREATE CONSTRAINT url_normalized IF NOT EXISTS FOR (u:URL) REQUIRE u.url IS UNIQUE;
CREATE CONSTRAINT cloud_arn IF NOT EXISTS FOR (cr:CloudResource) REQUIRE cr.arn IS UNIQUE;
CREATE CONSTRAINT container_key IF NOT EXISTS FOR (c:Container) REQUIRE c.key IS UNIQUE;

// Identity
CREATE CONSTRAINT user_key IF NOT EXISTS FOR (u:User) REQUIRE u.key IS UNIQUE;
CREATE CONSTRAINT group_key IF NOT EXISTS FOR (g:Group) REQUIRE g.key IS UNIQUE;
CREATE CONSTRAINT credential_key IF NOT EXISTS FOR (c:Credential) REQUIRE c.key IS UNIQUE;
CREATE CONSTRAINT session_key IF NOT EXISTS FOR (s:Session) REQUIRE s.key IS UNIQUE;

// Vulnerability
CREATE CONSTRAINT vuln_key IF NOT EXISTS FOR (v:Vulnerability) REQUIRE v.key IS UNIQUE;
CREATE CONSTRAINT cve_id IF NOT EXISTS FOR (c:CVE) REQUIRE c.cve_id IS UNIQUE;
CREATE CONSTRAINT misconfig_key IF NOT EXISTS FOR (m:Misconfiguration) REQUIRE m.key IS UNIQUE;
CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (w:Weakness) REQUIRE w.cwe_id IS UNIQUE;

// Code
CREATE CONSTRAINT repo_url IF NOT EXISTS FOR (r:Repository) REQUIRE r.url IS UNIQUE;
CREATE CONSTRAINT source_file_key IF NOT EXISTS FOR (f:SourceFile) REQUIRE f.key IS UNIQUE;
CREATE CONSTRAINT code_location_key IF NOT EXISTS FOR (cl:CodeLocation) REQUIRE cl.key IS UNIQUE;
CREATE CONSTRAINT contract_addr IF NOT EXISTS FOR (c:Contract) REQUIRE c.address IS UNIQUE;

// Attack Progression
CREATE CONSTRAINT technique_id IF NOT EXISTS FOR (t:Technique) REQUIRE t.technique_id IS UNIQUE;
CREATE CONSTRAINT entrypoint_key IF NOT EXISTS FOR (e:Entrypoint) REQUIRE e.key IS UNIQUE;
CREATE CONSTRAINT crown_jewel_key IF NOT EXISTS FOR (cj:CrownJewel) REQUIRE cj.key IS UNIQUE;
CREATE CONSTRAINT attack_path_key IF NOT EXISTS FOR (ap:AttackPath) REQUIRE ap.key IS UNIQUE;
CREATE CONSTRAINT finding_key IF NOT EXISTS FOR (f:Finding) REQUIRE f.key IS UNIQUE;

// Analysis
CREATE CONSTRAINT candidate_key IF NOT EXISTS FOR (c:Candidate) REQUIRE c.key IS UNIQUE;
CREATE CONSTRAINT hypothesis_key IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.key IS UNIQUE;
CREATE CONSTRAINT patch_key IF NOT EXISTS FOR (p:Patch) REQUIRE p.key IS UNIQUE;

// Defense Layer
CREATE CONSTRAINT defense_action_key IF NOT EXISTS FOR (da:DefenseAction) REQUIRE da.key IS UNIQUE;
CREATE INDEX defense_action_status IF NOT EXISTS FOR (da:DefenseAction) ON (da.status);
CREATE INDEX defense_action_type IF NOT EXISTS FOR (da:DefenseAction) ON (da.action_type);
CREATE INDEX defense_action_finding IF NOT EXISTS FOR (da:DefenseAction) ON (da.finding_ref);

// ── Performance Indexes ─────────────────────────────────────────────────

CREATE INDEX host_explored IF NOT EXISTS FOR (h:Host) ON (h.explored);
CREATE INDEX host_compromised IF NOT EXISTS FOR (h:Host) ON (h.compromised);
CREATE INDEX service_product IF NOT EXISTS FOR (s:Service) ON (s.product, s.version);
CREATE INDEX vuln_severity IF NOT EXISTS FOR (v:Vulnerability) ON (v.severity);
CREATE INDEX vuln_validated IF NOT EXISTS FOR (v:Vulnerability) ON (v.validated);
CREATE INDEX vuln_class IF NOT EXISTS FOR (v:Vulnerability) ON (v.vuln_class);
CREATE INDEX vuln_exploited IF NOT EXISTS FOR (v:Vulnerability) ON (v.exploited);
CREATE INDEX finding_status IF NOT EXISTS FOR (f:Finding) ON (f.status);
CREATE INDEX candidate_status IF NOT EXISTS FOR (c:Candidate) ON (c.status);
CREATE INDEX credential_cracked IF NOT EXISTS FOR (c:Credential) ON (c.cracked);
CREATE INDEX technique_tactic IF NOT EXISTS FOR (t:Technique) ON (t.tactic);
CREATE INDEX user_admin IF NOT EXISTS FOR (u:User) ON (u.admin);
CREATE INDEX hypothesis_confidence IF NOT EXISTS FOR (h:Hypothesis) ON (h.confidence);
CREATE INDEX cve_epss IF NOT EXISTS FOR (c:CVE) ON (c.epss);
CREATE INDEX attack_path_cost IF NOT EXISTS FOR (ap:AttackPath) ON (ap.total_cost);

// ── Full-Text Search ────────────────────────────────────────────────────

CALL db.index.fulltext.createNodeIndex("vuln_search", ["Vulnerability", "Finding"], ["description", "title"]);
CALL db.index.fulltext.createNodeIndex("host_search", ["Host"], ["hostname", "ip"]);
