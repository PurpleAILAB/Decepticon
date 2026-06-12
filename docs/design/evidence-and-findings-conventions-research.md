# Evidence, Findings & Shared-Artifact Conventions — External Research

> **Status:** research note (input to the agent file/reporting redesign).
> **Date:** 2026-06-12.
> **Scope:** professional pentest / red-team / bug-bounty conventions for
> evidence-based artifact writing, shared file/workspace systems, and
> findings recording — sourced externally and cross-checked against primary
> standards, then mapped onto Decepticon's current behavior.

This note answers "what does the industry actually require/recommend for
evidence files, shared workspaces, and findings" so the redesign of
Decepticon's agent file contract (see
[`agent-file-mapping.md`](../agent-file-mapping.md) §4 inconsistencies and
[`agent-file-conventions.md`](../agent-file-conventions.md)) is grounded in
domain standards rather than ad-hoc choices.

Every convention below is tied to a primary source. Claims were
fan-out-searched, fetched, and adversarially verified (25 candidate claims →
25 confirmed, 0 refuted); modal-verb caveats from the standards are
preserved. Sources are listed in [§7](#7-sources).

---

## 1. Why this matters for an autonomous red-team system

A pentest deliverable is only as defensible as its evidence trail. The same
property an audit firm needs — *every finding reproducible from stored
artifacts, every action attributable in an append-only log* — is exactly
what an autonomous multi-agent system needs to (a) let the orchestrator make
correct routing decisions, (b) survive context summarization, and (c)
produce a report a human can sign. The industry has converged on a small,
stable set of conventions; adopting them verbatim buys interoperability
(SARIF/ATT&CK consumers, reporting tools) and credibility for free.

AWS's 2026 multi-agent pentest agent independently lands on the same shape:
findings are *"structured reports containing the vulnerability type, affected
endpoints, exploitation evidence, and technical context,"* and candidate
findings *"undergo validation through both deterministic validators and
specialized LLM-based agents that attempt active exploitation"* before being
*"synthesized into final reports with validation results, severity scores,
and exploitation evidence."* That is the evidence-first, validate-before-
promote pattern Decepticon already uses — confirmation the architecture is
on the right track. [AWS]

---

## 2. Evidence & chain-of-custody (the operator log + artifact store)

### 2.1 The append-only activity log (NIST SP 800-115)

NIST SP 800-115 is the baseline standard. It prescribes a **minimum field
set** for the operator activity log and frames that log as the
**deconfliction** mechanism:

> "If an activities log is used, it should include at a minimum the following
> information — date and time, assessor's name, assessment system identifier
> (i.e., IP or MAC), target system identifier (i.e., IP or MAC), tool used,
> command executed, and comments." [NIST]

> "Assessors should keep a log that includes assessment system information
> and a step-by-step record of their activities. This provides an audit
> trail, and allows the organization to distinguish between the actions of
> assessors and true adversaries." [NIST]

**Adoptable schema** — one append-only JSONL record per action:

| Field | NIST term | Decepticon mapping |
|-------|-----------|--------------------|
| `ts` | date and time | already in `timeline.jsonl` / `events.jsonl` |
| `actor` | assessor's name | **gap** — should be the *agent name* (recon/exploit/…) |
| `src` | assessment system identifier | sandbox container / engagement id |
| `target` | target system identifier | target host/URL |
| `tool` | tool used | bash tool / skill invoked |
| `command` | command executed | the actual command string |
| `comments` | comments | free-text note |

> **Caveat:** "append-only" is a design recommendation, not NIST's literal
> wording (NIST says "at a minimum" / "step-by-step record"). Tamper-evidence
> (hash-chaining, signing) is *not* specified by NIST — it is an open design
> question NIST leaves to the implementer.

### 2.2 The artifact store (what must be retained)

NIST enumerates the audit-trail artifacts a store must securely retain:

> "Assessment plans and ROEs; Documentation on system security configuration
> and network architecture; Results from automated tools and other findings;
> Assessment results report; Corrective action plan or Plan of Action and
> Milestones (POA&M)." [NIST]

This maps almost 1:1 onto Decepticon's workspace tree: `plan/` (ROEs,
CONOPS), `recon/`+raw tool output (results from automated tools), `findings/`
(other findings), `report/` (assessment results report). **The one gap is
the POA&M / corrective-action plan** — Decepticon produces remediation inside
findings/report but has no dedicated remediation-tracking artifact.

---

## 3. Findings documentation

### 3.1 The minimum finding schema (convergent across sources)

HackerOne's official training (Hacker101), Bugcrowd's VRT, and the tool data
models (PwnDoc, Faraday, Sysreptor) all converge on the same core fields:

> "A well-written report consists of: A title describing the vulnerable site,
> endpoint, and the vulnerability type; CWE & CVSS score describing the
> criticality of the vulnerability; Clear reproduction steps; An impact
> statement." [Hacker101]

Consolidated **finding field set** (union of the verified schemas):

| Field | Source(s) | Notes |
|-------|-----------|-------|
| Title | Hacker101, PwnDoc, Faraday | site/endpoint + vuln type |
| Vulnerability class / Type | Bugcrowd VRT, PwnDoc, Faraday | see §3.3 |
| **CWE** | Hacker101, Bugcrowd VRT | classification |
| **CVSS score + vector** | Hacker101, FIRST, PwnDoc | store *both* (see §3.2) |
| Severity label | CVSS, Bugcrowd P1–P5 | derived from score |
| Description | PwnDoc, Faraday, Hacker101 | what it is |
| Steps to reproduce / PoC | Hacker101, Faraday | see §3.4 |
| Impact | Hacker101, Faraday | attacker capability |
| Remediation / Resolution | PwnDoc, Faraday | + complexity + priority (PwnDoc) |
| References | PwnDoc, Faraday | external links |
| Affected component / host:service | Faraday | asset linkage |
| Evidence pointers | Faraday, SARIF | see §4 |
| Confirmed (boolean) + Status | Faraday | validation state |
| External ID | Faraday | cross-reference |

PwnDoc's documented schema is the tightest reference: *"A Vulnerability is
defined by: Title, Type, Language, Description, Observation, CVSS,
Remediation, Remediation Complexity, Remediation Priority, References,
Category."* [PwnDoc]

Faraday adds the per-finding fields an autonomous system needs for state:
*Name, Description, Severity, External ID, Status, Confirmed, Ease of
Resolution, Impact, Resolution, Policy Violations, References, Creation
Date.* [Faraday]

> Decepticon's `finding-protocol` operational template (id, severity, title,
> agent, objective_id, discovered_at, evidence_pointer + Description/Evidence/
> Next) is a lean subset. The exploit-reporting heavyweight template (CVSS
> 4.0 vector, CWE, MITRE) adds the rest. **Both are well within industry
> norms** — the gap is consistency, not coverage (see §6).

### 3.2 Severity: CVSS v4.0, store the vector not just the score

FIRST's CVSS v4.0 spec fixes the score→severity bands and **requires the
vector string to be published alongside the score** so the derivation is
reproducible:

> None = 0.0, Low = 0.1–3.9, Medium = 4.0–6.9, High = 7.0–8.9,
> Critical = 9.0–10.0. [FIRST, Table 22]

> "[publishers] provide both the score and the vector string so others can
> understand how the score was derived." [FIRST]

> CVSS v4.0 nomenclature labels — **CVSS-B** (Base), **CVSS-BT**
> (Base+Threat), **CVSS-BE** (Base+Environmental), **CVSS-BTE** — "should be
> used wherever a numerical CVSS value is displayed or communicated." [FIRST]

**Key design implication:** store the **vector string** (which encodes the
version), not just a float. CVSS v3.1 (8 base metrics, includes *Scope*)
remains widely used in 2026 alongside v4.0 (11 base metrics, *Scope*
removed). A bare `cvss_score: 9.3` is ambiguous; `CVSS:4.0/AV:N/AC:L/...` is
self-describing and auditable. PwnDoc models this as three fields —
`cvssv3` (vector), `cvssScore` (numeric), `cvssSeverity` (label). [PwnDoc]

### 3.3 Vulnerability classification: Bugcrowd VRT

Bugcrowd's Vulnerability Rating Taxonomy is the adoptable bug-bounty
vocabulary:

- **P1–P5 priority** scale: P1=Critical, P2=High, P3=Medium, P4=Low,
  P5=Informational. [Bugcrowd VRT]
- **Three-level nested classification**: Category → Sub-Category → Variant
  (e.g. *Server-Side Injection → SQL Injection → Blind*). Storable as the
  finding's vuln-class field. [Bugcrowd VRT]
- **Machine-readable mappings** from each taxonomy entry to CVSS v3/v4, CWE,
  and remediation advice (`mappings/cvss_v4/`, `mappings/cwe/`, etc.,
  governed by `vrt.schema.json`). [Bugcrowd VRT]
- CVSS ranges can auto-prefill the P1–P5 technical severity. [Bugcrowd]

This is directly relevant to Decepticon's *recon-observes / orchestrator-
classifies* split: the VRT category tree is exactly the kind of mapping the
orchestrator's domain-router skills already encode informally. Adopting VRT
identifiers would make classifications interoperable and auditable.

### 3.4 Proof-of-concept structure (reproducibility)

Hacker101's verbatim PoC layout — a ready-made template for an autonomous
finding generator:

> "Description / Introduction; Working proof of concept; HTTP request; HTTP
> Response or the DOM (if needed); Impact Statement." HTTP request submitted
> **as text** (not screenshot). [Hacker101]

HackerOne requires the PoC to address three things:

> "What the vulnerability is; The steps to reproduce the vulnerability; What
> kind of impact an attacker can make if they exploited the vulnerability."
> [HackerOne]

**Text-not-screenshot** for requests/responses is the convention an
autonomous system should prefer anyway — text is greppable, diffable, and
machine-replayable. This validates Decepticon's "save raw evidence to
`findings/evidence/FIND-NNN_*.txt`, reference the path, never inline > 20
lines" rule.

### 3.5 Structured intake (HackerOne)

HackerOne's submission uses structured fields — **Asset (type)**, **Report
Template** (Markdown pre-defined structure), and **Weakness/Issue Type**
(category). [HackerOne] An automated submitter populates exactly these; a
Decepticon finding already carries the equivalents (target, finding template,
vuln class).

---

## 4. Evidence-per-finding linkage (the load-bearing relationship)

Every serious model makes the **finding → evidence** link explicit and
machine-followable:

- **SARIF** (OASIS Standard v2.1.0) links each result to evidence via a
  `physicalLocation` containing an `artifactLocation` (`uri` +
  `uriBaseId` for relative-path resolution) and a `region`, plus
  `logicalLocations` for code constructs. [SARIF]
- **Faraday** links every vulnerability to *at least one host, optionally a
  service*, and stores web-vuln reproducibility as `Request`, `Response`,
  `Method`, `Path`, `Data` fields. [Faraday]
- **Bugcrowd / Decepticon** convention: every shell/credential row carries a
  `finding_id` back-reference; the finding's Evidence table lists the
  artifact path.

**Adoptable rule:** an evidence file is never orphaned and a finding never
asserts without a pointer. Decepticon already encodes this
(`SHELL-NNN.finding_id → FIND-NNN`, `evidence_pointer` frontmatter) — the
research confirms it's the right invariant and suggests tightening it into a
validated constraint.

---

## 5. Interchange & attack-path artifacts (emit standard formats)

A multi-agent system gains interoperability by emitting the formats other
tools already consume:

### 5.1 SARIF — machine-readable findings

> "A SARIF log file SHALL contain a serialization of the SARIF object model
> into the JSON format" and "SHALL be encoded in UTF-8"; the file name
> "SHOULD end with the extension `.sarif`" (MAY add `.json`). [SARIF]

SARIF is the lingua franca for static/dynamic analysis results (GitHub code
scanning, DefectDojo import, etc.). Decepticon's analyst *ingests* SARIF via
`kg_ingest("sarif", ...)` **and already emits** it: `tools/reporting/sarif.py`
`render_sarif()` serializes the engagement KG (Vulnerability/Finding nodes
populated from `findings/FIND-NNN.md`) to SARIF v2.1.0, and the
`decepticon scan --sarif-output` CLI path exposes it. So this is **already
aligned**, not a gap.

### 5.2 MITRE ATT&CK Navigator layers — coverage / attack-path

> "The ATT&CK Navigator stores layers as JSON" with required top-level fields
> `name` and `domain` (`enterprise-attack` | `mobile-attack` |
> `ics-attack`); each technique annotation is keyed by `techniqueID` in
> canonical `T####` / `T####.###` (sub-technique) format. [MITRE]

Decepticon findings already carry MITRE technique fields and build attack-
path narratives (`findings/attack-paths/PATH-NNN.md` with per-step T-IDs), and
it **already emits** an ATT&CK Navigator layer: `tools/defense/brief.py`
`export_attack_navigator()` / `build_navigator_layer()` writes a v4.5 layer
(detected techniques green, gaps red) for the blue-cell / Offensive-Vaccine
direction. So this is **already aligned** — the open item is wiring the same
layer export into the offensive final-report path, not building it.

### 5.3 DefectDojo unified import / OCSF

DefectDojo's universal parser centralizes findings from any tool; OCSF is an
emerging open finding schema. (Both were in scope but produced no
*surviving* verified claim in this pass — flagged as an open question in
§8.) The pragmatic target today is **SARIF + ATT&CK Navigator**, which are
unambiguously standardized.

---

## 6. Shared-workspace / collaborative data models

The reporting tools agree on a **hierarchical container model** an agent
system can mirror as its directory/relational layout:

- **Faraday:** `Workspace → Host/Target → Service (name+port) → Vulnerability`.
  Web vulns parent to a service, confirming host→service→finding nesting.
  [Faraday]
- **PwnDoc / Sysreptor:** project → fixed finding schema (§3.1), with
  templates for reusable finding definitions.

Decepticon's workspace (`plan/`, `recon/`, `exploit/`, `post-exploit/`,
`findings/`, `report/`) is **phase-organized**, while Faraday is
**asset-organized** (host→service→finding). For a kill-chain agent the
phase organization is the right primary axis, but the research suggests the
**knowledge graph** (Host/Service/Finding nodes) should carry the
asset-organized view in parallel — which Decepticon's `kg_record` schema
already does. The two views are complementary: files for human/handoff,
graph for asset-relational queries.

---

## 7. Mapping to Decepticon: alignment & gaps

| Convention (sourced) | Decepticon today | Verdict |
|----------------------|------------------|---------|
| Append-only activity log w/ NIST fields | `timeline.jsonl` + `events.jsonl` | **Aligned**; add `actor=agent`, `tool`, `command`, `target` to reach NIST minimum |
| Tamper-evident chain-of-custody | `audit.jsonl` HMAC-chained (RoE decisions) | **Ahead of NIST** — extend hash-chaining to the activity log |
| Artifact store contents | `plan/`+`recon/`+`findings/`+`report/` | **Aligned**; missing POA&M/remediation-tracking artifact |
| Finding minimum schema | `finding-protocol` + exploit-reporting templates | **Aligned** in coverage; inconsistent in practice (§ mapping doc §4) |
| CVSS vector stored, not just score | exploit-reporting uses `cvss_vector` (v4.0) | **Aligned**; make vector mandatory everywhere, never bare score |
| CWE + ATT&CK on every finding | present in heavyweight template | **Partial** — operational-tier findings often omit CWE |
| VRT-style vuln classification | informal domain-router skills | **Applied** — optional `vrt` field added to finding-protocol + final-report deliverable schema |
| PoC = text request/response | "save evidence to file, don't inline" rule | **Aligned** |
| Evidence-per-finding linkage | `finding_id` back-refs + `evidence_pointer` | **Aligned**; promote to a validated invariant |
| Emit SARIF | `render_sarif()` emits v2.1.0 from KG + `scan --sarif-output` | **Aligned** (already implemented) |
| Emit ATT&CK Navigator layer | `export_attack_navigator()` writes v4.5 layer (blue-cell) | **Aligned**; remaining: wire into offensive final-report |
| Asset-relational view | KG Host/Service/Finding nodes | **Aligned** (graph channel) |

### Highest-value actions for the redesign — APPLIED 2026-06-12

The redesign below was implemented in the skill/prompt contract (see the
"Redesign applied" note at the top of `agent-file-mapping.md`):

1. **Finding-filename contract fixed** — operational tier keeps the stable
   `findings/FIND-NNN.md` key (matches code: `shutdown.py` glob/write, SARIF
   renderer, all `finding_id` cross-refs); the stray `{severity}-{slug}.md`
   prose in recon/exploit/post-exploit/final-report skills was corrected to
   `FIND-NNN.md`. The **deliverable tier** now uses a severity-sorted,
   human-readable `report/<severity><NN>-<slug>.md` (e.g.
   `report/critical01-struts-rce.md`), generated once at engagement end when
   severity is final, with `id: FIND-NNN` retained in frontmatter for
   traceability.
2. **Credentials path unified** to `exploit/creds/initial.json` (subdir,
   co-located with `creds/credentials.md`).
3. **CVSS vector + CWE** made explicit/required at deliverable tier (vector,
   not just score, per FIRST); CWE/VRT added to finding-protocol with the
   "optional operational / required deliverable" rule.
4. **VRT identifiers adopted** — optional `vrt` field
   (`category/sub-category/variant`) in both finding tiers.
5. **SARIF + ATT&CK Navigator** confirmed already implemented (not gaps);
   remaining work is wiring the Navigator export into the offensive
   final-report path.

**Deferred (code-level, separate change):** extending the operator activity
log to the full NIST field set + hash-chaining it like `audit.jsonl`. The
NIST requirements are *currently met in aggregate* (see §2.1 mapping below):
`events.jsonl` is the redacted structural audit trail, `.sessions/*.log`
holds the full command+output (NIST "command executed"), and `audit.jsonl`
is the HMAC-chained RoE-decision ledger. Storing raw commands into
`events.jsonl` was deliberately avoided — the middleware redacts args by
design to keep secrets/payloads out of the event log.

---

## 8. Caveats & open questions

**Caveats (from verification):**
- NIST SP 800-115 is 2008-vintage — durable field schema, but predates
  cloud/container/ATT&CK; treat as a *floor*, not a complete model.
- Several conventions are normative **SHOULD**, not hard MUST (NIST "at a
  minimum", FIRST nomenclature, SARIF `.sarif` naming, HackerOne PoC
  guidance). They are strong recommendations.
- Tool schemas (PwnDoc, Faraday, Sysreptor) are vendor-specific and
  extensible, not universal standards; PwnDoc's `pwndoc-ng` fork uses a
  nested CVSS object instead of three flat fields.
- "Append-only" log property is a sound design recommendation, not literal
  NIST attribution.

**Coverage gaps (in scope but no surviving verified claim this pass):**
PTES, OSSTMM, CREST, OWASP WSTG, and PCI-DSS pentest guidance; the on-disk
layouts of GhostWriter / Sysreptor / Dradis / AttackForge / DefectDojo /
Serpico; OCSF; and the broader 2025-2026 AI-assisted evidence-collection
literature. These underrepresent in this synthesis and warrant a focused
follow-up.

**Open questions for the redesign:**
1. How should append-only operator logs be made tamper-evident
   (hash-chaining / signed entries)? Decepticon's `audit.jsonl` already
   answers this for RoE decisions — extend the pattern.
2. What conventions govern **AI-agent-generated** evidence specifically —
   provenance/attestation of *which agent* produced a finding, automated PoC
   reliability scoring, human-triage gating? (NIST/SARIF/Faraday are
   human-centric; agent provenance is novel ground.)
3. Do PTES / OWASP WSTG / CREST prescribe evidence-naming or per-finding
   linkage that extends the NIST/SARIF/Faraday models verified here —
   especially for attack-path narratives and purple-team detection-gap
   reporting?
4. Should Decepticon target DefectDojo unified import / OCSF in addition to
   SARIF for downstream interoperability?

---

## 9. Sources

Primary sources carry the most weight; all core claims were verified against
these.

| # | Source | Type | Used for |
|---|--------|------|----------|
| NIST | [NIST SP 800-115](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-115.pdf) | primary (standard) | activity-log fields, artifact store, deconfliction |
| FIRST | [CVSS v4.0 Specification](https://www.first.org/cvss/v4-0/specification-document) | primary (standard) | severity bands, vector+score, nomenclature |
| Bugcrowd VRT | [vulnerability-rating-taxonomy](https://github.com/bugcrowd/vulnerability-rating-taxonomy) + [CVSS mapping](https://docs.bugcrowd.com/changelog/customers/cvss-scoring-mapped-to-technical-severity/) | primary | P1–P5, Category→Sub→Variant, CWE/CVSS mappings |
| Hacker101 | [Writing a Report and CVSS](https://www.hacker101.com/resources/articles/writing_a_report_and_cvss.html) | primary | finding fields, PoC layout |
| HackerOne | [Submitting Reports](https://docs.hackerone.com/en/articles/8473994-submitting-reports) | primary | PoC three-elements, structured intake |
| PwnDoc | [vulnerabilities.md](https://github.com/pwndoc/pwndoc/blob/main/docs/vulnerabilities.md) | primary (tool) | fixed finding schema, CVSS three-field |
| Faraday | [Vulns docs](https://docs.faradaysec.com/Vulns/) | primary (tool) | workspace→host→service→finding, web evidence fields |
| MITRE | [ATT&CK Navigator layer format v4.5](https://github.com/mitre-attack/attack-navigator/blob/master/layers/spec/v4.5/layerformat.md) | primary (standard) | attack-path layer JSON, techniqueID format |
| SARIF | [OASIS SARIF v2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) | primary (standard) | JSON interchange, `.sarif` naming, location/evidence model |
| AWS | [Inside AWS Security Agent](https://aws.amazon.com/blogs/security/inside-aws-security-agent-a-multi-agent-architecture-for-automated-penetration-testing/) | primary (vendor) | multi-agent evidence/validation pattern (2026) |
| Sysreptor | [CLI finding docs](https://docs.sysreptor.com/cli/projects-and-templates/finding/) | primary (tool) | finding template model |
| DefectDojo | [Universal parser](https://defectdojo.com/blog/defectdojo-universal-parser-explained-how-to-centralize-security-findings-from-any-security-tool) | secondary | unified import (open question) |

*Research method: 5-angle fan-out web search → 24 sources fetched → 109
claims extracted → 25 adversarially verified (3-vote) → 25 confirmed, 0
refuted. Underrepresented angles noted in §8.*
