# 0007. Add a Technology knowledge-graph node kind for AI-surface and tech-detection signals

- **Status:** Accepted
- **Date:** 2026-06-06
- **Deciders:** @PurpleCHOIms
- **Related:** #593 (Redamon integration roadmap), `docs/proposals/redamon-feature-integration.md`,
  `docs/proposals/redamon-top3-integration-plan.md`; PR #598 (Technology NodeKind on KGStore),
  PR #600 / #601 / #602 / #603 / #604 (AI-surface classifier ingests on nmap + httpx)

## Context

The gap analysis in #593 found that Decepticon's single largest categorical blind spot is
AI-attack-surface discovery: the `llm-redteam` plugin can attack exposed Ollama / vLLM / LangChain /
MLflow / ComfyUI instances, but recon has no way to *recognize* them. Today an open port `11434` is
ingested as a `Service` with `service=unknown` (`kg_ingest_masscan`), an Ollama banner is copied
verbatim from nmap, and an `httpx` title or response header naming an AI stack is stored as a flat
property no agent routes on. The cheap, deterministic classifiers that would fix this (header / port /
title / banner / endpoint catalogs) all need somewhere to write a *typed, queryable* result.

The same missing primitive blocks the broader recon tech-detection upgrade (whatweb / Wappalyzer →
versioned products that CVE cross-referencing assumes as input). Both clusters want the same thing: a
first-class graph node representing "a named piece of technology running on / behind a service," with a
category and a detection provenance.

KG node kinds live in `packages/decepticon-core/decepticon_core/types/kg.py` and are part of the
public type surface (exercised by `packages/decepticon-core/tests/test_public_api_stability.py` and
`packages/decepticon-core/tests/test_kg_detection_types.py`). Adding one is a deliberate schema
decision, not an incidental change —
hence this ADR rather than a drive-by type addition.

## Decision

Add a `Technology` node kind to the knowledge graph, with a companion migration:

- **Identity:** `MERGE` on `(key, engagement)` where `key` is a normalized
  `<category>:<name>` (e.g. `ai-runtime:ollama`), preserving the existing per-engagement isolation
  invariant every other node kind follows.
- **Properties:** `name`, `category` (enum incl. `ai-runtime`, `ai-proxy`, `ai-framework`,
  `ai-sdk-client`, plus generic web-tech categories), optional `version`, and `detected_by`
  (provenance: `httpx-ai-header`, `port-catalog`, `nmap-banner`, `title-regex`, `whatweb`, …).
- **Relationships:** `RUNS` from a `Service`/`Host` to the `Technology` it exposes.
- A low-confidence title/banner match is recorded as corroborating-only (`_guess`) so it cannot, on
  its own, drive an exploit chain.

The classifier PRs in #593 (AI header / port / title / endpoint, and later whatweb tech-detection)
write into this node kind. They are explicitly out of scope for this ADR, which decides only the
schema.

## Consequences

- **Easier:** AI-surface and tech-detection signals become typed, queryable graph data the chain
  planner and `llm-redteam` plugin can route on; each classifier PR becomes a small, self-contained
  ingester change rather than inventing ad-hoc properties.
- **Harder:** one more node kind to maintain in the public type surface and its stability tests; the
  category enum needs an owned, finite vocabulary (we do not want unbounded free-text categories).
- **Given up:** storing tech detections as loose `Service` properties. That option is rejected below.
- **Migration:** a forward migration adds the node label + the `(key, engagement)` uniqueness
  constraint. No existing data is rewritten; the node kind is additive. Existing ingesters are
  unchanged until their own PRs land.

## Alternatives considered

- **Flat properties on the `Service` node** (e.g. `service.ai_runtime = "ollama"`). Rejected: a host
  can run multiple technologies (an AI proxy *and* the framework behind it), versions and provenance
  do not fit a single scalar, and the chain planner cannot traverse a property the way it traverses a
  `RUNS` edge.
- **Reuse the existing `Vulnerability`/`Finding` kinds.** Rejected: a detected technology is not a
  finding; conflating "MLflow is here" with "MLflow here is vulnerable" pollutes findings counts and
  the remediation roadmap.
- **A free-text `category` string.** Rejected: an unbounded vocabulary defeats the closed-label design
  that keeps KG queries parameterized and injection-safe; the enum is the point.
