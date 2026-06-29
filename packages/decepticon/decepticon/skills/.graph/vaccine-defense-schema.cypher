// ============================================================================
// Offensive Vaccine — Knowledge Graph Schema
//
// Idempotent Cypher (MERGE only) for the three node types and five edge types
// introduced by the vaccine subsystem.  Safe to run repeatedly; existing
// nodes/edges are matched, never duplicated.
//
// Node types:  Mitigation, DefenseAction, VerificationResult
// Edge types:  ADDRESSES, MITIGATES, IMPLEMENTS, VERIFIES, TESTED
// ============================================================================

// ---------------------------------------------------------------------------
// Constraints & Indexes (idempotent — IF NOT EXISTS)
// ---------------------------------------------------------------------------

CREATE CONSTRAINT mitigation_id_unique IF NOT EXISTS
FOR (m:Mitigation) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT defense_action_id_unique IF NOT EXISTS
FOR (d:DefenseAction) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT verification_result_id_unique IF NOT EXISTS
FOR (v:VerificationResult) REQUIRE v.id IS UNIQUE;

CREATE INDEX mitigation_status_idx IF NOT EXISTS
FOR (m:Mitigation) ON (m.status);

CREATE INDEX defense_action_status_idx IF NOT EXISTS
FOR (d:DefenseAction) ON (d.status);

CREATE INDEX verification_disposition_idx IF NOT EXISTS
FOR (v:VerificationResult) ON (v.disposition);

CREATE INDEX finding_vaccine_status_idx IF NOT EXISTS
FOR (f:Finding) ON (f.vaccine_status);

// ---------------------------------------------------------------------------
// Node: Mitigation
//
// Represents a planned or completed remediation effort for a Finding.
// Lifecycle: planned → deployed → verified | failed
// ---------------------------------------------------------------------------

MERGE (m:Mitigation {id: $mitigation_id})
ON CREATE SET
    m.status        = "planned",
    m.finding_id    = $finding_id,
    m.severity      = $severity,
    m.techniques    = $techniques,
    m.created_at    = datetime()
ON MATCH SET
    m.updated_at    = datetime();

// ---------------------------------------------------------------------------
// Node: DefenseAction
//
// A single compensating control deployed as part of a Mitigation.
// action_type ∈ {firewall_rule, config_change, detection_rule, code_patch, other}
// ---------------------------------------------------------------------------

MERGE (d:DefenseAction {id: $defense_action_id})
ON CREATE SET
    d.action_type    = $action_type,
    d.description    = $description,
    d.configuration  = $configuration,
    d.mitigation_id  = $mitigation_id,
    d.finding_id     = $finding_id,
    d.deployed_at    = datetime(),
    d.status         = "deployed"
ON MATCH SET
    d.updated_at     = datetime();

// ---------------------------------------------------------------------------
// Node: VerificationResult
//
// The outcome of re-executing an attack vector against a defended target.
// disposition ∈ {pending, blocked, bypassed, partial}
// ---------------------------------------------------------------------------

MERGE (v:VerificationResult {id: $verification_id})
ON CREATE SET
    v.defense_action_id    = $defense_action_id,
    v.finding_id           = $finding_id,
    v.attack_replay_command = $attack_replay_command,
    v.disposition          = "pending",
    v.evidence             = "",
    v.verified_at          = datetime()
ON MATCH SET
    v.updated_at           = datetime();

// ---------------------------------------------------------------------------
// Edge: ADDRESSES  —  Mitigation → Finding
// "This mitigation addresses this finding."
// ---------------------------------------------------------------------------

MERGE (m:Mitigation {id: $mitigation_id})
MERGE (f:Finding   {id: $finding_id})
MERGE (m)-[:ADDRESSES]->(f);

// ---------------------------------------------------------------------------
// Edge: MITIGATES  —  DefenseAction → Finding
// "This control mitigates this finding."
// ---------------------------------------------------------------------------

MERGE (d:DefenseAction {id: $defense_action_id})
MERGE (f:Finding       {id: $finding_id})
MERGE (d)-[:MITIGATES]->(f);

// ---------------------------------------------------------------------------
// Edge: IMPLEMENTS  —  DefenseAction → Mitigation
// "This action implements this mitigation plan."
// ---------------------------------------------------------------------------

MERGE (d:DefenseAction {id: $defense_action_id})
MERGE (m:Mitigation    {id: $mitigation_id})
MERGE (d)-[:IMPLEMENTS]->(m);

// ---------------------------------------------------------------------------
// Edge: VERIFIES  —  VerificationResult → DefenseAction
// "This test verifies this control."
// ---------------------------------------------------------------------------

MERGE (v:VerificationResult {id: $verification_id})
MERGE (d:DefenseAction      {id: $defense_action_id})
MERGE (v)-[:VERIFIES]->(d);

// ---------------------------------------------------------------------------
// Edge: TESTED  —  VerificationResult → Finding
// "This test re-targeted this finding."
// ---------------------------------------------------------------------------

MERGE (v:VerificationResult {id: $verification_id})
MERGE (f:Finding            {id: $finding_id})
MERGE (v)-[:TESTED]->(f);

// ---------------------------------------------------------------------------
// Update Finding vaccine_status after successful verification
// ---------------------------------------------------------------------------

MERGE (f:Finding {id: $finding_id})
ON MATCH SET
    f.vaccine_status = $vaccine_status;
