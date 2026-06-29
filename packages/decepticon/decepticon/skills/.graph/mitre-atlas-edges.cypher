// MITRE ATLAS overlay for the Skillogy graph.
// Additive (MERGE-based, idempotent). Source: MITRE ATLAS v4.6.
// Maps 30 ATLAS technique nodes and IMPLEMENTS_ATLAS edges linking
// Decepticon skills to the adversarial-ML technique they operationalise.


// ============================================================
// === ATLASTechnique nodes ===================================
// ============================================================
// ATLAS techniques cover the adversarial machine-learning lifecycle.
// IDs follow the AML.TNNNN / AML.TNNNN.NNN pattern.

// --- Reconnaissance ---
MERGE (t:ATLASTechnique {id: 'AML.T0000'})
SET t.name        = 'ML Model Access',
    t.tactic      = 'Reconnaissance',
    t.description = 'Adversary gains query or API access to a deployed ML model',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0000';

MERGE (t:ATLASTechnique {id: 'AML.T0001'})
SET t.name        = 'ML Artifact Collection',
    t.tactic      = 'Reconnaissance',
    t.description = 'Collecting publicly available ML artifacts (model cards, weights, datasets)',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0001';

MERGE (t:ATLASTechnique {id: 'AML.T0002'})
SET t.name        = 'Search for Victim ML Resources',
    t.tactic      = 'Reconnaissance',
    t.description = 'Identifying ML endpoints, model registries, or training pipelines in target environment',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0002';

// --- ML Attack Staging ---
MERGE (t:ATLASTechnique {id: 'AML.T0003'})
SET t.name        = 'Develop Adversarial ML Attack',
    t.tactic      = 'ML Attack Staging',
    t.description = 'Developing evasion, poisoning, or extraction attack payloads against ML models',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0003';

MERGE (t:ATLASTechnique {id: 'AML.T0004'})
SET t.name        = 'Craft Adversarial Data',
    t.tactic      = 'ML Attack Staging',
    t.description = 'Creating input perturbations designed to mislead model inference',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0004';

MERGE (t:ATLASTechnique {id: 'AML.T0005'})
SET t.name        = 'Create Proxy Model',
    t.tactic      = 'ML Attack Staging',
    t.description = 'Training a substitute model to approximate target model behaviour for transfer attacks',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0005';

MERGE (t:ATLASTechnique {id: 'AML.T0043'})
SET t.name        = 'Acquire Public ML Model',
    t.tactic      = 'ML Attack Staging',
    t.description = 'Downloading publicly available pre-trained model as attack baseline',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0043';

// --- Initial Access ---
MERGE (t:ATLASTechnique {id: 'AML.T0006'})
SET t.name        = 'Supply Chain Compromise of ML Artifacts',
    t.tactic      = 'Initial Access',
    t.description = 'Compromising ML model supply chain — malicious model weights, datasets, or libraries',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0006';

MERGE (t:ATLASTechnique {id: 'AML.T0007'})
SET t.name        = 'Exploit Public-Facing ML Application',
    t.tactic      = 'Initial Access',
    t.description = 'Exploiting vulnerabilities in ML inference APIs or model-serving endpoints',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0007';

MERGE (t:ATLASTechnique {id: 'AML.T0044'})
SET t.name        = 'Full ML Model Access',
    t.tactic      = 'Initial Access',
    t.description = 'Gaining white-box access to model weights, architecture, and training data',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0044';

// --- Persistence ---
MERGE (t:ATLASTechnique {id: 'AML.T0008'})
SET t.name        = 'Backdoor ML Model',
    t.tactic      = 'Persistence',
    t.description = 'Injecting a hidden trigger into a model that activates on specific inputs',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0008';

MERGE (t:ATLASTechnique {id: 'AML.T0010'})
SET t.name        = 'ML Model Poisoning',
    t.tactic      = 'Persistence',
    t.description = 'Corrupting training data or fine-tuning process to embed persistent misclassifications',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0010';

// --- Evasion ---
MERGE (t:ATLASTechnique {id: 'AML.T0015'})
SET t.name        = 'Evade ML Model',
    t.tactic      = 'Evasion',
    t.description = 'Crafting inputs that cause the model to produce incorrect or attacker-desired outputs',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0015';

MERGE (t:ATLASTechnique {id: 'AML.T0015.001'})
SET t.name        = 'White-Box Evasion',
    t.tactic      = 'Evasion',
    t.description = 'Gradient-based perturbation using full model access (FGSM, PGD, C&W)',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0015/001',
    t.parent      = 'AML.T0015';

MERGE (t:ATLASTechnique {id: 'AML.T0015.002'})
SET t.name        = 'Black-Box Evasion',
    t.tactic      = 'Evasion',
    t.description = 'Query-based perturbation using only model outputs (score / decision boundary)',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0015/002',
    t.parent      = 'AML.T0015';

MERGE (t:ATLASTechnique {id: 'AML.T0015.003'})
SET t.name        = 'Physical Adversarial Examples',
    t.tactic      = 'Evasion',
    t.description = 'Real-world adversarial patches, stickers, or wearables that fool vision models',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0015/003',
    t.parent      = 'AML.T0015';

MERGE (t:ATLASTechnique {id: 'AML.T0016'})
SET t.name        = 'Obtain Capabilities',
    t.tactic      = 'Evasion',
    t.description = 'Acquiring existing adversarial ML tools, datasets, or attack scripts',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0016';

// --- Discovery ---
MERGE (t:ATLASTechnique {id: 'AML.T0011'})
SET t.name        = 'Discover ML Model Ontology',
    t.tactic      = 'Discovery',
    t.description = 'Mapping model input/output schema, classes, and confidence thresholds',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0011';

MERGE (t:ATLASTechnique {id: 'AML.T0012'})
SET t.name        = 'Discover ML Model Family',
    t.tactic      = 'Discovery',
    t.description = 'Identifying the model architecture family (CNN, transformer, GBM) via probing',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0012';

// --- Exfiltration ---
MERGE (t:ATLASTechnique {id: 'AML.T0024'})
SET t.name        = 'Exfiltration via ML Inference API',
    t.tactic      = 'Exfiltration',
    t.description = 'Extracting training data or model internals through inference-API side channels',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0024';

MERGE (t:ATLASTechnique {id: 'AML.T0024.001'})
SET t.name        = 'Model Extraction',
    t.tactic      = 'Exfiltration',
    t.description = 'Stealing model functionality by querying and distilling a clone',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0024/001',
    t.parent      = 'AML.T0024';

MERGE (t:ATLASTechnique {id: 'AML.T0024.002'})
SET t.name        = 'Training Data Extraction',
    t.tactic      = 'Exfiltration',
    t.description = 'Recovering memorised training examples from model outputs',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0024/002',
    t.parent      = 'AML.T0024';

MERGE (t:ATLASTechnique {id: 'AML.T0025'})
SET t.name        = 'Membership Inference',
    t.tactic      = 'Exfiltration',
    t.description = 'Determining whether a specific record was in the training dataset',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0025';

// --- Impact ---
MERGE (t:ATLASTechnique {id: 'AML.T0029'})
SET t.name        = 'Denial of ML Service',
    t.tactic      = 'Impact',
    t.description = 'Degrading or disabling ML service availability through adversarial queries',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0029';

MERGE (t:ATLASTechnique {id: 'AML.T0031'})
SET t.name        = 'Erode ML Model Integrity',
    t.tactic      = 'Impact',
    t.description = 'Gradually degrading model accuracy through sustained adversarial input campaigns',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0031';

MERGE (t:ATLASTechnique {id: 'AML.T0034'})
SET t.name        = 'Cost Harvesting',
    t.tactic      = 'Impact',
    t.description = 'Inflating inference costs by triggering expensive model computations',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0034';

// --- LLM / Generative-AI specific ---
MERGE (t:ATLASTechnique {id: 'AML.T0051'})
SET t.name        = 'LLM Prompt Injection',
    t.tactic      = 'Initial Access',
    t.description = 'Injecting adversarial instructions into LLM prompts to hijack model behaviour',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0051';

MERGE (t:ATLASTechnique {id: 'AML.T0051.001'})
SET t.name        = 'Direct Prompt Injection',
    t.tactic      = 'Initial Access',
    t.description = 'User-supplied prompt directly overrides system instructions',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0051/001',
    t.parent      = 'AML.T0051';

MERGE (t:ATLASTechnique {id: 'AML.T0051.002'})
SET t.name        = 'Indirect Prompt Injection',
    t.tactic      = 'Initial Access',
    t.description = 'Adversarial instructions planted in external data sources consumed by the LLM',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0051/002',
    t.parent      = 'AML.T0051';

MERGE (t:ATLASTechnique {id: 'AML.T0054'})
SET t.name        = 'LLM Jailbreak',
    t.tactic      = 'Evasion',
    t.description = 'Bypassing LLM safety guardrails to elicit restricted outputs',
    t.url         = 'https://atlas.mitre.org/techniques/AML.T0054';


// ============================================================
// === ATLAS MatrixVersion node ===============================
// ============================================================

MERGE (n:MatrixVersion {matrix: 'atlas'})
SET n.framework = 'atlas', n.version = '4.6';


// ============================================================
// === IMPLEMENTS_ATLAS edges (Skill → ATLASTechnique) ========
// === Links Decepticon skills to the ATLAS techniques they   =
// === operationalise during an engagement.                   =
// ============================================================

// --- Prompt Injection skills ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0051'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0051.001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0051.002'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0054'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0015'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0004'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0003'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0029'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0034'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Model extraction / exfiltration skills ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0024'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0024.001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0025'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Reconnaissance of ML systems ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0000'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0011'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0012'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Supply-chain compromise of ML artifacts ---
MATCH (s:Skill {name: 'supply-chain'}), (t:ATLASTechnique {id: 'AML.T0006'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'supply-chain'}), (t:ATLASTechnique {id: 'AML.T0001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Exploiting public-facing ML applications ---
MATCH (s:Skill {name: 'web'}), (t:ATLASTechnique {id: 'AML.T0007'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'command-injection'}), (t:ATLASTechnique {id: 'AML.T0007'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Data poisoning via training pipelines ---
MATCH (s:Skill {name: 'supply-chain'}), (t:ATLASTechnique {id: 'AML.T0010'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Backdooring ML models ---
MATCH (s:Skill {name: 'supply-chain'}), (t:ATLASTechnique {id: 'AML.T0008'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- RE skills discovering ML model internals ---
MATCH (s:Skill {name: 'deep-analysis'}), (t:ATLASTechnique {id: 'AML.T0044'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ghidra'}), (t:ATLASTechnique {id: 'AML.T0044'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Scanning / recon of ML resources ---
MATCH (s:Skill {name: 'web-recon'}), (t:ATLASTechnique {id: 'AML.T0002'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'osint'}), (t:ATLASTechnique {id: 'AML.T0001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'osint'}), (t:ATLASTechnique {id: 'AML.T0002'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'passive-recon'}), (t:ATLASTechnique {id: 'AML.T0002'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Cloud skills accessing model endpoints ---
MATCH (s:Skill {name: 'gcp-org-escalation'}), (t:ATLASTechnique {id: 'AML.T0000'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'm365-mailbox-compromise'}), (t:ATLASTechnique {id: 'AML.T0024'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Evasion sub-techniques via specialised skills ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0015.001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0015.002'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

// --- ML model integrity erosion ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0031'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Proxy model creation ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0005'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Training data extraction ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0024.002'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Acquiring public ML models ---
MATCH (s:Skill {name: 'osint'}), (t:ATLASTechnique {id: 'AML.T0043'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'supply-chain'}), (t:ATLASTechnique {id: 'AML.T0043'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Obtaining adversarial ML capabilities ---
MATCH (s:Skill {name: 'ai-red-team'}), (t:ATLASTechnique {id: 'AML.T0016'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'full', source: 'MITRE ATLAS'}]->(t);

// --- Fuzzing ML endpoints ---
MATCH (s:Skill {name: 'fuzzing'}), (t:ATLASTechnique {id: 'AML.T0007'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'fuzzing'}), (t:ATLASTechnique {id: 'AML.T0029'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Threat intel on adversarial ML campaigns ---
MATCH (s:Skill {name: 'ti-ioc-extraction'}), (t:ATLASTechnique {id: 'AML.T0001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

MATCH (s:Skill {name: 'threat-profile'}), (t:ATLASTechnique {id: 'AML.T0001'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);

// --- Physical adversarial examples (firmware/hardware skills) ---
MATCH (s:Skill {name: 'firmware'}), (t:ATLASTechnique {id: 'AML.T0015.003'})
MERGE (s)-[:IMPLEMENTS_ATLAS {coverage: 'partial', source: 'MITRE ATLAS'}]->(t);
