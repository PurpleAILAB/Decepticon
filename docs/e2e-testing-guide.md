# E2E Testing Guide — LLM Gateway Enhancement

Manual testing procedures for verifying the LLM gateway features.

## Prerequisites

- Docker and Docker Compose installed
- At least one LLM provider API key or an authorized local/OpenAI-compatible model endpoint
- `make dev` successfully starts all services

## Scenario 1: API Key Provider Routing

**Providers:** Anthropic, OpenAI, Google, MiniMax

### Steps
1. Set API key(s) in `~/.decepticon/.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
2. Start services: `make dev`
3. Verify LiteLLM health: `curl http://localhost:4000/health`
4. Test model routing:
   ```bash
   curl -X POST http://localhost:4000/chat/completions \
     -H "Authorization: Bearer sk-decepticon-master" \
     -H "Content-Type: application/json" \
     -d '{"model": "anthropic/claude-haiku-4-5", "messages": [{"role": "user", "content": "Say hello"}]}'
   ```
5. Verify response contains a valid completion

### Expected
- HTTP 200 with model response
- LiteLLM logs show the request routed to Anthropic

### Troubleshooting
- 401: Check API key is set in `.env` and loaded by Docker
- 404: Verify model name matches `config/litellm.yaml` entries


## Scenario 2: Custom LiteLLM Model Routing

### Prerequisites
- A provider API key or a local/OpenAI-compatible gateway you are authorized to use

### Steps
1. Set a custom model and matching provider key in your environment file:
   ```bash
   DECEPTICON_MODEL_PROFILE=custom
   DECEPTICON_MODEL=openrouter/anthropic/claude-3.7-sonnet
   OPENROUTER_API_KEY=sk-or-v1-...
   ```
2. Start services: `make dev`
3. Verify LiteLLM health: `curl http://localhost:4000/health`
4. Test the custom route:
   ```bash
   curl -X POST http://localhost:4000/chat/completions \
     -H "Authorization: Bearer sk-decepticon-master" \
     -H "Content-Type: application/json" \
     -d '{"model": "openrouter/anthropic/claude-3.7-sonnet", "messages": [{"role": "user", "content": "Say hello"}]}'
   ```

### Expected
- LiteLLM startup logs show dynamic model route registration
- HTTP 200 with a model response

### Troubleshooting
- 401: Check the provider-specific API key variable (`OPENROUTER_API_KEY`, `GROQ_API_KEY`, etc.)
- 404: Check `DECEPTICON_MODEL` uses LiteLLM `provider/model` format


## Scenario 3: OpenAI-Compatible Gateway or Local Model

### Prerequisites
- A local or private gateway that exposes an OpenAI-compatible `/v1` API, or Ollama for `ollama/*` models

### Steps
1. Configure a custom gateway:
   ```bash
   DECEPTICON_MODEL_PROFILE=custom
   DECEPTICON_MODEL=custom/qwen3-coder
   CUSTOM_OPENAI_API_BASE=https://gateway.example.test/v1
   CUSTOM_OPENAI_API_KEY=...
   ```
2. Or configure Ollama:
   ```bash
   DECEPTICON_MODEL_PROFILE=custom
   DECEPTICON_MODEL=ollama/llama3.2
   OLLAMA_API_BASE=http://host.docker.internal:11434
   ```
3. Start services and call the selected model through LiteLLM.

### Expected
- The selected model responds through LiteLLM
- No consumer subscription/OAuth token is required

### Troubleshooting
- Connection refused: confirm the gateway is reachable from Docker (`host.docker.internal` is available in the compose file)
- Authentication errors: use an official provider API key or an authorized gateway token


## Scenario 4: Ollama Local Provider

### Prerequisites
- Ollama installed and running (`ollama serve`)
- At least one model pulled (`ollama pull llama3.2`)

### Steps
1. Verify Ollama is running:
   ```bash
   curl http://localhost:11434/api/tags
   ```
2. Set in `.env`:
   ```
   DECEPTICON_MODEL_PROFILE=custom
   DECEPTICON_MODEL=ollama/llama3.2
   OLLAMA_API_BASE=http://host.docker.internal:11434
   ```
3. Start services: `make dev`
4. Test Ollama routing:
   ```bash
   curl -X POST http://localhost:4000/chat/completions \
     -H "Authorization: Bearer sk-decepticon-master" \
     -H "Content-Type: application/json" \
     -d '{"model": "ollama/llama3.2", "messages": [{"role": "user", "content": "Say hello"}]}'
   ```

### Expected
- Response from local Ollama model
- No external API calls made

### Troubleshooting
- Connection refused: Ensure Ollama is running on the configured port
- In Docker: Verify `extra_hosts: ["host.docker.internal:host-gateway"]` in docker-compose.yml
- Set `OLLAMA_API_BASE=http://host.docker.internal:11434` for Docker access


## Scenario 5: Onboard Wizard Complete Flow

### Steps
1. Run: `decepticon onboard`
2. Step through all wizard steps:
   - Select a provider (e.g., Anthropic, OpenRouter, custom gateway, or Ollama)
   - Choose API-key auth or the existing local Claude handler
   - Enter API keys/base URLs as needed
   - Enter a model ID for non-Anthropic providers
   - Select model profile (`eco`/`max`/`test`/`custom`)
   - Confirm `.env` generation
3. Verify output:
   ```bash
   cat ~/.decepticon/.env
   ```

### Expected
- Interactive wizard completes all setup steps
- `.env` file written to `~/.decepticon/.env`


## Scenario 6: Fallback Chain Activation

### Steps
1. Set a primary and fallback model in `.env`:
   ```bash
   DECEPTICON_MODEL_PROFILE=custom
   DECEPTICON_MODEL=openrouter/provider-that-will-fail
   DECEPTICON_MODEL_FALLBACK=openai/gpt-4.1
   OPENAI_API_KEY=sk-...
   ```
2. Start services.
3. Make a request through Decepticon that uses the configured role.
4. Verify fallback activates to the API-key model.

### Expected
- Primary fails, fallback succeeds
- Logs show retry/fallback behavior without printing API keys

### Troubleshooting
- If fallback doesn't activate: Check `router_settings.num_retries` in `config/litellm.yaml` and the model assignment in `DECEPTICON_MODEL*` variables


## Scenario 7: Authorized OAuth / Subscription Use

Decepticon does not require consumer subscription/OAuth tokens for custom model routing. For production, prefer official provider APIs, organization-approved OAuth integrations, or your own OpenAI-compatible gateway. Do not configure tokens in ways that bypass provider entitlements or terms.


## Security Verification

After all scenarios, verify no tokens leak into logs:

```bash
# Should return zero matches (except test fixtures)
grep -r "sk-ant-oat01" decepticon/ --include="*.py" | grep -v test | grep -v fixture
docker compose logs litellm 2>&1 | grep -c "sk-ant-oat01"  # Should be 0
```
