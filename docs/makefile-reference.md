# Makefile Reference

The Makefile is for **local development and pre-release verification**. Every Docker target builds from your local checkout. End users install via `curl | bash` and run `decepticon` — they don't use `make`.

Run `make help` for a quick summary. Full reference below.

---

## Development

| Target | Description |
|--------|-------------|
| `make dev` | Build all Docker images and start with hot-reload (`docker compose watch`) — source changes sync into containers automatically |
| `make cli` | Open the interactive terminal UI inside Docker (forces a local rebuild before run) |
| `make cli-dev` | Open the interactive terminal UI locally with hot-reload (Node) — backend stays in Docker |
| `make web-dev` | Run the Next.js dev server locally with infra services in Docker |

Typical contributor workflow:

```bash
# Terminal 1 — start services with hot-reload
make dev

# Terminal 2 — open the interactive CLI
make cli
```

The Web dashboard is part of the default Compose stack; after `make dev` it's reachable at <http://localhost:3000>.

---

## Pre-release Verification

| Target | Description |
|--------|-------------|
| `make smoke` | Replicates the OSS user start path on local code: clean → build images from local → `compose up -d --no-build --wait` → health checks. Use this before tagging a release. |

The `up` flags (`--no-build --wait --wait-timeout`) match the launcher's `compose.Up` exactly, so smoke validates the same path an installed `decepticon` user takes — but with whatever code you have checked out instead of GHCR-published images.

---

## Operations

| Target | Description |
|--------|-------------|
| `make status` | Show running service status (`docker compose ps`) |
| `make logs [SVC=service]` | Follow logs (default: `langgraph`). Override: `make logs SVC=litellm` |
| `make health` | KG backend + Neo4j + Web health checks (parity with `decepticon health`) |
| `make clean` | Stop services and remove all volumes (parity with `decepticon remove`) |

---

## Quality Gates

| Target | Description |
|--------|-------------|
| `make quality` | Run all quality gates: Python lint + tests + CLI typecheck/build/test + Web lint/build |
| `make lint` | Python lint + type-check (`ruff check` + `ruff format --check` + `basedpyright`) |
| `make lint-fix` | Auto-fix Python lint and formatting |
| `make quality-cli` | CLI typecheck + build + test (`vitest`) |

---

## Testing

| Target | Description |
|--------|-------------|
| `make test [ARGS=...]` | Run Python tests (`pytest`) inside the Docker container |
| `make test-local [ARGS=...]` | Run Python tests locally (requires `uv sync --dev`) |

CLI tests are part of `make quality-cli`. To run them in isolation: `npm run test --workspace=@decepticon/cli`.

---

## Web Dashboard

| Target | Description |
|--------|-------------|
| `make web-dev` | Start the Next.js dev server locally; brings up infra in Docker |
| `make web-build` | Build the web dashboard (also generates the Prisma client) |
| `make web-lint` | Lint the web dashboard (ESLint) |
| `make web-migrate [NAME=name]` | Run a Prisma dev migration |
| `make web-ee` | Link the Enterprise Edition package (`@decepticon/ee`) |
| `make web-oss` | Unlink the EE package — revert to OSS mode |

To regenerate just the Prisma client (without a full build): `cd clients/web && npx prisma generate`.

---

## Demo Targets

| Target | Description |
|--------|-------------|
| `make victims` | Start vulnerable test targets (DVWA, Metasploitable 2) for practice engagements |
| `make demo` | Run the guided demo against Metasploitable 2 (forces a local CLI rebuild) |
| `make benchmark [ARGS="--level 1"]` | Run the benchmark suite locally |
