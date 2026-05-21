"""CI/CD integration — Strix-style ``decepticon scan`` headless gate.

Two pieces:

* :mod:`decepticon.cicd.scope` — resolve a *diff scope* (the set of files
  a PR changed) so a CI run only assesses what moved, matching Strix's
  ``--scope-mode diff --diff-base origin/main``.
* :mod:`decepticon.cicd.scan` — the headless entrypoint: resolve scope,
  (optionally) trigger the engagement, then read the findings artifact
  and exit non-zero when in-scope findings exist. This is the
  CI-gating contract — a failing exit blocks the PR merge.

The module is import-light (stdlib + the existing findings export) so the
GitHub Action can run ``python -m decepticon.cicd.scan`` without spinning
the full Docker stack just to evaluate the gate.
"""

from decepticon.cicd.scope import DiffScope, resolve_diff_scope

__all__ = ["DiffScope", "resolve_diff_scope"]
