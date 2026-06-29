// Knowledge Graph v2 schema extensions.
// Additive (MERGE-based, idempotent). Extends attack-graph-schema.md.
// Adds: Domain, CloudResource, NetworkSegment, Session, Finding, Campaign.

// ============================================================
// === Constraints & Indexes ===================================
// ============================================================

CREATE CONSTRAINT domain_fqdn_unique IF NOT EXISTS
  FOR (d:Domain) REQUIRE d.fqdn IS UNIQUE;

CREATE CONSTRAINT cloud_resource_arn_unique IF NOT EXISTS
  FOR (cr:CloudResource) REQUIRE cr.arn IS UNIQUE;

CREATE CONSTRAINT network_segment_cidr_unique IF NOT EXISTS
  FOR (ns:NetworkSegment) REQUIRE ns.cidr IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
  FOR (s:Session) REQUIRE s.session_id IS UNIQUE;

CREATE CONSTRAINT finding_id_unique IF NOT EXISTS
  FOR (f:Finding) REQUIRE f.finding_id IS UNIQUE;

CREATE CONSTRAINT campaign_id_unique IF NOT EXISTS
  FOR (c:Campaign) REQUIRE c.campaign_id IS UNIQUE;

CREATE INDEX domain_type_idx IF NOT EXISTS
  FOR (d:Domain) ON (d.type);

CREATE INDEX cloud_provider_idx IF NOT EXISTS
  FOR (cr:CloudResource) ON (cr.provider);

CREATE INDEX finding_severity_idx IF NOT EXISTS
  FOR (f:Finding) ON (f.severity);

CREATE INDEX campaign_status_idx IF NOT EXISTS
  FOR (c:Campaign) ON (c.status);

// ============================================================
// === Domain nodes ============================================
// ============================================================
// Represents a DNS domain or Active Directory domain/forest.

MERGE (d:Domain {fqdn: 'TEMPLATE_DOMAIN'})
SET d.type           = 'ad',          // 'ad' | 'dns' | 'cloud'
    d.forest         = null,          // parent AD forest FQDN
    d.functional_level = null,        // e.g. 'Windows2016Domain'
    d.trust_direction  = null,        // 'inbound' | 'outbound' | 'bidirectional'
    d.dc_count       = 0,
    d.discovered_at  = datetime(),
    d.notes          = null;

// Domain relationships
// (d:Domain)-[:CONTAINS]->(h:Host)           — host is joined to this domain
// (d:Domain)-[:TRUSTS]->(d2:Domain)          — AD trust relationship
// (d:Domain)-[:MANAGES]->(g:Group)           — domain-scoped security group
// (d:Domain)-[:HAS_POLICY]->(gpo:GPO)        — group policy linkage

// ============================================================
// === CloudResource nodes =====================================
// ============================================================
// Represents an AWS / GCP / Azure cloud resource.

MERGE (cr:CloudResource {arn: 'TEMPLATE_ARN'})
SET cr.provider       = 'aws',        // 'aws' | 'gcp' | 'azure'
    cr.resource_type  = 'ec2',        // 'ec2' | 's3' | 'iam-role' | 'lambda' | 'rds' | 'k8s-pod' ...
    cr.region         = null,
    cr.account_id     = null,
    cr.tags           = '{}',         // JSON-encoded resource tags
    cr.public_access  = false,
    cr.encryption     = null,         // 'aes-256' | 'kms' | 'none'
    cr.discovered_at  = datetime(),
    cr.notes          = null;

// CloudResource relationships
// (cr:CloudResource)-[:HOSTED_IN]->(r:Region)           — cloud region
// (cr:CloudResource)-[:ATTACHED_TO]->(cr2:CloudResource) — e.g. EBS→EC2
// (cr:CloudResource)-[:ASSUMES]->(role:CloudResource)    — IAM role assumption
// (cr:CloudResource)-[:EXPOSES]->(svc:Service)           — publicly exposed service
// (cr:CloudResource)-[:STORES]->(data:Secret)            — secrets in S3/SSM/Vault
// (cr:CloudResource)-[:PART_OF]->(ns:NetworkSegment)     — VPC/subnet membership

// ============================================================
// === NetworkSegment nodes ====================================
// ============================================================
// Represents a VLAN, subnet, VPC, or logical network zone.

MERGE (ns:NetworkSegment {cidr: 'TEMPLATE_CIDR'})
SET ns.name          = null,          // human-friendly label ('corp-lan', 'dmz', 'ot-scada')
    ns.vlan_id       = null,
    ns.zone          = null,          // 'internal' | 'dmz' | 'external' | 'ot' | 'mgmt'
    ns.gateway       = null,          // default gateway IP
    ns.provider      = null,          // 'on-prem' | 'aws-vpc' | 'azure-vnet' | 'gcp-vpc'
    ns.vpc_id        = null,
    ns.acl_policy    = null,          // JSON-encoded ACL summary
    ns.discovered_at = datetime(),
    ns.notes         = null;

// NetworkSegment relationships
// (ns:NetworkSegment)-[:CONTAINS]->(h:Host)              — host lives in this segment
// (ns:NetworkSegment)-[:PEERS_WITH]->(ns2:NetworkSegment) — routed/peered segments
// (ns:NetworkSegment)-[:FILTERED_BY]->(fw:Host)          — firewall/ACL appliance
// (ns:NetworkSegment)-[:PART_OF]->(d:Domain)             — segment belongs to domain

// ============================================================
// === Session nodes ===========================================
// ============================================================
// Represents an active or captured session (RDP, SSH, web, Kerberos TGT).

MERGE (s:Session {session_id: 'TEMPLATE_SESSION'})
SET s.type           = 'ssh',         // 'ssh' | 'rdp' | 'web' | 'kerberos' | 'ntlm' | 'vpn'
    s.source_ip      = null,
    s.target_ip      = null,
    s.username       = null,
    s.elevated       = false,         // session runs as admin/root
    s.created_at     = datetime(),
    s.expires_at     = null,
    s.token          = null,          // redacted auth token / ticket hash
    s.hijacked       = false,
    s.notes          = null;

// Session relationships
// (s:Session)-[:ORIGINATES_FROM]->(h:Host)   — source host
// (s:Session)-[:TARGETS]->(h2:Host)          — destination host
// (s:Session)-[:AUTHENTICATED_AS]->(u:User)  — identity behind session
// (s:Session)-[:USES_CREDENTIAL]->(c:Credential) — credential used
// (s:Session)-[:ESTABLISHED_VIA]->(svc:Service)  — service (SSH, RDP port)

// ============================================================
// === Finding nodes ===========================================
// ============================================================
// Represents a verified, reportable security finding (post-validation).

MERGE (f:Finding {finding_id: 'TEMPLATE_FINDING'})
SET f.title          = null,
    f.severity       = 'high',        // 'critical' | 'high' | 'medium' | 'low' | 'info'
    f.cvss           = null,          // numeric CVSS 3.1 score
    f.status         = 'confirmed',   // 'confirmed' | 'reported' | 'remediated' | 'accepted_risk'
    f.description    = null,
    f.evidence       = null,          // path to proof / artifact URI
    f.remediation    = null,          // recommended fix
    f.cwe_id         = null,
    f.discovered_at  = datetime(),
    f.reported_at    = null,
    f.notes          = null;

// Finding relationships
// (f:Finding)-[:AFFECTS]->(h:Host)              — impacted host
// (f:Finding)-[:AFFECTS]->(svc:Service)         — impacted service
// (f:Finding)-[:EXPLOITS]->(v:Vulnerability)    — CVE/vuln exploited
// (f:Finding)-[:EXPLOITS]->(v:CVE)              — specific CVE exploited
// (f:Finding)-[:DISCOVERED_IN]->(ns:NetworkSegment) — network context
// (f:Finding)-[:PART_OF]->(c:Campaign)          — parent campaign
// (f:Finding)-[:EVIDENCED_BY]->(a:Artifact)     — proof artifacts

// ============================================================
// === Campaign nodes ==========================================
// ============================================================
// Represents a red-team engagement, pentest campaign, or threat-actor operation.

MERGE (c:Campaign {campaign_id: 'TEMPLATE_CAMPAIGN'})
SET c.name           = null,
    c.status         = 'active',      // 'planning' | 'active' | 'paused' | 'completed' | 'aborted'
    c.type           = 'red-team',    // 'red-team' | 'pentest' | 'bug-bounty' | 'purple-team' | 'threat-hunt'
    c.scope          = null,          // JSON-encoded scope definition
    c.roe            = null,          // rules of engagement summary
    c.start_date     = null,
    c.end_date       = null,
    c.lead           = null,          // operator handle
    c.objectives     = '[]',         // JSON array of objective strings
    c.notes          = null;

// Campaign relationships
// (c:Campaign)-[:TARGETS]->(d:Domain)           — target domain
// (c:Campaign)-[:TARGETS]->(ns:NetworkSegment)  — target network
// (c:Campaign)-[:TARGETS]->(cr:CloudResource)   — target cloud infra
// (c:Campaign)-[:PRODUCED]->(f:Finding)         — findings from this campaign
// (c:Campaign)-[:USED_TECHNIQUE]->(t:Technique) — ATT&CK techniques used
// (c:Campaign)-[:ATTRIBUTED_TO]->(ta:ThreatActor) — threat emulation attribution
// (c:Campaign)-[:HAS_OBJECTIVE]->(cj:CrownJewel) — campaign crown jewels

// ============================================================
// === Cross-node relationship templates =======================
// ============================================================
// These MERGE patterns establish common multi-hop paths the agent
// uses for attack-chain reasoning. Parameterize in real usage.

// Domain → Host enrollment
// MERGE (d:Domain {fqdn: $domain})-[:CONTAINS]->(h:Host {hostname: $host})

// CloudResource → NetworkSegment placement
// MERGE (cr:CloudResource {arn: $arn})-[:PART_OF]->(ns:NetworkSegment {cidr: $cidr})

// Session → Host pivot path
// MERGE (s:Session {session_id: $sid})-[:ORIGINATES_FROM]->(src:Host {ip: $src_ip})
// MERGE (s)-[:TARGETS]->(dst:Host {ip: $dst_ip})

// Finding → Campaign roll-up
// MERGE (f:Finding {finding_id: $fid})-[:PART_OF]->(c:Campaign {campaign_id: $cid})

// Campaign → Domain scoping
// MERGE (c:Campaign {campaign_id: $cid})-[:TARGETS]->(d:Domain {fqdn: $domain})

// NetworkSegment → NetworkSegment lateral path
// MERGE (ns1:NetworkSegment {cidr: $cidr1})-[:PEERS_WITH]->(ns2:NetworkSegment {cidr: $cidr2})

// ============================================================
// === Cleanup: remove TEMPLATE sentinel nodes =================
// ============================================================
// Uncomment to purge template placeholders after schema bootstrap:
// MATCH (n) WHERE n.fqdn = 'TEMPLATE_DOMAIN'
//    OR n.arn = 'TEMPLATE_ARN' OR n.cidr = 'TEMPLATE_CIDR'
//    OR n.session_id = 'TEMPLATE_SESSION' OR n.finding_id = 'TEMPLATE_FINDING'
//    OR n.campaign_id = 'TEMPLATE_CAMPAIGN'
// DETACH DELETE n;
