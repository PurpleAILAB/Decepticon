# Web Dashboard

The web dashboard is an open-source (Apache 2.0) browser-based control plane for managing engagements. It runs alongside the terminal CLI — use whichever interface fits your workflow.

**Stack**: Next.js 16 · React 19 · PostgreSQL (Prisma) · Neo4j · React Flow · Tailwind CSS v4

---

## Running the Dashboard

**End users:**
```bash
decepticon
```
The dashboard is part of the default service stack. Open <http://localhost:3000>.

**Contributors (full stack with hot-reload):**
```bash
make dev
```
Builds and starts every service with source-sync hot-reload. Open <http://localhost:3000>.

**Contributors (local Next.js dev server):**
```bash
make web-dev
```
Runs the Next.js dev server locally on the host while infra (postgres, neo4j, litellm, langgraph, sandbox) stays in Docker. Faster web iteration than `make dev`.

---

## Features

### Engagement Setup

Create a new engagement by providing a target. Five input types:

| Type | Example |
|------|---------|
| IP range | `10.0.0.0/24` |
| Web URL | `https://app.example.com` |
| Git repository | `https://github.com/org/repo` |
| File upload | Binary, archive, or source tree |
| Local path | `/path/to/target` |

### Soundwave Interview

After creating an engagement, Soundwave interviews you to define the threat actor profile, scope, exclusions, and testing window. The interview streams in real time in the browser. When complete, Soundwave generates the full engagement document package (RoE, ConOps, Deconfliction Plan, OPPLAN).

### Execution Streaming

Once an engagement is running, the dashboard streams all agent events via Server-Sent Events (SSE) from LangGraph. You see tool calls, agent outputs, and objective status updates as they happen.

### Findings Viewer

Parses `FIND-NNN.md` reports from `workspace/findings/` and presents them in a structured view:
- Severity filter (CRITICAL / HIGH / MEDIUM / LOW / INFO)
- Per-finding detail: description, evidence, CVSS, CWE, MITRE technique
- Remediation recommendation

### Attack Graph Canvas

Interactive visualization of the Neo4j knowledge graph:
- Pan and zoom
- Click any node for full property detail
- Color-coded by node type (Host, Service, Vulnerability, Credential)
- Live — updates as the agent adds nodes and edges

Powered by [React Flow](https://reactflow.dev/) with Three.js for 3D rendering.

### OPPLAN Tracker

Per-objective progress board:
- Status badges: `pending` / `in-progress` / `completed` / `blocked` / `cancelled`
- MITRE ATT&CK technique IDs per objective
- OPSEC level indicator
- Dependency graph (which objectives must complete before this one starts)

---

## OSS vs EE Mode

| Feature | OSS | EE |
|---------|-----|----|
| Authentication | None (single local user) | Multi-user + RBAC |
| Engagement management | Single engagement | Multiple concurrent engagements |
| User management | — | User roles and permissions |
| Audit logging | — | Full audit trail |

**OSS mode** (default): No login required. All data belongs to a single `local` user. Suitable for individual operators and self-hosted deployments.

**EE mode** (Enterprise Edition): Links the private `@decepticon/ee` package. Requires a separate license.

```bash
make web-ee    # Switch to EE mode (links @decepticon/ee)
make web-oss   # Switch back to OSS mode
make dev       # Restart after switching
```

---

## Database

The dashboard uses PostgreSQL with Prisma ORM.

**Run migrations** (after `git pull` with schema changes):
```bash
make web-migrate
```

**Regenerate Prisma client** (after editing `prisma/schema.prisma`):
```bash
cd clients/web && npx prisma generate
```
Or run `make web-build` to regenerate the client and build the dashboard in one step.

Schema is at `clients/web/prisma/schema.prisma`. Key models: `User`, `Engagement`, `Finding`, `Objective`, `DefenseAction`.

---

## API Routes

The dashboard exposes Next.js App Router API routes under `clients/web/src/app/api/`. These proxy requests to LangGraph and serve as the backend for the React frontend. They are not a public API — the surface area may change between versions.
