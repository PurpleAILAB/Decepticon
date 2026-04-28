# Models

Decepticon routes every LLM call through a [LiteLLM](https://github.com/BerriAI/litellm) proxy that abstracts Anthropic, OpenAI, Google, and MiniMax behind a single endpoint. The model assigned to each agent — and the model that takes over when the primary fails — is computed at startup from your **credentials inventory** plus the active **profile**.

You don't pick agent-by-agent models manually. You tell Decepticon which credentials you have, in what order of preference; it builds the chain.

---

## How model selection works

Three orthogonal axes:

| Axis        | Values                                                                                                | Decided by              |
|-------------|--------------------------------------------------------------------------------------------------------|--------------------------|
| **Tier**    | `HIGH` / `MID` / `LOW`                                                                                 | Agent (e.g. orchestrator → HIGH, recon → LOW), overridable by profile |
| **AuthMethod** | `anthropic_oauth` / `anthropic_api` / `openai_api` / `google_api` / `minimax_api`                  | Your credentials inventory |
| **Profile** | `eco` / `max` / `test`                                                                                 | `DECEPTICON_MODEL_PROFILE` |

For each agent, Decepticon resolves a tier (from the profile) and walks your AuthMethod priority list, emitting the model identifier that method provides at that tier. The first hit is the primary; **every remaining hit is queued as a fallback in priority order**. langchain's `ModelFallbackMiddleware` walks the queue on primary failure, trying each method in turn until one succeeds.

### Tier × AuthMethod matrix

|                     | **HIGH**                       | **MID**                        | **LOW**                            |
|---------------------|--------------------------------|--------------------------------|------------------------------------|
| `anthropic_api`     | `anthropic/claude-opus-4-7`    | `anthropic/claude-sonnet-4-6`  | `anthropic/claude-haiku-4-5`       |
| `anthropic_oauth`   | `auth/claude-opus-4-7`         | `auth/claude-sonnet-4-6`       | `auth/claude-haiku-4-5`            |
| `openai_api`        | `openai/gpt-5.5`               | `openai/gpt-5.4`               | `openai/gpt-5-nano`              |
| `google_api`        | `gemini/gemini-2.5-pro`        | `gemini/gemini-2.5-flash`      | `gemini/gemini-2.5-flash-lite`     |
| `minimax_api`       | `minimax/MiniMax-M2.5`         | `minimax/MiniMax-M2.5-lightning`         | — *(falls through to next method)* |

When a method has no model at the requested tier (MiniMax LOW), the resolver skips it and continues with the next method in your priority list.

---

## Profiles

`DECEPTICON_MODEL_PROFILE` (default: `eco`) controls which tier each agent runs at.

### `eco` — per-agent tier (production default)

Each agent runs at the tier suited to its workload:

| Tier  | Agents                                                                                          |
|-------|-------------------------------------------------------------------------------------------------|
| HIGH  | `decepticon`, `exploiter`, `patcher`, `contract_auditor`, `analyst`, `vulnresearch`              |
| MID   | `exploit`, `detector`, `verifier`, `postexploit`, `defender`, `ad_operator`, `cloud_hunter`, `reverser` |
| LOW   | `soundwave`, `recon`, `scanner`                                                                 |

### `max` — every agent on HIGH

For high-value targets where accuracy outweighs cost. Forces every agent to the HIGH tier.

### `test` — every agent on LOW

For development / CI. Forces every agent to the cheapest tier (Haiku-class).

---

## Credentials inventory

Your inventory is built at startup from environment variables, written by `decepticon onboard`.

```bash
# Priority order (first = preferred). Defaults to:
#   anthropic_oauth,anthropic_api,openai_api,google_api,minimax_api
DECEPTICON_AUTH_PRIORITY=anthropic_oauth,openai_api

# Set true if you have an active Claude Code OAuth subscription
# (anthropic_oauth in the priority list above).
DECEPTICON_AUTH_CLAUDE_CODE=true

# Per-method credentials. Placeholder values (`your-..-key-here`) are
# treated as "not configured" and silently dropped from the inventory.
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
MINIMAX_API_KEY=eyJ...
```

The factory walks the priority list, drops methods whose detection check fails (placeholder API key, or `DECEPTICON_AUTH_CLAUDE_CODE=false`), and uses what's left.

---

## Fallback chain examples

All examples assume the `eco` profile.

### Single API key (Anthropic only)

```
DECEPTICON_AUTH_PRIORITY=anthropic_api
ANTHROPIC_API_KEY=sk-ant-...
```

| Agent (tier)     | Primary                       | Fallback |
|------------------|-------------------------------|----------|
| decepticon (HIGH)| `anthropic/claude-opus-4-7`   | —        |
| exploit (MID)    | `anthropic/claude-sonnet-4-6` | —        |
| recon (LOW)      | `anthropic/claude-haiku-4-5`  | —        |

No fallback — only one credential.

### Single API key (OpenAI only)

```
DECEPTICON_AUTH_PRIORITY=openai_api
OPENAI_API_KEY=sk-...
```

| Agent (tier)     | Primary               | Fallback |
|------------------|------------------------|----------|
| decepticon (HIGH)| `openai/gpt-5.5`      | —        |
| exploit (MID)    | `openai/gpt-5.4`      | —        |
| recon (LOW)      | `openai/gpt-5-nano` | —        |

### Claude Code OAuth + Anthropic API (subscription primary, paid fallback)

```
DECEPTICON_AUTH_PRIORITY=anthropic_oauth,anthropic_api
DECEPTICON_AUTH_CLAUDE_CODE=true
ANTHROPIC_API_KEY=sk-ant-...
```

| Agent (tier)     | Primary                  | Fallback                         |
|------------------|---------------------------|----------------------------------|
| decepticon (HIGH)| `auth/claude-opus-4-7`   | `anthropic/claude-opus-4-7`     |
| exploit (MID)    | `auth/claude-sonnet-4-6` | `anthropic/claude-sonnet-4-6`   |
| recon (LOW)      | `auth/claude-haiku-4-5`  | `anthropic/claude-haiku-4-5`    |

OAuth runs primary (no API cost). When the subscription quota hits, fallback drops to the paid API key — same model family, same quality.

### Mixed providers (Anthropic + OpenAI)

```
DECEPTICON_AUTH_PRIORITY=anthropic_api,openai_api
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

| Agent (tier)     | Primary                       | Fallback                |
|------------------|-------------------------------|-------------------------|
| decepticon (HIGH)| `anthropic/claude-opus-4-7`   | `openai/gpt-5.5`        |
| exploit (MID)    | `anthropic/claude-sonnet-4-6` | `openai/gpt-5.4`        |
| recon (LOW)      | `anthropic/claude-haiku-4-5`  | `openai/gpt-5-nano`   |

Cross-provider fallback — when Anthropic hits a rate limit or outage, OpenAI takes over seamlessly.

### MiniMax-only (LOW gap)

```
DECEPTICON_AUTH_PRIORITY=minimax_api
MINIMAX_API_KEY=eyJ...
```

| Agent (tier)     | Primary                | Notes                                     |
|------------------|------------------------|-------------------------------------------|
| decepticon (HIGH)| `minimax/MiniMax-M2.5` | OK                                        |
| exploit (MID)    | `minimax/MiniMax-M2.5-lightning` | OK                                        |
| recon (LOW)      | *(role unassigned)*    | MiniMax has no LOW model and no fallback method |

The Recon/Scanner/Soundwave roles fail to initialize. Add a second AuthMethod (e.g. `openai_api`) to fill the LOW slot.

---

## Failover behavior

`ModelFallbackMiddleware` (from `langchain.agents.middleware`) watches every LLM call. On primary failure (provider outage, 429 rate limit, context overflow, network error), it transparently retries each queued fallback in order until one succeeds. Agents see no interruption — same conversation history, same tool call.

The middleware receives the full chain `[primary, *fallbacks]` from `LLMFactory.get_fallback_models(role)`. If the user has all five AuthMethods configured, that's a five-deep chain; with a single credential it's primary-only and the middleware short-circuits. The chain length scales with credentials inventory — no upper cap, no silent truncation. Only when every method fails does the agent surface the error.

---

## LiteLLM proxy

All traffic flows through the LiteLLM container on port 4000. The proxy provides:

- **Unified API** — agents call one endpoint, model identifier picks the backend
- **Usage tracking** — tokens per model per agent role
- **Rate limiting** — per-provider knobs
- **Cost attribution** — billing data aggregated across providers

Configuration: `config/litellm.yaml`. Authentication: `LITELLM_MASTER_KEY` in `.env`.

---

## Adding a model

To wire in a new provider model:

1. Add a `model_list` entry to `config/litellm.yaml` with the LiteLLM `provider/model` identifier and the env var that holds the key.
2. Add the model identifier to the appropriate cell of `METHOD_MODELS` in `decepticon/llm/models.py`.
3. If introducing a new AuthMethod, also add it to `AuthMethod`, the factory's `_API_METHOD_ENV` map, and the onboard wizard's option list.

Tests in `tests/unit/llm/test_models.py` will catch dropped tiers or missing matrix entries.
