# Contributing

Contributions are welcome — whether you're a security researcher, AI engineer, or someone who cares about making defense better through offense.

---

## Development Setup

**Prerequisites**: Docker, Docker Compose v2, and [uv](https://docs.astral.sh/uv/) (for Python tooling locally).

```bash
git clone https://github.com/PurpleAILAB/Decepticon.git
cd Decepticon

# Copy and configure environment
cp .env.example .env
# Edit .env — set at least ANTHROPIC_API_KEY

# Start services with hot-reload
make dev

# Open the interactive CLI (in a separate terminal)
make cli
```

`make dev` uses `docker compose watch` — source changes sync into containers automatically without rebuilding.

---

## Project Structure

```
decepticon/          # Core Python package (LangGraph agents, middleware, tools)
├── agents/          # Agent factory functions (create_*_agent)
├── core/            # Engagement loop, schemas, logging
├── llm/             # Model profiles, LiteLLM configuration
├── middleware/       # Skills, filesystem, OPPLAN, safe command, fallback, etc.
└── tools/           # Bash, research (KG, CVE, chain planning), reporting

skills/              # Skill library (SKILL.md files organized by kill chain phase)

clients/
├── cli/             # TypeScript/Ink terminal UI
├── web/             # Next.js 16 web dashboard
└── shared/          # Shared streaming utilities (@decepticon/streaming)

config/              # LiteLLM proxy config (litellm.yaml)
containers/          # Dockerfile per service
demo/                # Demo engagement fixtures
```

---

## Quality Gates

Before opening a PR, run the quality checks:

```bash
make quality         # Full gate: Python + CLI + Web (run before opening a PR)

make lint            # Python only: ruff check + ruff format --check + basedpyright
make lint-fix        # Auto-fix Python lint and formatting
make quality-cli     # CLI: typecheck + build + vitest
make web-lint        # Web dashboard ESLint

make test            # Python tests in Docker
make test-local      # Python tests locally (requires uv sync --dev)
```

Minimum Python version: **3.13**

---

## Adding an Agent

1. Create `decepticon/agents/{name}.py` with a `create_{name}_agent()` factory function
2. Follow the middleware stack pattern from an existing agent (e.g., `recon.py`)
3. Define the agent's skill sources in the `SkillsMiddleware` configuration
4. Register the agent in the orchestrator's dispatch table
5. Create a skills directory at `skills/{name}/` if the agent needs dedicated skills

---

## Adding a Skill

1. Create a directory: `skills/{category}/{skill-name}/`
2. Write `SKILL.md` following the [skill format](skills.md#skill-format)
3. Add `references/` for content over 100 lines
4. Add `scripts/` for automation the agent should execute
5. Restart — `SkillsMiddleware` discovers skills at agent boot

No registration required. Skills are discovered automatically from the agent's configured source paths.

---

## Testing

Python tests live in `decepticon/tests/`. Run inside Docker for a clean environment:

```bash
make test            # pytest in container
make test-local      # pytest locally (requires: uv sync --dev)
```

CLI tests run via `make quality-cli` (typecheck + build + vitest), or directly:

```bash
npm run test --workspace=@decepticon/cli
```

When adding a new agent or tool, add corresponding tests in `decepticon/tests/`.

---

## Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`: `git checkout -b feat/your-feature`
3. Make changes — keep commits focused and descriptive
4. Run `make quality` and ensure all checks pass
5. Open a Pull Request against `main`
6. In the PR description, include:
   - What changed and why
   - How to test the change
   - Any relevant MITRE ATT&CK technique IDs (for new agent capabilities or skills)

---

## Areas Where Help Is Welcome

| Area | What's needed |
|------|--------------|
| **New skills** | More OSINT, cloud attack, and post-exploitation skill coverage |
| **C2 profiles** | Havoc framework support (`c2-havoc` profile) |
| **Victim targets** | Additional vulnerable targets beyond Metasploitable 2 |
| **Web dashboard** | UX improvements, new views, mobile responsiveness |
| **Documentation** | Tutorials, walkthroughs, translated READMEs |
| **Bug reports** | Open an issue with reproduction steps |

---

## Community

Join the [Discord](https://discord.gg/TZUYsZgrRG) to ask questions, share engagement logs, discuss techniques, or connect with others working on the project.
