# Changelog

All notable changes to Decepticon are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> The `version` field in `pyproject.toml` and the `package.json` files carries a
> permanent `0.0.0` sentinel. The real version is stamped from the git tag at
> build time — see [RELEASE.md](RELEASE.md) for the release process.

## [Unreleased]

### Added

- `CHANGELOG.md` and `RELEASE.md` documenting version history and the release process.

### Fixed

- `make test-local` now passes on Windows. The engagement filesystem backend
  normalizes virtual `/workspace` paths with `posixpath` instead of the
  OS-dependent `os.path`, and shared sandbox class state is reset between tests.

### Changed

- Repository hygiene for the open-source release: the dev-only `skills/_corpus/`
  reference corpus is ignored, and stale `@decepticon/ee` references were dropped
  from `.gitignore` and `.dockerignore`.
- Documentation refreshed to describe Soundwave's eight-document engagement
  bundle (previously documented as three or four documents).

## [1.1.1] — 2026-05-22

### Added

- PyPI-distributable core: skills ship as package data, optional extras are
  lean, and a `publish-pypi` job pushes the wheel via Trusted Publishing (#273).

### Fixed

- The langgraph image installs the `neo4j` extra so the knowledge graph works
  after `neo4j` moved to an optional dependency extra (#274).

### Removed

- `@decepticon/ee` enterprise-edition references from the OSS repository (#270).

## [1.1.0] — 2026-05-21

### Added

- Entry-point plugin system with bundle activation and a skills/backends
  architecture (#262).
- Plugin override system and a langchain-style library API across all 16 agent
  factories (#268).
- Runtime plugin bundles with `/plugins` and `/agent` CLI switchers (#264).
- Push-style background-command notifications in the CLI, with command output
  inlined (#265).
- Soundwave's engagement bundle expanded from three to eight documents, with a
  mandatory completion call (#267).

### Changed

- Soundwave collects operator input through a single channel with no mid-bundle
  approval gates (#266).
- Sandbox transport is HTTP-only; the host Docker-socket dependency was removed,
  bounding the blast radius of sandboxed execution (#263).

Releases before 1.1.0 predate this changelog — see the
[GitHub Releases](https://github.com/PurpleAILAB/Decepticon/releases) page.

[Unreleased]: https://github.com/PurpleAILAB/Decepticon/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/PurpleAILAB/Decepticon/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/PurpleAILAB/Decepticon/compare/v1.0.27...v1.1.0
