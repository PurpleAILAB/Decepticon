# Decepticon — Development & Operations
#
# Dev workflow:    make dev   (build + hot-reload via docker compose watch)
# Production:     make start (build + start, same as open-source user experience)
# Interactive CLI: make cli   (in a separate terminal)
#
# Both dev and prod run identical Docker containers.
# The only difference: `watch` syncs local source changes into containers.

COMPOSE := docker compose
COMPOSE_CLI := $(COMPOSE) --profile cli
COMPOSE_WEB := $(COMPOSE) --profile web

.PHONY: dev start cli cli-dev web web-dev web-db-ensure web-build web-lint web-migrate web-ee web-oss stop status logs kg-health neo4j-health build test test-cli lint lint-cli quality clean

# ── Development ──────────────────────────────────────────────────

## Build images and start with hot-reload (source changes auto-sync)
dev:
	$(COMPOSE) watch

## Run interactive CLI in Docker (prod-like, requires `make dev` for backend)
cli:
	$(COMPOSE_CLI) run --rm cli

## Run interactive CLI locally (dev mode with hot-reload, reflects source changes instantly)
cli-dev:
	DECEPTICON_API_URL=$${DECEPTICON_API_URL:-http://localhost:2024} npm run cli:dev

# ── Production-like ──────────────────────────────────────────────

## Build and start all services in background (same as open-source user)
start:
	$(COMPOSE) up -d --build

## Stop all services
stop:
	$(COMPOSE) --profile cli --profile web --profile victims --profile c2-sliver down

## Show service status
status:
	$(COMPOSE) ps

## Knowledge-graph backend health from the running LangGraph container
kg-health:
	$(COMPOSE) exec langgraph python -m decepticon.research.health

## Direct Neo4j startup check (cypher-shell RETURN 1)
neo4j-health:
	$(COMPOSE) exec neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-decepticon-graph}" "RETURN 1 AS ok;"

## Follow service logs (usage: make logs or make logs SVC=langgraph)
logs:
	$(COMPOSE) logs -f $(or $(SVC),langgraph)

# ── Build ────────────────────────────────────────────────────────

## Build all Docker images without starting
build:
	$(COMPOSE) --profile cli --profile web build

## Build a specific service (usage: make build-svc SVC=langgraph)
build-svc:
	$(COMPOSE) build $(SVC)

# ── Testing & Quality ────────────────────────────────────────────

## Run pytest inside langgraph container
test:
	$(COMPOSE) exec langgraph python -m pytest $(ARGS)

## Run tests locally (requires uv sync --dev)
test-local:
	pytest $(ARGS)

## Lint and typecheck Python locally
lint:
	ruff check .
	ruff format --check .
	basedpyright

## Auto-fix Python lint issues
lint-fix:
	ruff check --fix .
	ruff format .

## CLI (TypeScript) quality gates — mirror the CI workflow so local
## runs catch CLI breakage before push. These three targets are what
## unblocked the HIGH-1 finding: build + typecheck + vitest all exist
## in the CLI workspace but the default `make lint` never ran them.
lint-cli:
	npm run typecheck --workspace=@decepticon/cli

build-cli:
	npm run build --workspace=@decepticon/cli

test-cli:
	npm run test --workspace=@decepticon/cli

## Single command that exercises EVERY quality gate locally —
## Python lint + Python tests + CLI typecheck + CLI build + CLI tests.
## Run this before opening a PR so a CLI-workspace break cannot slip
## through the way it did prior to the HIGH-1 finding.
quality: lint test-local lint-cli build-cli test-cli web-lint web-build
	@echo ""
	@echo "OK — all quality gates passed (python + cli + web)"

# ── Web Dashboard ───────────────────────────────────────────────

## Start web dashboard (Docker, includes PostgreSQL + Neo4j)
web:
	$(COMPOSE_WEB) up -d --build web

## Start web dashboard in dev mode (local Next.js, requires running PostgreSQL)
## Auto-ensures decepticon_web DB exists + applies migrations before starting.
web-dev: web-db-ensure
	cd clients/web && npm run dev

## Ensure decepticon_web DB exists, schema is migrated, and OSS seed user exists.
## Idempotent — safe to run multiple times.
web-db-ensure:
	@docker exec decepticon-postgres psql -U decepticon -d postgres -tAc \
		"SELECT 1 FROM pg_database WHERE datname='decepticon_web'" 2>/dev/null | grep -q 1 \
		|| docker exec decepticon-postgres psql -U decepticon -d postgres -c "CREATE DATABASE decepticon_web;" >/dev/null
	@cd clients/web && npx prisma migrate deploy 2>&1 | tail -1
	@docker exec decepticon-postgres psql -U decepticon -d decepticon_web -tAc \
		"INSERT INTO \"User\" (id, \"updatedAt\") VALUES ('local', NOW()) ON CONFLICT (id) DO NOTHING;" >/dev/null

## Build web dashboard (generates Prisma client first)
web-build: web-generate
	cd clients/web && npm run build

## Lint web dashboard
web-lint:
	cd clients/web && npx eslint src/ --max-warnings 0

## Run Prisma migration for web dashboard (usage: make web-migrate or make web-migrate NAME=add_fields)
web-migrate:
	cd clients/web && npx prisma migrate dev --name $(or $(NAME),init)

## Generate Prisma client
web-generate:
	cd clients/web && npx prisma generate

## Link EE package for SaaS development
web-ee:
	cd clients/ee && npm link
	cd clients/web && npm link @decepticon/ee
	@grep -q 'NEXT_PUBLIC_DECEPTICON_EDITION' clients/web/.env 2>/dev/null \
		&& sed -i 's/NEXT_PUBLIC_DECEPTICON_EDITION=.*/NEXT_PUBLIC_DECEPTICON_EDITION=ee/' clients/web/.env \
		|| echo 'NEXT_PUBLIC_DECEPTICON_EDITION=ee' >> clients/web/.env
	@echo "EE linked — restart web-dev for SaaS mode"

## Unlink EE package (switch to OSS mode)
web-oss:
	cd clients/web && npm unlink @decepticon/ee 2>/dev/null; true
	@sed -i '/NEXT_PUBLIC_DECEPTICON_EDITION/d' clients/web/.env 2>/dev/null; true
	@echo "EE unlinked — restart web-dev for OSS mode"

# ── Victim Targets (demo/testing) ───────────────────────────────

## Start vulnerable test targets
victims:
	$(COMPOSE) --profile victims up -d

## Run guided demo (Metasploitable 2)
demo:
	$(COMPOSE) --profile victims up -d
	@echo "Waiting for services..."
	@until curl -sf http://localhost:$${LANGGRAPH_PORT:-2024}/ok >/dev/null 2>&1; do sleep 2; done
	$(COMPOSE_CLI) run --rm -e DECEPTICON_INITIAL_MESSAGE="Resume the demo engagement and execute all objectives." cli

# ── Cleanup ──────────────────────────────────────────────────────

## Stop services and remove volumes
clean:
	$(COMPOSE) --profile cli --profile web --profile victims down --volumes --remove-orphans

# ── Help ─────────────────────────────────────────────────────────

## Show this help
help:
	@echo "Decepticon — Development & Operations"
	@echo ""
	@echo "Development:"
	@echo "  make dev        Build + start with hot-reload (docker compose watch)"
	@echo "  make cli        Run interactive CLI in Docker (prod-like)"
	@echo "  make cli-dev    Run interactive CLI locally (dev mode, hot-reload)"
	@echo ""
	@echo "Production-like:"
	@echo "  make start      Build + start in background"
	@echo "  make stop       Stop all services"
	@echo "  make status       Show service status"
	@echo "  make kg-health    Graph backend health (from langgraph container)"
	@echo "  make neo4j-health Direct Neo4j startup check (cypher-shell)"
	@echo "  make logs         Follow logs (SVC=langgraph)"
	@echo ""
	@echo "Quality (Python):"
	@echo "  make test        Run pytest in container"
	@echo "  make test-local  Run pytest locally"
	@echo "  make lint        Python lint + typecheck"
	@echo "  make lint-fix    Auto-fix Python lint issues"
	@echo ""
	@echo "Quality (CLI — TypeScript):"
	@echo "  make lint-cli    Typecheck the Ink CLI workspace"
	@echo "  make build-cli   Build the Ink CLI workspace"
	@echo "  make test-cli    Run vitest in the CLI workspace"
	@echo ""
	@echo "Web Dashboard:"
	@echo "  make web          Start web dashboard (Docker, includes PG + Neo4j)"
	@echo "  make web-dev      Local Next.js dev server"
	@echo "  make web-build    Build web dashboard"
	@echo "  make web-lint     Lint web (ESLint)"
	@echo "  make web-migrate  Run Prisma DB migration"
	@echo "  make web-generate Generate Prisma client"
	@echo "  make web-ee       Link EE package (SaaS mode)"
	@echo "  make web-oss      Unlink EE package (OSS mode)"
	@echo ""
	@echo "Combined:"
	@echo "  make quality     Python + CLI — run before every PR"
	@echo ""
	@echo "Other:"
	@echo "  make build      Build all Docker images"
	@echo "  make victims    Start vulnerable targets"
	@echo "  make demo       Run guided demo"
	@echo "  make clean      Stop + remove volumes"
