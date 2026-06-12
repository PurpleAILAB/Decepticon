# Update channels

Decepticon publishes two update channels so operators can choose between
conservative stability and early access to fixes.

| Channel | Tracks | GHCR tag | Who it's for |
|---------|--------|----------|--------------|
| **stable** (default) | The newest **final** release (no pre-releases). | `:stable` | Production / most users. The safe default. |
| **latest** | The newest release **including pre-releases** (`vX.Y.Z-rc.N`). | `:latest` | Early adopters who want fixes before they're finalized. |

A pre-release moves `:latest` but **not** `:stable`; a final release moves
both. So `stable` only ever advances to vetted final releases, while
`latest` surfaces release candidates first.

## Selecting a channel

The channel lives in `DECEPTICON_CHANNEL` in your `~/.decepticon/.env`
(default `stable` when unset or unrecognized — a typo can never silently
opt you into pre-release images):

```bash
# ~/.decepticon/.env
DECEPTICON_CHANNEL=latest
```

It can be set three ways:

- **At install** — `CHANNEL=latest curl -fsSL https://decepticon.red/install | bash`.
  The installer resolves and pins the newest version on that channel.
- **In `.env`** — set `DECEPTICON_CHANNEL=stable|latest`. The launch-time
  self-update and `decepticon update` both honor it.
- **Per command** — `decepticon update --channel latest` overrides `.env`
  for that one run (does not persist).

Pinning an exact version still wins over the channel:
`VERSION=1.2.0 curl ... | bash` (install) or `DECEPTICON_VERSION=1.2.0`
(compose) installs that exact tag regardless of channel.

## How it works

- **Launcher self-update / `decepticon update`** resolve the channel via
  `updater.ResolveChannel` and fetch accordingly:
  - `stable` → GitHub `…/releases/latest` (which already excludes
    pre-releases and drafts).
  - `latest` → GitHub `…/releases` and picks the newest non-draft release
    by SemVer precedence, pre-releases included.
- **Version comparison** is full SemVer §11: a pre-release ranks *below*
  its associated final version (`1.2.0-rc.1 < 1.2.0`), and prerelease
  identifiers compare field-by-field (`rc.2 < rc.10`). This is what lets
  the `latest` channel offer an `-rc` and then upgrade to the final, and
  prevents the `stable` channel from ever "upgrading" to a pre-release.
- **Docker image tags** are promoted by the release workflow's
  `publish-release` job: `:stable` for final releases only, `:latest` for
  every release.
- **Compose fallback.** When `DECEPTICON_VERSION` is unset, the images in
  `docker-compose.yml` fall back to `:stable` (`${DECEPTICON_VERSION:-stable}`)
  — the conservative default. In normal operation the launcher pins
  `DECEPTICON_VERSION` to a concrete version, so the fallback is only a
  safety net for direct `docker compose` use.

## Notes

- `:stable` is seeded by the first **final** release published after this
  feature landed; until then, pin `DECEPTICON_VERSION` if you run
  `docker compose` directly without the launcher.
- Drafts are never installed: GitHub omits them from anonymous
  `…/releases` responses, and the launcher additionally skips any
  `draft: true` entry.
- The channel is independent of `AUTO_UPDATE` (which controls *whether*
  updates apply automatically) and `DECEPTICON_BRANCH` (which tracks a git
  branch's config instead of a release tag).
