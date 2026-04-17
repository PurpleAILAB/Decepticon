# Models

Decepticon routes LLM requests through a [LiteLLM](https://github.com/BerriAI/litellm) proxy, which supports Anthropic, OpenAI, and Google backends with automatic failover.

---

## Model Profiles

Three profiles control which models are assigned to which agent roles.

### `eco` — Production (default)

Balanced cost and performance. Recommended for most engagements.

| Role | Primary | Fallback |
|------|---------|---------|
| Orchestrator | `claude-opus-4-6` | `gpt-5.4` |
| Planner | `claude-opus-4-6` | `gpt-5.4` |
| Soundwave | `claude-haiku-4-5` | `gemini-2.5-flash` |
| Exploit | `claude-sonnet-4-6` | `gpt-4.1` |
| Recon | `claude-haiku-4-5` | `gemini-2.5-flash` |
| Post-Exploit | `claude-sonnet-4-6` | `gpt-4.1` |

### `max` — High-value targets

Opus or Sonnet everywhere. Use for complex engagements where accuracy matters more than cost.

| Role | Primary | Fallback |
|------|---------|---------|
| Orchestrator | `claude-opus-4-6` | `gpt-5.4` |
| Planner | `claude-opus-4-6` | `claude-sonnet-4-6` |
| Soundwave | `claude-sonnet-4-6` | `claude-haiku-4-5` |
| Exploit | `claude-opus-4-6` | `claude-sonnet-4-6` |
| Recon | `claude-sonnet-4-6` | `claude-opus-4-6` |
| Post-Exploit | `claude-opus-4-6` | `claude-sonnet-4-6` |

### `test` — Development / CI

Haiku everywhere. No fallback. Minimizes cost during development and automated testing.

| Role | Primary | Fallback |
|------|---------|---------|
| All roles | `claude-haiku-4-5` | — |

---

## Setting the Profile

In your `.env` file (edit with `decepticon config`):

```bash
DECEPTICON_MODEL_PROFILE=eco    # eco | max | test
```

The default is `eco` if not set.

---

## Fallback Chain

`ModelFallbackMiddleware` handles failover transparently. When the primary model returns an error (provider outage, rate limit, context length exceeded), it automatically retries with the fallback model.

The switch is seamless — the agent continues with no interruption.

---

## Supported Models

Models are referenced using LiteLLM's `provider/model` format in `decepticon/llm/models.py`.

| Provider | Model ID | Notes |
|----------|----------|-------|
| Anthropic | `anthropic/claude-opus-4-6` | Most capable |
| Anthropic | `anthropic/claude-sonnet-4-6` | Balanced |
| Anthropic | `anthropic/claude-haiku-4-5` | Fast, low cost |
| OpenAI | `openai/gpt-5.4` | GPT fallback for Opus |
| OpenAI | `openai/gpt-4.1` | GPT fallback for Sonnet |
| Google | `gemini/gemini-2.5-flash` | Gemini fallback for Haiku |

Any model supported by LiteLLM can be added. Edit `config/litellm.yaml` to add new providers or routes.

---

## LiteLLM Proxy

All LLM traffic flows through the LiteLLM proxy container (`port 4000`). This provides:

- **Unified API** — agents use one endpoint regardless of backend
- **Usage tracking** — token consumption per model, per agent role
- **Rate limiting** — configurable per provider
- **Billing aggregation** — cost attribution across providers

Configuration: `config/litellm.yaml`

Authentication: set `LITELLM_MASTER_KEY` in your `.env` file.
