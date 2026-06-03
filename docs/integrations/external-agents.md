# External agents — OpenClaw & Hermes

Decepticon ships an **engagement MCP server** so external agent runtimes can
drive it as a tool: discover graphs, launch an authorized engagement, monitor
it, and pull findings. This is what makes Decepticon usable from
[OpenClaw](https://github.com/openclaw/openclaw) and
[Hermes](https://github.com/NousResearch/hermes-agent) — including from a phone,
via those agents' chat channels.

The MCP server is a thin control plane. The red-team work runs inside the
Decepticon LangGraph server (full RoE enforcement, sandbox, knowledge-graph
persistence); the MCP layer only translates tool calls into LangGraph runs
(`decepticon.mcp_server`) and reads persisted findings back as SARIF.

```
OpenClaw / Hermes  ──MCP──▶  decepticon-mcp  ──LangGraph SDK──▶  Decepticon server
   (chat / phone)              (bridge)         (HTTP :2024)        (16 agents, RoE, KG)
```

## 1. Install + run

```bash
# Install Decepticon with the MCP server extra
pip install 'decepticon[mcp]'        # or: uv sync --extra mcp

# Start the Decepticon LangGraph server (one of):
langgraph dev                        # dev server on http://localhost:2024
# or the Docker stack — see docs/deployment

# Smoke-test the bridge over stdio (Ctrl-C to exit):
decepticon-mcp --transport stdio
```

The bridge connects to `DECEPTICON_API_URL` (default `http://localhost:2024`).
Override with `--langgraph-url` or the env var.

## 2. OpenClaw

Register the MCP server, then install the bundled skill:

```bash
# Register the engagement MCP server (stdio)
openclaw mcp set decepticon '{
  "command": "decepticon-mcp",
  "args": ["--transport", "stdio"],
  "env": { "DECEPTICON_API_URL": "http://localhost:2024" }
}'

# Install the agent skill (clone the repo first, then point at the skill dir)
openclaw skills install ./Decepticon/integrations/agent-skills/decepticon --as decepticon --global
openclaw gateway restart
```

Now message your OpenClaw agent (from the dashboard or any connected channel,
e.g. Telegram for phone): *"Run a Decepticon recon engagement against
`https://test.example.com`, scope only that host."* The agent will call
`decepticon_start_engagement`, poll status, and report findings.

## 3. Hermes

Add the MCP server to `~/.hermes/config.yaml` and drop the skill into Hermes's
skills directory:

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  decepticon:
    command: decepticon-mcp
    args: ["--transport", "stdio"]
    env:
      DECEPTICON_API_URL: "http://localhost:2024"
```

```bash
# Install the skill for Hermes (copy the skill folder into Hermes' skills dir)
cp -r ./Decepticon/integrations/agent-skills/decepticon ~/.hermes/skills/decepticon
```

Restart Hermes; the `decepticon` skill and `decepticon_*` tools become
available to the agent.

## 4. Remote / networked use (optional)

For a networked deployment (agent host separate from the Decepticon host), run
the bridge over HTTP instead of stdio:

```bash
decepticon-mcp --transport streamable-http --host 0.0.0.0 --port 8765 \
  --langgraph-url http://decepticon-host:2024
```

Point the agent's MCP client at `http://<bridge-host>:8765/mcp`. Restrict
exposure to a trusted network — the bridge can launch authorized engagements.

## Tools exposed

| Tool | Purpose |
|------|---------|
| `decepticon_list_graphs` | Discover engagement graphs (decepticon, recon, soundwave, …) |
| `decepticon_start_engagement` | Launch a background engagement (targets + scope/RoE) |
| `decepticon_engagement_status` | Poll run status + findings availability |
| `decepticon_engagement_findings` | Fetch findings summary / full SARIF |
| `decepticon_cancel_engagement` | Cancel a running engagement |

## Authorization

Engagements run under Decepticon's Rules-of-Engagement enforcement. The calling
agent **must** pass scope (in / out of scope) in the `instruction` argument and
only target assets the operator is authorized to test. See the bundled
`integrations/agent-skills/decepticon/SKILL.md` for the agent-facing contract.
