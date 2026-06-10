-- KG schema v004 — Technology node kind for AI-surface and tech-detection
-- signals (ADR-0007).
--
-- A Technology node is a named product/runtime detected on or behind a
-- Service — an AI runtime (Ollama, vLLM), an AI proxy, a web framework.
-- Recon classifiers (HTTP header, port catalog, nmap banner, frontend
-- title) MERGE into this label and link it ``(Service)-[:RUNS]->(Technology)``
-- so detections become typed, queryable graph data the chain planner and
-- the llm-redteam plugin can route on, instead of flat Service properties.
--
-- Same ``(key, engagement)`` composite invariant as V001/V003: the same
-- ``<category>:<name>`` key in two engagements is two nodes (multi-tenant);
-- the same key in one engagement is one node (idempotent MERGE so two
-- classifiers corroborating the same product converge).

CREATE CONSTRAINT technology_key_engagement IF NOT EXISTS
  FOR (n:Technology) REQUIRE (n.key, n.engagement) IS UNIQUE;

-- Engagement-scoped category lookup — "which AI runtimes did we find in
-- this engagement" is the primary read path for the llm-redteam plugin.
CREATE INDEX engagement_technology_category IF NOT EXISTS
  FOR (n:Technology) ON (n.engagement, n.category);
