# Contributing to Decepticon

Thank you for your interest in contributing to Decepticon! Whether you're a security researcher, AI engineer, or documentation enthusiast, we welcome your contributions.

## Getting Started

### Prerequisites

- Python 3.13+
- Docker & Docker Compose v2
- Node.js 22+ (for CLI client)
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Development Setup

```bash
git clone https://github.com/PurpleAILAB/Decepticon.git
cd Decepticon

# Start with hot-reload (builds Docker images + watches for source changes)
make dev

# In a separate terminal — open the interactive CLI
make cli
```

### Running Tests & Linting

```bash
make test          # Run pytest inside container
make test-local    # Run pytest locally (requires: uv sync --dev)
make lint          # Lint + typecheck locally
make lint-fix      # Auto-fix lint issues
```

## How to Contribute

### Reporting Bugs

Use the [Bug Report](https://github.com/PurpleAILAB/Decepticon/issues/new?template=bug_report.yml) issue template. Include:
- Steps to reproduce
- Expected vs actual behavior
- Docker and Python version info

### Suggesting Features

Use the [Feature Request](https://github.com/PurpleAILAB/Decepticon/issues/new?template=feature_request.yml) issue template.

### Submitting Pull Requests

1. **Fork** the repository and create your branch from `main`.
2. **Write code** following the conventions below.
3. **Test** your changes — ensure `make lint` and `make test-local` pass.
4. **Commit** with clear, descriptive messages using [Conventional Commits](https://www.conventionalcommits.org/) format:
   - `feat(scope):` — new feature
   - `fix(scope):` — bug fix
   - `docs:` — documentation only
   - `chore:` — maintenance
   - `refactor:` — code restructuring
5. **Open a PR** against `main` with a clear description of what and why.

## Code Conventions

- **Python**: Pydantic v2, Ruff for formatting/linting, basedpyright for type checking
- **Line length**: 100 characters
- **Imports**: Absolute imports, public API re-exported through `__init__.py`
- **Logging**: `from decepticon.core.logging import get_logger; log = get_logger("module.sub")`
- **Skills**: Markdown files in `decepticon/skills/` with YAML frontmatter
- **CLI (TypeScript)**: Ink.js components in `clients/cli/src/`

## Project Structure

```
decepticon/          Python agents, core logic, backends
clients/cli/         Ink.js terminal UI (TypeScript)
decepticon/skills/   Markdown knowledge base for agents
containers/          Dockerfiles
config/              Runtime configuration
scripts/             Installer and utilities
docs/                Documentation
```

## Authoring Skills

Every `packages/decepticon/decepticon/skills/**/SKILL.md` file must
conform to the schema in [docs/skill-schema.md](docs/skill-schema.md).
Before opening a PR, run `make audit-skills` locally and fix any
reported violations. CI runs the same check on every PR.

For the cleanup of legacy skills that pre-date the schema, see
[docs/skill-cleanup-process.md](docs/skill-cleanup-process.md). New
authors writing skills against the schema do not need to read the
cleanup process — only the schema doc.

## Releases

Maintainers: see [RELEASE.md](RELEASE.md) for the versioning model and the release process.

## Security

If you discover a security vulnerability, please follow our [Security Policy](SECURITY.md) instead of opening a public issue.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
