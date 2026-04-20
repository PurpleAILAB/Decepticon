# Decepticon — Development & Operations
#
# Dev workflow:    make dev   (build + hot-reload via docker compose watch)
# Production:     make start (build + start, same as open-source user experience)
# Interactive CLI: make cli   (in a separate terminal)
#
# Both dev and prod run identical Docker containers.
# The only difference: `watch` syncs local source changes into containers.

COMPOSE     := docker compose
COMPOSE_CLI := $(COMPOSE) --profile cli

# Ensure DECEPTICON_HOME is always set so Docker Compose bind mounts resolve
# correctly. Docker Compose cannot expand ~ in default values, so we must
# expand it here via Make's $(HOME) before passing it to the compose process.
export DECEPTICON_HOME ?= $(HOME)/.decepticon

.PHONY: dev start cli cli-dev web web-dev web-db-ensure web-build web-lint web-migrate web-ee web-oss \
        stop status logs health smoke build \
        test test-local lint lint-fix quality-cli quality \
        clean demo victims help

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
	$(COMPOSE) --profile cli --profile victims --profile c2-sliver down

## Show service status
status:
	$(COMPOSE) ps

## Run all health checks (KG backend + Neo4j + Web dashboard)
health:
	@$(COMPOSE) exec langgraph python -m decepticon.tools.research.health >/dev/null 2>&1 \
		&& echo "kg:    OK" || (echo "kg:    FAIL" && exit 1)
	@$(COMPOSE) exec -T neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-decepticon-graph}" "RETURN 1 AS ok;" >/dev/null 2>&1 \
		&& echo "neo4j: OK" || (echo "neo4j: FAIL" && exit 1)
	@curl -sf http://localhost:$${WEB_PORT:-3000} >/dev/null 2>&1 \
		&& echo "web:   OK (http://localhost:$${WEB_PORT:-3000})" \
		|| (echo "web:   FAIL — not reachable on port $${WEB_PORT:-3000}" && exit 1)

## Follow service logs (usage: make logs or make logs SVC=langgraph)
logs:
	$(COMPOSE) logs -f $(or $(SVC),langgraph)

# ── Build ────────────────────────────────────────────────────────

## Build all Docker images without starting
build:
	$(COMPOSE) --profile cli build

# ── Testing & Quality ────────────────────────────────────────────

## Run pytest inside langgraph container
test:
	$(COMPOSE) exec langgraph python -m pytest $(ARGS)

## Run tests locally (requires uv sync --dev)
test-local:
	uv run pytest $(ARGS)

## Lint and typecheck Python locally
lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run basedpyright

## Auto-fix Python lint issues
lint-fix:
	uv run ruff check --fix .
	uv run ruff format .

# Internal: ensure root node_modules exist (idempotent)
node-install:
	@test -d node_modules || npm install

## CLI quality gates: typecheck + build + test (mirrors CI)
quality-cli: node-install
	npm run typecheck --workspace=@decepticon/cli
	npm run build --workspace=@decepticon/cli
	npm run test --workspace=@decepticon/cli

## Run every quality gate locally — Python + CLI + Web. Run before opening a PR.
quality: lint test-local quality-cli web-lint web-build
	@echo ""
	@echo "OK — all quality gates passed (python + cli + web)"

# ── Web Dashboard ───────────────────────────────────────────────

## Start web dashboard (Docker, includes PostgreSQL + Neo4j)
web:
	$(COMPOSE) up -d --build web

## Start web dashboard in dev mode (Next.js + terminal WebSocket server)
## Automatically starts infra services (postgres, neo4j, etc.) if not running.
web-dev: web-infra web-db-ensure
	@echo "[web-dev] Starting terminal server (ws://localhost:3003)..."
	@cd clients/web && npx tsx server/terminal-server.ts &
	@echo "[web-dev] Starting Next.js dev server (http://localhost:3000)..."
	cd clients/web && npm run dev

# Internal: start infra services needed by web (skip web container itself)
web-infra:
	@echo "[web-infra] Ensuring backend services are running..."
	@$(COMPOSE) up -d postgres neo4j litellm langgraph sandbox

# Internal: ensure decepticon_web DB exists and migrations are applied
web-db-ensure:
	@echo "[web-db-ensure] Waiting for PostgreSQL..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		docker exec decepticon-postgres pg_isready -U decepticon -q 2>/dev/null && break; \
		sleep 1; \
	done
	@docker exec decepticon-postgres psql -U decepticon -d postgres -tAc \
		"SELECT 1 FROM pg_database WHERE datname='decepticon_web'" 2>/dev/null | grep -q 1 \
		|| docker exec decepticon-postgres psql -U decepticon -d postgres -c "CREATE DATABASE decepticon_web;" >/dev/null
	@cd clients/web && npx prisma migrate deploy 2>&1 | tail -1

# Internal: ensure web node_modules exist (idempotent)
web-install:
	@test -d clients/web/node_modules || npm install --prefix clients/web

## Build web dashboard (generates Prisma client first)
web-build: web-install
	cd clients/web && npx prisma generate && npm run build

## Lint web dashboard
web-lint: web-install
	cd clients/web && npx eslint src/ --max-warnings 0

## Run Prisma migration (usage: make web-migrate or make web-migrate NAME=add_fields)
web-migrate: web-install
	cd clients/web && npx prisma migrate dev --name $(or $(NAME),init)

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

# ── OSS Smoke Test ──────────────────────────────────────────────

## End-to-end OSS user simulation: clean slate → build → start → health checks.
## Replicates exactly what an open-source user experiences on first run.
smoke:
	@echo "=== Decepticon OSS smoke test ==="
	@echo ""
	@echo "[1/4] Clean state (removing all containers + volumes)..."
	@$(COMPOSE) --profile cli --profile victims --profile c2-sliver down --volumes --remove-orphans 2>/dev/null; true
	@echo ""
	@echo "[2/4] Building and starting all services (docker compose up -d --build)..."
	$(COMPOSE) up -d --build
	@echo ""
	@echo "[3/4] Waiting for services to become healthy..."
	@echo -n "  LangGraph: "
	@until curl -sf http://localhost:$${LANGGRAPH_PORT:-2024}/ok >/dev/null 2>&1; do printf '.'; sleep 3; done && echo " OK"
	@echo -n "  Neo4j:     "
	@until $(COMPOSE) exec -T neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-decepticon-graph}" "RETURN 1 AS ok;" >/dev/null 2>&1; do printf '.'; sleep 3; done && echo " OK"
	@echo -n "  Web:       "
	@until curl -sf http://localhost:$${WEB_PORT:-3000} >/dev/null 2>&1; do printf '.'; sleep 3; done && echo " OK"
	@echo ""
	@echo "[4/4] Running health checks..."
	@$(MAKE) health
	@echo ""
	@echo "=== Smoke test PASSED — stack is healthy ==="
	@echo ""
	@echo "  Web dashboard:  http://localhost:$${WEB_PORT:-3000}"
	@echo "  LangGraph API:  http://localhost:$${LANGGRAPH_PORT:-2024}"
	@echo "  Run CLI:        make cli"
	@echo ""
	@echo "To tear down: make clean"

# ── Victim Targets (demo/testing) ───────────────────────────────

## Start vulnerable test targets (DVWA + Metasploitable 2)
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
	$(COMPOSE) --profile cli --profile victims --profile c2-sliver down --volumes --remove-orphans

# ── Help ─────────────────────────────────────────────────────────

## Show this help
help:
	@echo "Decepticon — Development & Operations"
	@echo ""
	@echo "Development:"
	@echo "  make dev          Build + start with hot-reload (docker compose watch)"
	@echo "  make cli          Run interactive CLI in Docker"
	@echo "  make cli-dev      Run interactive CLI locally (hot-reload)"
	@echo ""
	@echo "Production:"
	@echo "  make start        Build + start all services"
	@echo "  make stop         Stop all services"
	@echo "  make status       Show service status"
	@echo "  make health       Run all health checks (KG + Neo4j + Web)"
	@echo "  make logs         Follow logs (SVC=langgraph)"
	@echo ""
	@echo "OSS Release Testing:"
	@echo "  make smoke        Full OSS user simulation (clean → build → health checks)"
	@echo ""
	@echo "Quality:"
	@echo "  make quality      Run all quality gates (Python + CLI + Web) — run before PR"
	@echo "  make test         Run pytest in container"
	@echo "  make test-local   Run pytest locally"
	@echo "  make lint         Python lint + typecheck"
	@echo "  make lint-fix     Auto-fix Python lint"
	@echo "  make quality-cli  CLI typecheck + build + test"
	@echo "  make web-lint     Web ESLint"
	@echo "  make web-build    Build web dashboard"
	@echo ""
	@echo "Web Dashboard:"
	@echo "  make web          Start web (Docker)"
	@echo "  make web-dev      Local Next.js dev server"
	@echo "  make web-migrate  Run Prisma migration (NAME=migration_name)"
	@echo "  make web-ee       Link EE package (SaaS mode)"
	@echo "  make web-oss      Unlink EE package (OSS mode)"
	@echo ""
	@echo "Other:"
	@echo "  make build        Build all Docker images"
	@echo "  make victims      Start vulnerable targets (DVWA + Metasploitable 2)"
	@echo "  make demo         Run guided demo"
	@echo "  make clean        Stop + remove volumes"
