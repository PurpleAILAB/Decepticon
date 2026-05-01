# CLI Reference

## Commands

| Command | Description |
|---------|-------------|
| `decepticon` | Start all services, open the terminal UI, and print the web dashboard URL |
| `decepticon onboard` | Interactive setup wizard (provider, API key, model profile, LangSmith) |
| `decepticon onboard --reset` | Reconfigure even if `.env` already exists |
| `decepticon stop` | Stop all services |
| `decepticon status` | Show service status |
| `decepticon logs [service]` | Follow service logs (default: `langgraph`) |
| `decepticon kg-health` | Diagnose the Neo4j knowledge graph |
| `decepticon update` | Check for updates and apply them |
| `decepticon remove` | Uninstall Decepticon completely |
| `decepticon --version` | Show installed version |

> **Web dashboard** is included in the default stack. After `decepticon` starts, the dashboard is available at `http://localhost:3000` (configurable via `WEB_PORT` in `.env`).

### `decepticon logs` — Service names

```bash
decepticon logs             # langgraph (default)
decepticon logs litellm     # LiteLLM proxy
decepticon logs postgres    # PostgreSQL
decepticon logs neo4j       # Neo4j graph database
decepticon logs sandbox     # Kali Linux sandbox
decepticon logs web         # Web dashboard
```

---

## Interactive Terminal UI

The interactive CLI is built with React 19 + [Ink](https://github.com/vadimdemedes/ink). It streams events from LangGraph in real time.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+O` | Toggle Prompt ↔ Transcript mode |
| `Ctrl+G` | Cycle graph sidebar: Overview → Nodes → Flows |
| `Ctrl+B` | Toggle graph sidebar visibility |
| `Ctrl+C` | Cancel active stream / exit transcript / exit app |
| `Esc` | Exit transcript mode |

### View Modes

**Prompt Mode** (default)
- Compact view suitable for monitoring
- Sub-agent sessions collapsed
- Consecutive tool calls from the same agent are grouped
- Shows current objective and streaming agent output

**Transcript Mode** (`Ctrl+O`)
- Full event history
- Complete tool inputs and outputs
- All sub-agent details expanded
- Useful for debugging and reviewing what the agent actually did

### Graph Sidebar

The right-side panel visualizes the live Neo4j attack graph:

| View | Content |
|------|---------|
| **Overview** | High-level graph summary (node/edge counts, top hosts) |
| **Nodes** | Individual node list with type and properties |
| **Flows** | Attack chain paths discovered so far |

Cycle with `Ctrl+G`, hide/show with `Ctrl+B`. A Web Canvas auto-starts for pan/zoom interaction.

### Slash Commands

Available inside the interactive terminal UI:

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/?` | Show available commands and keyboard shortcuts |
| `/clear` | | Clear conversation history |
| `/resume [message]` | `/r` | Resume a paused run or continue previous session |
| `/quit` | | Exit the CLI |

---

## Environment Variables

These can be set in your `.env` file (configure with `decepticon onboard`) or as shell environment variables.

### Required (at least one LLM key)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `OPENAI_API_KEY` | OpenAI API key (fallback) |
| `GEMINI_API_KEY` | Google Gemini API key (fallback) |
| `MINIMAX_API_KEY` | MiniMax API key (fallback) |

### Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DECEPTICON_MODEL_PROFILE` | `eco` | Tier preset: `eco` (per-agent), `max` (all HIGH), or `test` (all LOW) |
| `DECEPTICON_AUTH_PRIORITY` | `anthropic_oauth,anthropic_api,openai_oauth,openai_api,google_api,minimax_api,deepseek_api,xai_api,mistral_api,openrouter_api,nvidia_api,ollama_local` | Comma-separated AuthMethod priority — first method primary, rest are fallbacks. Methods whose credential isn't configured are skipped at runtime. |
| `DECEPTICON_AUTH_CLAUDE_CODE` | `false` | Set `true` to route Anthropic models via Claude Code OAuth (`auth/claude-*` in LiteLLM) |
| `DECEPTICON_AUTH_CHATGPT` | `false` | Set `true` to route OpenAI models via ChatGPT subscription OAuth (`auth/gpt-*`) |
| `DECEPTICON_AUTH_GEMINI` | `false` | Set `true` to route Google models via Gemini Advanced OAuth (`gemini-sub/*`) |
| `DECEPTICON_AUTH_COPILOT` | `false` | Set `true` for Microsoft Copilot Pro OAuth (`copilot/*`) |
| `DECEPTICON_AUTH_GROK` | `false` | Set `true` for xAI SuperGrok OAuth (`grok-sub/*`) |
| `DECEPTICON_AUTH_PERPLEXITY` | `false` | Set `true` for Perplexity Pro OAuth (`pplx-sub/*`) |
| `OLLAMA_API_BASE` / `OLLAMA_MODEL` | unset | When set, registers `ollama_chat/<OLLAMA_MODEL>` and enables the `ollama_local` AuthMethod |

See [Models](models.md) for the full Tier × AuthMethod matrix and chain examples.

### Infrastructure

| Variable | Default | Description |
|----------|---------|-------------|
| `LITELLM_MASTER_KEY` | `sk-decepticon-master` | LiteLLM proxy auth key |
| `LITELLM_SALT_KEY` | `sk-decepticon-salt-change-me` | LiteLLM salt (change in production) |
| `POSTGRES_PASSWORD` | `decepticon` | PostgreSQL password |
| `NEO4J_PASSWORD` | `decepticon-graph` | Neo4j password |

### Ports (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGGRAPH_PORT` | `2024` | LangGraph API server port |
| `LITELLM_PORT` | `4000` | LiteLLM proxy port |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `WEB_PORT` | `3000` | Web dashboard port |
| `TERMINAL_PORT` | `3003` | Terminal WebSocket bridge for the embedded CLI |

Neo4j ports (`7474` browser, `7687` bolt) are fixed in `docker-compose.yml`.

### C2 Framework

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPOSE_PROFILES` | `c2-sliver` | Active Docker Compose profile |

Currently supported profiles: `c2-sliver`. Future: `c2-havoc`.

### Observability (optional)

| Variable | Description |
|----------|-------------|
| `LANGSMITH_TRACING` | Set to `true` to enable LangSmith tracing |
| `LANGSMITH_API_KEY` | LangSmith API key |
| `LANGSMITH_PROJECT` | LangSmith project name (default: `decepticon`) |

### Debug

| Variable | Description |
|----------|-------------|
| `DECEPTICON_DEBUG` | Set to `true` for verbose debug output |
