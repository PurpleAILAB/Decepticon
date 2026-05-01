# Decepticon — Pre-release Verification & Development
#
# Purpose: dogfood and validate the OSS release flow before tagging. Every
# Docker target builds from the local checkout (never pulls from GHCR), so
# what you test is exactly what ships.
#
# Common workflows:
#   make dogfood      Full OSS UX (launcher → onboard → CLI) on local code
#   make smoke        Compose-only smoke (no launcher) — fast pre-release check
#   make quality      PR gate (Python + CLI + Web)
#   make dev          Backend hot-reload (compose watch) — daily dev loop
#   make help         List all targets

COMPOSE       := docker compose
COMPOSE_WATCH := docker compose -f docker-compose.yml -f docker-compose.watch.yml
PROFILES_ALL  := --profile cli --profile c2-sliver
WEB_DIR       := clients/web

# Dogfood: isolated $DECEPTICON_HOME so the launcher can onboard, write .env,
# and stand up the stack without touching the user's real ~/.decepticon. The
# launcher resolves all relative paths against the compose file's directory,
# so docker-compose.yml + config/ + containers/ + .env.example are symlinked
# back to the repo. workspace/ stays a real directory (engagement bind mount).
DOGFOOD_HOME  := $(CURDIR)/.dogfood
LAUNCHER_BIN  := clients/launcher/bin/decepticon

# docker compose cannot expand ~ inside compose-file defaults, so resolve it
# here before any subprocess inherits the env.
export DECEPTICON_HOME ?= $(HOME)/.decepticon

.PHONY: help \
        dogfood launcher smoke \
        dev cli-dev web-dev infra \
        quality quality-cli test test-local lint lint-fix \
        web-build web-lint web-migrate web-ee web-oss \
        status logs health clean \
        node-install web-db-ensure \
        benchmark

# ── Help (default target) ────────────────────────────────────────

help:
	@echo "Decepticon — Pre-release Verification & Development"
	@echo ""
	@echo "Pre-release verification (release readiness):"
	@echo "  make dogfood      Full OSS UX (launcher → onboard → CLI) on local code"
	@echo "  make smoke        Compose-only smoke (no launcher) — fast OSS-shape check"
	@echo "  make launcher     Build the Go launcher binary ($(LAUNCHER_BIN))"
	@echo ""
	@echo "Development (build the thing being released):"
	@echo "  make dev          Backend hot-reload (compose watch)"
	@echo "  make cli-dev      CLI locally + backend hot-reload"
	@echo "  make web-dev      Web (Next.js) locally + backend hot-reload"
	@echo ""
	@echo "Quality gates (PR readiness):"
	@echo "  make quality      Full gate (Python + CLI + Web)"
	@echo "  make test         pytest in container"
	@echo "  make test-local   pytest locally (uv sync --dev)"
	@echo "  make lint         Python lint + format check + typecheck"
	@echo "  make lint-fix     Auto-fix Python lint + format"
	@echo ""
	@echo "Web dashboard (single checks):"
	@echo "  make web-build    Prisma generate + Next build"
	@echo "  make web-lint     ESLint"
	@echo "  make web-migrate [NAME=]   Prisma migrate dev"
	@echo "  make web-ee / web-oss      Toggle EE/OSS mode (dev-only)"
	@echo ""
	@echo "Ops:"
	@echo "  make status       docker compose ps"
	@echo "  make logs [SVC=]  Follow logs (default: langgraph)"
	@echo "  make health       KG + Neo4j + Web health checks"
	@echo "  make clean        Full teardown (compose volumes + .dogfood/)"
	@echo ""
	@echo "Other:"
	@echo "  make benchmark [ARGS=\"--level 1\"]"

# ── Pre-release Verification (PRIMARY) ───────────────────────────

## End-to-end OSS dogfood: launcher onboard → engagement picker → compose up
## → CLI. Identical UX to a real `curl | bash` install, but every image and
## the launcher itself come from the current checkout (tag :dev). The
## launcher version is "dev" so auto-update + config-sync are skipped — the
## symlinked .dogfood/ tree is the source of truth.
dogfood: launcher
	@mkdir -p $(DOGFOOD_HOME)/workspace
	@ln -sfn $(CURDIR)/docker-compose.yml $(DOGFOOD_HOME)/docker-compose.yml
	@ln -sfn $(CURDIR)/config              $(DOGFOOD_HOME)/config
	@ln -sfn $(CURDIR)/containers          $(DOGFOOD_HOME)/containers
	@ln -sfn $(CURDIR)/.env.example        $(DOGFOOD_HOME)/.env.example
	@echo ""
	@echo "[dogfood] Building images from local code (tag :dev)..."
	DECEPTICON_VERSION=dev $(COMPOSE) --profile cli build
	@echo ""
	@echo "[dogfood] Launching ./$(LAUNCHER_BIN) (DECEPTICON_HOME=$(DOGFOOD_HOME))"
	@echo ""
	DECEPTICON_VERSION=dev DECEPTICON_HOME=$(DOGFOOD_HOME) ./$(LAUNCHER_BIN)

## Build the Go launcher binary (version=dev, gates auto-update + config sync).
launcher:
	cd clients/launcher && go build \
		-ldflags '-X github.com/PurpleAILAB/Decepticon/clients/launcher/cmd.version=dev' \
		-o bin/decepticon

## Compose-only smoke (no launcher, no onboard wizard) — fastest possible
## release-shape check. Replicates only the launcher's compose Up step:
##   1. Down + purge volumes (parity with `decepticon remove`)
##   2. Build all images from local code (replaces `compose pull` from GHCR)
##   3. up -d --no-build --wait --wait-timeout  (identical to launcher Up)
##   4. Health checks (identical to `decepticon health`)
## Use dogfood for the full release flow; use smoke when the compose stack
## is the only thing you've changed.
smoke:
	@echo "=== Decepticon pre-release smoke (compose-only, no launcher) ==="
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
	@echo "  Web:          http://localhost:$${WEB_PORT:-3000}"
	@echo "  LangGraph:    http://localhost:$${LANGGRAPH_PORT:-2024}"
	@echo "  Run dogfood:  make dogfood"
	@echo "  Teardown:     make clean"

# ── Development (build the thing being released) ─────────────────

## Build images and start with hot-reload (source changes auto-sync).
dev:
	$(COMPOSE_WATCH) watch

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

# ── Quality gates ────────────────────────────────────────────────

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

# ── Web Dashboard (single checks) ────────────────────────────────
# All web targets share the root `node-install` so workspace deps hoist
# into the root node_modules — no separate clients/web/node_modules tree.

web-build: node-install
	cd $(WEB_DIR) && npx prisma generate && npm run build

web-lint: node-install
	cd $(WEB_DIR) && npx eslint src/ --max-warnings 0

web-migrate: node-install
	cd $(WEB_DIR) && npx prisma migrate dev --name $(or $(NAME),init)

## Link EE package for SaaS development (dev-only; not part of OSS flow).
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

# ── Status / Logs / Health / Clean ───────────────────────────────

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

## Full teardown: containers + volumes + .dogfood/. Destructive — also
## wipes the dogfood .env (API keys) so the next `make dogfood` starts
## with a fresh onboard wizard.
clean:
	$(COMPOSE) $(PROFILES_ALL) down --volumes --remove-orphans
	@rm -rf $(DOGFOOD_HOME)
	@echo "OK — compose volumes purged, .dogfood/ removed"

# ── Internal idempotent helpers ──────────────────────────────────

node-install:
	@test -d node_modules || npm install

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

# ── Benchmark ────────────────────────────────────────────────────

## Run benchmark suite (usage: make benchmark ARGS="--level 1")
benchmark:
	uv run python -m benchmark.runner $(ARGS)
