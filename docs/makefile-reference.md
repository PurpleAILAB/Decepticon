# Makefile Reference

Run `make help` for a quick summary. Full reference below.

---

## Development

| Target | Description |
|--------|-------------|
| `make dev` | Build all Docker images and start with hot-reload (`docker compose watch`) — source changes sync into containers automatically |
| `make cli` | Open the interactive terminal UI inside Docker (production-like) |
| `make cli-dev` | Open the interactive terminal UI locally with hot-reload (requires running services) |

Typical contributor workflow:

```bash
# Terminal 1 — start services with hot-reload
make dev

# Terminal 2 — open the interactive CLI
make cli
```

---

## Production / Operations

| Target | Description |
|--------|-------------|
| `make start` | Build + start all services in the background (same experience as `decepticon` for end users) |
| `make stop` | Stop all services |
| `make status` | Show running service status |
| `make logs [SVC=service]` | Follow logs (default: `langgraph`). Override: `make logs SVC=litellm` |

---

## Build & Quality

| Target | Description |
|--------|-------------|
| `make build` | Build all Docker images |
| `make lint` | Python lint + type-check (`ruff check` + `basedpyright`) |
| `make lint-fix` | Auto-fix Python lint issues |
| `make lint-cli` | TypeScript CLI type-check |
| `make build-cli` | Build the CLI workspace (TypeScript compile) |
| `make quality` | Run all quality gates: Python lint + CLI typecheck + web lint |

---

## Testing

| Target | Description |
|--------|-------------|
| `make test` | Run Python tests (`pytest`) inside the Docker container |
| `make test-local` | Run Python tests locally (requires `uv sync --dev`) |
| `make test-cli` | Run CLI tests (`vitest`) |

---

## Web Dashboard

| Target | Description |
|--------|-------------|
| `make web` | Start the full web stack in Docker (includes PostgreSQL + Neo4j) |
| `make web-dev` | Start the Next.js dev server locally (requires running database) |
| `make web-build` | Build the web dashboard (also generates the Prisma client) |
| `make web-lint` | Lint the web dashboard (ESLint) |
| `make web-migrate` | Run Prisma database migrations |
| `make web-generate` | Regenerate the Prisma client (after schema changes) |
| `make web-ee` | Link the Enterprise Edition package (`@decepticon/ee`) |
| `make web-oss` | Unlink the EE package — revert to OSS mode |

---

## Testing Targets & Demo

| Target | Description |
|--------|-------------|
| `make victims` | Start vulnerable test targets (DVWA, Metasploitable 2) for practice engagements |
| `make demo` | Run the guided demo against Metasploitable 2 (full kill chain + Sliver C2) |

---

## Cleanup

| Target | Description |
|--------|-------------|
| `make clean` | Stop all services **and remove all volumes** (PostgreSQL data, Neo4j graph, workspace files). Resets everything. |
