---
name: testing-decepticon
description: How to run Decepticon's local CI gates and compose smoke test (make smoke, ci-lint, ci-test, check-skill-graph), including required .env and env-var pitfalls.
---

# Testing Decepticon locally

## Prereqs
- `uv` (Python 3.10): `uv sync --frozen` installs all deps.
- Docker + docker compose v2 for `make smoke`.
- `make check-skill-graph` needs the MITRE ATT&CK STIX bundle at
  `~/.cache/skillogy/mitre/enterprise-attack-<version>.json` (e.g. 19.1, from
  https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-19.1.json).

## Gates
- `make ci-lint` — ruff check + format --check + basedpyright error gate (writes `bp.json`; delete after).
- `make ci-test` — IMPORTANT: run with provider keys UNSET, e.g.
  `env -u MOONSHOT_API_KEY -u KIMI_API_KEY make ci-test`. If real provider keys are
  exported, `TestResolveCredentials` cases in
  `packages/decepticon/tests/unit/llm/test_factory.py` fail by design (they don't
  delenv those vars). Expected: ~5300 passed / ~44 skipped (Neo4j + Windows skips are normal).
- `make check-skill-graph` — verifies `skills/.graph/skills.cypher` matches build output.
  Name-resolution WARNINGs from skillogy MoC are harmless offline noise.

## make smoke (compose build + boot + health)
- Requires a `.env` at the repo root: `cp .env.example .env` is enough (placeholder keys
  boot fine); without it, `compose up` fails with "env file .env not found" (Error 14).
  Optionally set one real key (e.g. `MOONSHOT_API_KEY`) to test a live completion via
  LiteLLM: `curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer sk-decepticon-master" ...`.
- First build downloads a large Kali sandbox image (~470MB of apt packages); allow ~10 min.
- Success prints `=== smoke OK ===` with `kg: OK`, `neo4j: OK`, `web: SKIP`.
- Teardown: `make clean` (purges containers + volumes). Remove the test `.env` afterwards.

## Devin Secrets Needed
- `MOONSHOT_API_KEY` (optional, only for live LiteLLM completion checks).
