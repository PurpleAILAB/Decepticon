# SPEC

## §G GOAL
Port selected Strix v1.5.0 capabilities into Decepticon without parallel architecture.

## §C CONSTRAINTS
- Reuse Decepticon plugin, role, KG, reporting, LLM, sandbox contracts.
- ∀ API operation, dependency finding, container → engagement-scoped + provenance-tagged.
- API import ! parse-only; network actions remain RoE + egress-gated.
- No second plugin manager, skill store, graph schema, UI server, or agent loop.
- Preserve public tool/API contracts unless additive.
- Both source projects Apache-2.0; retain notices for copied code, prefer native implementation.

## §I INTERFACES
- tool: API spec/collection import → compact JSON inventory + KG observations.
- tool: `cve_enrich_dependencies` → repo-relative manifest path, chain, reachability evidence.
- report: finding severity → demonstrated-impact ceiling + evidence level.
- env: `DECEPTICON_LLM_EXTRA_HEADERS` → JSON object, optional OpenAI-compatible request headers.
- env: `DECEPTICON_LLM_DISABLE_STREAMING` → opt-in non-streaming OpenAI-compatible calls.
- runtime: dynamic container → engagement/run identity label; teardown selects matching label.

## §R RESEARCH
id|topic|finding|src
R1|Strix v1.5.0|Adds API spec/Postman targets, dependency reachability evidence, impact-calibrated severity, LLM compatibility controls, run labels|https://github.com/usestrix/strix/releases/tag/v1.5.0
R2|SCA baseline|`cve_enrich_dependencies` parses 4 manifest forms, ranks OSV/NVD/EPSS/KEV results, but lacks manifest provenance + reachability ladder|https://github.com/PurpleAILAB/Decepticon/blob/main/packages/decepticon/decepticon/tools/research/tools.py#L558-L684
R3|extension contracts|Plugins, roles, skills, middleware, KG ingesters already first-class; new features ! extend nearest contract|https://github.com/PurpleAILAB/Decepticon/tree/main/packages/decepticon-core/decepticon_core
R4|license|Strix + Decepticon Apache-2.0|https://github.com/usestrix/strix/blob/v1.5.0/LICENSE

## §V INVARIANTS
V1: ∀ imported API op → engagement + source provenance; import sends no network request.
V2: ∀ imported API op → request execution still passes RoE + egress gates.
V3: ∀ dependency finding → engagement-workspace-relative manifest path + evidence level; outside path emits no provenance path.
V4: reported severity ≤ evidence ceiling: declared≤low, resolved≤medium, symbol/call-path≤high, runtime-observed≤critical; raw CVSS/EPSS/KEV remains retained.
V5: header config ! JSON string map; reject `Authorization`, `Host`, `Content-Length`; non-streaming preserves usage + error handling.
V6: ∀ dynamic container → engagement/run label; teardown filters both labels.
V7: all new data survives existing serialisation, reporting, and engagement isolation paths.
V8: API import accepts local OpenAPI/Postman JSON/YAML only; external `$ref` ⊥ resolves.
V9: workload profile owned by one engagement; generated run ID labels every created dynamic container.

## §T TASKS
id|status|task|cites
T1|x|add OpenAPI/Postman import tool + KG adapter|V1,V2,V7,V8,I.tool
T2|x|add dependency chain + reachability evidence|V3,V7,I.tool
T3|x|cap report severity by impact evidence|V4,V7,I.report
T4|x|add LLM header + non-streaming controls|V5,I.env
T5|x|label dynamic containers by run|V6,I.runtime
T6|x|test imported capabilities + regression paths|V1,V2,V3,V4,V5,V6,V7

## §B BUGS
id|date|cause|fix
B1|2026-08-09|`uv run pytest` timeout before collection|retry direct venv pytest; no code invariant
B2|2026-08-09|dependency-evidence test skipped helper call|invoke `_dependency_chains` before assertion
B3|2026-08-09|test expected raw CVSS, not KEV-adjusted score|assert existing composite score
B4|2026-08-09|async cleanup test asserted before unrelated start completed|wait for seeded workload starts
