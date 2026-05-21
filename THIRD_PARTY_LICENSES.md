# Third-Party Licenses

Decepticon vendors external knowledge bases as git submodules under
`skills/_corpus/` and references additional resources at runtime. Each
upstream's license terms are preserved alongside the source in the
submodule itself; this file is a summary attribution.

## Vendored (git submodule)

### PayloadsAllTheThings
- **Path**: `skills/_corpus/payloads/`
- **Upstream**: https://github.com/swisskyrepo/PayloadsAllTheThings
- **License**: MIT
- **Copyright**: © Swissky and contributors
- **Use**: Reference payload catalog cited by `skills/exploit/web/*` leaves
  for additional bypass variants and encoding tricks.

The complete MIT license text ships in `skills/_corpus/payloads/LICENSE`.

## Referenced (not vendored)

### h4cker
- **Upstream**: https://github.com/The-Art-of-Hacking/h4cker
- **License**: MIT
- **Copyright**: © Omar Santos and contributors
- **Use**: Referenced via `skills/_corpus/h4cker_manifest.yaml` (when present)
  — high-value subtrees cloned shallow on demand, not vendored due to size.

### Awesome-Hacking
- **Upstream**: https://github.com/Hack-with-Github/Awesome-Hacking
- **License**: CC0 1.0 Universal (public domain dedication)
- **Use**: Link index flattened into `skills/_corpus/awesome_index.json`
  (when present) for recon-agent learning-resource lookups.

## Decepticon's own license

This repository's own license terms are in `LICENSE` at the repo root.
Vendoring third-party content does not relicense any part of this repo
— the upstream MIT and CC0 licenses remain attached to their respective
submodule contents.

## Updating

```bash
# Pull all submodules to upstream HEAD
git submodule update --remote --recursive

# Or just the payload corpus
git submodule update --remote skills/_corpus/payloads

# Refresh the drift manifest
python3 scripts/ingest_corpus.py
```

The `scripts/ingest_corpus.py --check` command exits non-zero on drift
(new vuln classes, stale hashes, missing leaf mappings); wire into CI
to keep the corpus pinned and the leaf coverage current.
