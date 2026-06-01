# Release Process

How Decepticon is versioned and released.

## Versioning

Decepticon follows [Semantic Versioning](https://semver.org/). Releases are
tagged `vMAJOR.MINOR.PATCH` (e.g. `v1.1.1`); pre-releases use a suffix
(e.g. `v1.2.0-rc.1`).

The `version` field in `pyproject.toml`, `clients/cli/package.json`, and
`clients/web/package.json` is a permanent `0.0.0` **sentinel**. The real
version is stamped from the git tag at build time — `release.yml` rewrites the
sentinel for the PyPI build and passes `--build-arg VERSION=<tag>` into the
Docker images. There is no version-bump commit to make before tagging.

## Cutting a release

1. Make sure `main` is green and the working tree is clean.
2. Run the local gates:
   ```bash
   make quality      # Python + CLI + Web: lint, typecheck, tests
   make smoke        # Compose build + service health checks
   ```
   Optionally run `make dogfood` for a full launcher → onboard → up smoke test.
3. In [CHANGELOG.md](CHANGELOG.md), move the `[Unreleased]` entries under a new
   `[X.Y.Z] — YYYY-MM-DD` heading and add the compare link at the bottom.
4. Commit the changelog (`docs: release vX.Y.Z`).
5. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

Pushing a `v*` tag triggers `.github/workflows/release.yml`.

## What the release workflow does

| Job | Output |
|-----|--------|
| `publish-pypi` | Builds the wheel + sdist and publishes the `decepticon` package to PyPI via Trusted Publishing (OIDC — no API token). |
| `launcher` | Builds the Go launcher binaries with GoReleaser (which drafts the GitHub release) and uploads `config-checksums.txt`, a SHA-256 integrity manifest for `docker-compose.yml`, `config/litellm.yaml`, and `.env.example`. |
| `docker` | Builds and pushes the multi-arch `litellm`, `langgraph`, `cli`, and `skillogy` images. |
| `docker-heavy` / `docker-heavy-merge` | Builds `sandbox` and `c2-sliver` on native amd64/arm64 runners (the Kali base is too slow under QEMU), then merges the per-arch digests into manifests. |
| `docker-web` / `docker-web-merge` | Builds and merges the `web` image the same way. |
| `publish-release` | Verifies all seven `:<version>` images exist on GHCR, promotes them to `:latest`, and flips the GitHub release from draft to published. |

Every image is signed with Cosign (keyless OIDC) and ships a CycloneDX SBOM.
The `:latest` tag and the published release appear only *after* every image is
verified, so a half-finished release never moves the `:latest` tag.

## Pre-releases

A tag whose version contains a hyphen (`v1.2.0-rc.1`) is treated as a
pre-release: the GitHub release is marked pre-release and the `:latest` Docker
tag is **not** promoted, so existing `:latest` users are unaffected.

## Recovering a failed release

`.github/workflows/release-recover.yml` is a manual (`workflow_dispatch`)
fallback that re-runs the release steps for an existing tag. Use it when a
transient failure (registry 5xx, Sigstore Rekor outage) leaves a release
half-finished.

## Submodules

`benchmark/xbow-validation-benchmarks` is a git submodule. After cloning, run:

```bash
git submodule update --init --recursive
```

so benchmark runs use the pinned upstream commit. `benchmark/MHBench` is
optional and only needed for that benchmark provider.
