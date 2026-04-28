# Decepticon — Development & Pre-release Verification
#
# Every Docker target builds from the local codebase. `make smoke` mirrors the
# OSS launcher start path (compose up -d --no-build --wait) but uses locally-
# built images instead of pulling from GHCR — pre-release verification on
# whatever you have checked out.
#
# Common workflows:
#   make dev          Hot-reload backend (compose watch)
#   make cli          Interactive CLI in Docker (separate terminal)
#   make web-dev      Local Next.js dev server with infra
#   make smoke        Pre-release verify: clean → local build → OSS-style up → health
#   make quality      Full PR gate (Python + CLI + Web)
#   make help         List all targets

COMPOSE       := docker compose
COMPOSE_WATCH := docker compose -f docker-compose.yml -f docker-compose.watch.yml
PROFILES_ALL  := --profile cli --profile victims --profile c2-sliver
WEB_DIR       := clients/web

# docker compose cannot expand ~ inside compose-file defaults, so resolve it
# here before any subprocess inherits the env.
export DECEPTICON_HOME ?= $(HOME)/.decepticon

.PHONY: help dev cli cli-dev web-dev infra \
        smoke clean status logs health \
        test test-local lint lint-fix quality quality-cli \
        web-build web-lint web-migrate web-ee web-oss \
        node-install web-install web-db-ensure \
        victims demo benchmark

# ── Help (default target) ────────────────────────────────────────

help:
	@echo "Decepticon — Development & Pre-release Verification"
	@echo ""
	@echo "Development (local codebase + hot-reload):"
	@echo "  make dev          Build + start with hot-reload (compose watch)"
	@echo "  make cli          Interactive CLI in Docker (forces local build)"
	@echo "  make cli-dev      CLI locally + backend hot-reload"
	@echo "  make web-dev      Web (Next.js) locally + infra hot-reload"
	@echo ""
	@echo "Pre-release verification:"
	@echo "  make smoke        Clean → build local → OSS-style up → health checks"
	@echo ""
	@echo "Quality gates:"
	@echo "  make quality      Full gate (Python + CLI + Web)"
	@echo "  make test         pytest in container"
	@echo "  make test-local   pytest locally (uv sync --dev)"
	@echo "  make lint         Python lint + typecheck"
	@echo "  make lint-fix     Auto-fix Python lint"
	@echo ""
	@echo "Ops:"
	@echo "  make status       docker compose ps"
	@echo "  make logs [SVC=]  Follow logs (default: langgraph)"
	@echo "  make health       KG + Neo4j + Web health checks"
	@echo "  make clean        Stop + remove volumes"
	@echo ""
	@echo "Web dashboard:"
	@echo "  make web-build    Prisma generate + Next build"
	@echo "  make web-lint     ESLint"
	@echo "  make web-migrate [NAME=]   Prisma migrate dev"
	@echo "  make web-ee / web-oss      Toggle EE/OSS mode"
	@echo ""
	@echo "Other:"
	@echo "  make victims      Start vulnerable test targets (DVWA + MSF2)"
	@echo "  make demo         Guided demo on Metasploitable 2"
	@echo "  make benchmark [ARGS=\"--level 1\"]"

# ── Development (local codebase + hot-reload) ─────────────────────

## Build images and start with hot-reload (source changes auto-sync)
dev:
	$(COMPOSE_WATCH) watch

## Interactive CLI in Docker; --build forces a local rebuild before run
## so the cli image always reflects the current checkout.
cli:
	$(COMPOSE) --profile cli run --rm --build cli

## CLI locally (Node) — backend stays in Docker with hot-reload sync.
cli-dev: infra
	@$(COMPOSE_WATCH) watch --no-up --quiet langgraph &
	cd clients/cli && DECEPTICON_API_URL=$${DECEPTICON_API_URL:-http://localhost:2024} npm run dev

## Next.js dev server locally — infra stays in Docker with hot-reload.
web-dev: infra web-db-ensure
	@$(COMPOSE_WATCH) watch --no-up --quiet langgraph &
	@echo "[web-dev] Starting terminal server (ws://localhost:3003)..."
	@cd $(WEB_DIR) && npx tsx server/terminal-server.ts &
	@echo "[web-dev] Starting Next.js dev server (http://localhost:3000)..."
	cd $(WEB_DIR) && npm run dev

# Internal: bring up backend infra (built from local code).
infra:
	@echo "[infra] Ensuring backend services are running..."
	@$(COMPOSE) up -d --build postgres neo4j litellm langgraph sandbox

# ── Pre-release Verification (mirrors OSS launcher flow) ──────────

## Replicates the OSS user start path while using LOCAL code:
##   1. Down + purge volumes (parity with `decepticon remove`)
##   2. Build all images from local code (replaces `compose pull` from GHCR)
##   3. up -d --no-build --wait --wait-timeout  (identical to launcher Up)
##   4. Health checks (identical to `decepticon health`)
smoke:
	@echo "=== Decepticon pre-release smoke (local build, OSS launcher flow) ==="
	@echo ""
	@echo "[1/4] Clean state (purging containers + volumes)..."
	@$(COMPOSE) $(PROFILES_ALL) down --volumes --remove-orphans 2>/dev/null; true
	@echo ""
	@echo "[2/4] Building images from local code..."
	$(COMPOSE) --profile cli build
	@echo ""
	@echo "[3/4] Starting services (--no-build --wait, OSS launcher flow)..."
	$(COMPOSE) --profile cli up -d --no-build --wait \
		--wait-timeout $${DECEPTICON_STARTUP_TIMEOUT_SECONDS:-600}
	@echo ""
	@echo "[4/4] Health checks..."
	@$(MAKE) -s health
	@echo ""
	@echo "=== smoke OK — stack mirrors OSS user state ==="
	@echo "  Web:       http://localhost:$${WEB_PORT:-3000}"
	@echo "  LangGraph: http://localhost:$${LANGGRAPH_PORT:-2024}"
	@echo "  Run CLI:   make cli"
	@echo "  Teardown:  make clean"

## Stop services and remove volumes (parity with `decepticon remove`).
clean:
	$(COMPOSE) $(PROFILES_ALL) down --volumes --remove-orphans

# ── Status / Logs / Health ───────────────────────────────────────

status:
	$(COMPOSE) ps

## Follow logs (usage: make logs or make logs SVC=langgraph)
logs:
	$(COMPOSE) logs -f $(or $(SVC),langgraph)

## Health checks: KG backend + Neo4j + Web (parity with `decepticon health`).
health:
	@$(COMPOSE) exec -T langgraph python -m decepticon.tools.research.health >/dev/null 2>&1 \
		&& echo "kg:    OK" || (echo "kg:    FAIL" && exit 1)
	@$(COMPOSE) exec -T neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-decepticon-graph}" "RETURN 1 AS ok;" >/dev/null 2>&1 \
		&& echo "neo4j: OK" || (echo "neo4j: FAIL" && exit 1)
	@curl -sf http://localhost:$${WEB_PORT:-3000} >/dev/null 2>&1 \
		&& echo "web:   OK (http://localhost:$${WEB_PORT:-3000})" \
		|| (echo "web:   FAIL — not reachable on port $${WEB_PORT:-3000}" && exit 1)

# ── Tests / Lint ─────────────────────────────────────────────────

test:
	$(COMPOSE) exec langgraph python -m pytest $(ARGS)

test-local:
	uv run pytest $(ARGS)

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run basedpyright

lint-fix:
	uv run ruff check --fix .
	uv run ruff format .

quality-cli: node-install
	npm run typecheck --workspace=@decepticon/cli
	npm run build --workspace=@decepticon/cli
	npm run test --workspace=@decepticon/cli

## Full PR gate — Python + CLI + Web. Run before opening a PR.
quality: lint test-local quality-cli web-lint web-build
	@echo ""
	@echo "OK — all quality gates passed (python + cli + web)"

# ── Web Dashboard ────────────────────────────────────────────────

web-build: web-install
	cd $(WEB_DIR) && npx prisma generate && npm run build

web-lint: web-install
	cd $(WEB_DIR) && npx eslint src/ --max-warnings 0

web-migrate: web-install
	cd $(WEB_DIR) && npx prisma migrate dev --name $(or $(NAME),init)

## Link EE package for SaaS development.
web-ee:
	cd clients/ee && npm link
	cd $(WEB_DIR) && npm link @decepticon/ee
	@grep -q 'NEXT_PUBLIC_DECEPTICON_EDITION' $(WEB_DIR)/.env 2>/dev/null \
		&& sed -i 's/NEXT_PUBLIC_DECEPTICON_EDITION=.*/NEXT_PUBLIC_DECEPTICON_EDITION=ee/' $(WEB_DIR)/.env \
		|| echo 'NEXT_PUBLIC_DECEPTICON_EDITION=ee' >> $(WEB_DIR)/.env
	@echo "EE linked — restart web-dev for SaaS mode"

## Unlink EE package (switch to OSS mode).
web-oss:
	cd $(WEB_DIR) && npm unlink @decepticon/ee 2>/dev/null; true
	@sed -i '/NEXT_PUBLIC_DECEPTICON_EDITION/d' $(WEB_DIR)/.env 2>/dev/null; true
	@echo "EE unlinked — restart web-dev for OSS mode"

# ── Internal idempotent helpers ──────────────────────────────────

node-install:
	@test -d node_modules || npm install

web-install:
	@test -d $(WEB_DIR)/node_modules || npm install --prefix $(WEB_DIR)

# postgres-init/01-create-web-db.sql auto-creates decepticon_web on fresh
# volumes. This target only waits for postgres readiness and applies
# Prisma migrations.
web-db-ensure:
	@echo "[web-db-ensure] Waiting for PostgreSQL..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		docker exec decepticon-postgres pg_isready -U decepticon -q 2>/dev/null && break; \
		sleep 1; \
	done
	@cd $(WEB_DIR) && npx prisma migrate deploy 2>&1 | tail -1

# ── Demo / Targets / Benchmark ───────────────────────────────────

## Start vulnerable test targets (DVWA + Metasploitable 2)
victims:
	$(COMPOSE) --profile victims up -d

## Guided demo on Metasploitable 2 — forces local CLI build.
demo: victims
	@echo "Waiting for langgraph..."
	@until curl -sf http://localhost:$${LANGGRAPH_PORT:-2024}/ok >/dev/null 2>&1; do sleep 2; done
	$(COMPOSE) --profile cli run --rm --build \
		-e DECEPTICON_INITIAL_MESSAGE="Resume the demo engagement and execute all objectives." \
		cli

## Run benchmark suite (usage: make benchmark ARGS="--level 1")
benchmark:
	uv run python -m benchmark.runner $(ARGS)
