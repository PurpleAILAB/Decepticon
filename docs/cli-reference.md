# CLI Reference

## Commands

| Command | Description |
|---------|-------------|
| `decepticon` | Start all services, open the terminal UI, and print the web dashboard URL |
| `decepticon onboard` | Interactive setup wizard (provider, API key, model profile, LangSmith) |
| `decepticon onboard --reset` | Reconfigure even if `.env` already exists |
| `decepticon demo` | Run guided demo (Metasploitable 2, full kill chain + Sliver C2) |
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
| `GOOGLE_API_KEY` | Google Gemini API key (fallback) |
| `MINIMAX_API_KEY` | MiniMax API key (fallback) |

### Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DECEPTICON_MODEL_PROFILE` | `eco` | Model profile: `eco`, `max`, or `test` |
| `DECEPTICON_MODEL_PROVIDER` | `api` | Auth method: `api` (API keys) or `auth` (OAuth) |

See [Models](models.md) for full profile details.

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
