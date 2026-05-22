# PyPI Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `decepticon` a correct, lean, PyPI-publishable wheel — skills ship as package data, heavy deps are optional, benchmark skills are excluded, and a release job publishes to PyPI via Trusted Publishing.

**Architecture:** Relocate `skills/` into the package (`decepticon/skills/`) and resolve its path via `importlib.resources`, so the same code works for wheel/editable/Docker installs. Keep the agent-facing logical `/skills/` convention (mapped by `CompositeBackend`) unchanged. Split optional deps (`neo4j`) into extras; the driver is already lazily imported. Exclude benchmark skills from the wheel. Add a `publish-pypi` job to the existing release workflow.

**Tech Stack:** Python 3.13, hatchling, uv, pytest, GitHub Actions, PyPI Trusted Publishing.

**Spec:** `docs/superpowers/specs/2026-05-22-pypi-distribution-strategy-design.md`

---

### Task 1: Relocate `skills/` into the package + resolve via `importlib.resources`

This is one atomic change: the move breaks the Dockerfile/compose/CI references that point at the old root path, so they are fixed in the same commit to keep build + dev green.

**Files:**
- Move: `skills/` → `decepticon/skills/`
- Modify: `decepticon/backends/__init__.py:6-14` (comment + `SKILLS_LOCAL_PATH`)
- Modify: `containers/langgraph.Dockerfile:21` (remove redundant copy)
- Modify: `docker-compose.dev.yml:45` (bind path)
- Modify: `docker-compose.watch.yml:20` (watch path/target)
- Test: `tests/unit/backends/test_skills_path.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/backends/test_skills_path.py`:

```python
import os

from decepticon.backends import SKILLS_LOCAL_PATH


def test_skills_local_path_resolves_into_the_package():
    # Skills ship as package data under decepticon/skills/, so the resolved
    # path must end in .../decepticon/skills and actually exist on disk.
    assert SKILLS_LOCAL_PATH.endswith(os.path.join("decepticon", "skills"))
    assert os.path.isdir(SKILLS_LOCAL_PATH)


def test_standard_and_shared_bundles_are_present():
    assert os.path.isdir(os.path.join(SKILLS_LOCAL_PATH, "standard"))
    assert os.path.isdir(os.path.join(SKILLS_LOCAL_PATH, "shared"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/backends/test_skills_path.py -v`
Expected: FAIL — `SKILLS_LOCAL_PATH` is `/app/skills` (does not end in `decepticon/skills` and does not exist on the dev box).

- [ ] **Step 3: Move the skills tree into the package**

```bash
git mv skills decepticon/skills
```

- [ ] **Step 4: Resolve `SKILLS_LOCAL_PATH` from the installed package**

In `decepticon/backends/__init__.py`, replace lines 1-14 (the imports header + comment + constant) with:

```python
import importlib.resources

from deepagents.backends import CompositeBackend, FilesystemBackend

from .factory import build_sandbox_backend
from .http_sandbox import HTTPSandbox

# Skills ship as package data under ``decepticon/skills/`` and are read
# in-process by a local ``FilesystemBackend`` (not the sandbox container).
# Resolving via ``importlib.resources`` yields the correct on-disk location
# for every install shape — wheel (site-packages), editable (repo checkout),
# and the langgraph Docker image (``/app/decepticon/skills``) — so no
# container-specific path is hardcoded.
SKILLS_LOCAL_PATH = str(importlib.resources.files("decepticon") / "skills")
```

Also update the docstring line in `make_agent_backend` that reads
`/skills/...   ->  /app/skills/... in the langgraph container (~5ms)` to:

```python
#   /skills/...   ->  decepticon/skills/... read in-process (~5ms)
```

- [ ] **Step 5: Remove the now-redundant Dockerfile copy**

In `containers/langgraph.Dockerfile`, delete line 21:

```dockerfile
COPY skills/ skills/
```

(Skills are now under `decepticon/` and arrive via the existing `COPY decepticon/ decepticon/` on line 20. `importlib.resources` resolves them to `/app/decepticon/skills`.)

- [ ] **Step 6: Update the dev bind mount**

In `docker-compose.dev.yml`, change line 45 from:

```yaml
      - ./skills:/app/skills:ro
```
to:
```yaml
      - ./decepticon/skills:/app/decepticon/skills:ro
```

- [ ] **Step 7: Update the compose-watch sync path**

In `docker-compose.watch.yml`, update the skills watch entry so its `path` is `./decepticon/skills` and its `target` (line 20) is:

```yaml
          target: /app/decepticon/skills
```

- [ ] **Step 8: Run the path tests + existing skills/backends suites**

Run: `uv run pytest tests/unit/backends/ tests/unit/middleware/test_skills.py -v`
Expected: PASS (the new path tests pass; existing skills/middleware tests still pass because the logical `/skills/` convention is unchanged).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(skills): relocate skills/ into decepticon/ package + resolve via importlib.resources"
```

---

### Task 2: Correct the stale "skills live in the sandbox" prompt + comments

The agent-facing skills prompt and several docstrings still claim skills are baked into the sandbox container. After the backend split they are local to the langgraph process; the text misinforms the agent and future readers.

**Files:**
- Modify: `decepticon/middleware/skills.py:104-111` (agent-facing prompt — Access Rules)
- Modify: `decepticon/tools/skills.py:45-46,96-97` (docstrings)
- Modify: `decepticon/agents/standard/exploit.py:16`, `decepticon/agents/standard/postexploit.py:16` (header comments)
- Test: `tests/unit/middleware/test_skills.py` (existing — must still pass)

- [ ] **Step 1: Fix the agent-facing Access Rules block**

In `decepticon/middleware/skills.py`, replace the `### Access Rules` bullets (lines 104-111) with:

```python
### Access Rules
- `load_skill("/skills/<category>/<skill-name>/SKILL.md")` — **REQUIRED** for
  every /skills/* file. Returns the FULL body (no line limit) plus a base
  directory header and an index of references/* and sibling sub-skills in the
  same directory.
- `read_file("/skills/...")` and `bash(command="cat /skills/...")` — DO NOT
  use these for skill files. `/skills/` is served in-process by a local
  FilesystemBackend (not the sandbox); only `load_skill` resolves it.
```

- [ ] **Step 2: Fix the `decepticon/tools/skills.py` docstrings**

Replace the two stale references (lines ~45-46 and ~96-97) that mention the
"sandbox container's `/skills/` mount / where `/skills/` is baked into the
image" with text describing the local FilesystemBackend route, e.g.:

```python
    # ``/skills/`` is routed by ``CompositeBackend`` to a local
    # ``FilesystemBackend`` reading the package's ``decepticon/skills`` tree
    # in-process — it is NOT served from the sandbox container.
```

(Apply to both docstring locations; keep surrounding wording intact.)

- [ ] **Step 3: Fix the agent header comments**

In `decepticon/agents/standard/exploit.py:16` and
`decepticon/agents/standard/postexploit.py:16`, change the parenthetical
`/skills/ live in the ...` note to:

```python
# Backend: HTTPSandbox for /workspace; /skills/ served in-process from the
# local decepticon/skills package tree via CompositeBackend.
```

- [ ] **Step 4: Run the skills middleware test**

Run: `uv run pytest tests/unit/middleware/test_skills.py -v`
Expected: PASS (prompt still formats; only wording changed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs(skills): correct stale 'skills baked in sandbox' prompt + comments"
```

---

### Task 3: Move `neo4j` to an optional extra (lean core)

The neo4j driver is already imported lazily (`decepticon/tools/research/neo4j_store.py:118`, inside `Neo4jStore.__init__`, guarded by `Neo4jUnavailableError`). So the only change is packaging — plus a regression test that proves importing the research tools does not import the driver at module load.

**Files:**
- Modify: `pyproject.toml:66` (remove `neo4j` from core) and `:69` area (add extras)
- Test: `tests/unit/research/test_no_neo4j_at_import.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/research/test_no_neo4j_at_import.py`:

```python
import subprocess
import sys


def test_research_tools_do_not_import_neo4j_at_module_load():
    # Base `pip install decepticon` (no neo4j extra) must still import the
    # research tools. The driver is loaded lazily only when a Neo4jStore is
    # constructed. A subprocess gives a clean module table.
    code = (
        "import sys; "
        "import decepticon.tools.research.tools; "
        "assert 'neo4j' not in sys.modules, sorted(m for m in sys.modules if 'neo4j' in m)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
```

- [ ] **Step 2: Run the test to verify current behavior**

Run: `uv run pytest tests/unit/research/test_no_neo4j_at_import.py -v`
Expected: PASS already (import is lazy). This test is a **regression guard** — it locks in the contract before we move neo4j to an extra. If it FAILS, stop and make the offending import lazy before continuing.

- [ ] **Step 3: Move `neo4j` from core deps to an extra**

In `pyproject.toml`, delete from the core `dependencies` list (line 66):

```toml
    # Graph memory (Neo4j attack-chain graph)
    "neo4j>=5.0",
```

Add a new section immediately after `dependencies = [ ... ]` (before `[dependency-groups]`):

```toml
[project.optional-dependencies]
neo4j = ["neo4j>=5.0"]
all = ["decepticon[neo4j]"]
```

- [ ] **Step 4: Re-lock and re-run the guard test**

Run:
```bash
uv lock
uv run pytest tests/unit/research/test_no_neo4j_at_import.py -v
```
Expected: PASS. (`uv lock` keeps `uv.lock` consistent; neo4j stays available in the dev env via the lock/extra, so the import-time guard remains meaningful as the lazy-load contract.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/unit/research/test_no_neo4j_at_import.py
git commit -m "build(deps): move neo4j to an optional extra (decepticon[neo4j])"
```

---

### Task 4: Exclude benchmark skills from the wheel + verify wheel contents

Benchmark skills (`decepticon/skills/benchmark/`) are XBOW/CTF eval-harness conventions. Keep them in-repo for `make benchmark`, but exclude them from the published wheel.

**Files:**
- Modify: `pyproject.toml:153-154` (`[tool.hatch.build.targets.wheel]`)
- Test: `tests/unit/test_wheel_contents.py` (new, builds the wheel)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_wheel_contents.py`:

```python
import glob
import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_bundles_skills_but_excludes_benchmark(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "-m", "hatch", "build", "-t", "wheel", str(tmp_path)],
        cwd=repo_root,
        check=True,
    )
    whl = sorted(glob.glob(str(tmp_path / "*.whl")))[-1]
    names = zipfile.ZipFile(whl).namelist()

    assert any(n.startswith("decepticon/skills/standard/") for n in names), "standard skills missing"
    assert any(n.startswith("decepticon/skills/shared/") for n in names), "shared skills missing"
    assert any(n.startswith("decepticon/skills/plugins/") for n in names), "plugins skills missing"
    assert not any(n.startswith("decepticon/skills/benchmark/") for n in names), "benchmark skills must be excluded from the wheel"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_wheel_contents.py -v`
Expected: FAIL — either `hatch` build includes `decepticon/skills/benchmark/`, or (if data files aren't bundled) the standard/shared asserts fail. This pins down both requirements.

- [ ] **Step 3: Configure the wheel target**

In `pyproject.toml`, replace the `[tool.hatch.build.targets.wheel]` block (lines 153-154) with:

```toml
[tool.hatch.build.targets.wheel]
packages = ["decepticon"]
# Skill markdown trees ship as package data (standard/shared/plugins).
# Benchmark skills are eval-harness conventions — kept in-repo for
# `make benchmark` but excluded from the published wheel.
artifacts = ["decepticon/skills/**/*.md"]
exclude = ["decepticon/skills/benchmark/**"]
```

- [ ] **Step 4: Run the wheel-contents test**

Run: `uv run pytest tests/unit/test_wheel_contents.py -v`
Expected: PASS. If standard/shared `.md` files are still missing, the `artifacts` glob is the fix (forces non-`.py` package data into the wheel); re-run.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/unit/test_wheel_contents.py
git commit -m "build(wheel): bundle skill assets, exclude benchmark skills from the wheel"
```

---

### Task 5: Add the `publish-pypi` release job (Trusted Publishing)

The release workflow already declares `id-token: write` at the top level (`.github/workflows/release.yml:10`), so OIDC Trusted Publishing needs no secret.

**Prerequisite (manual, one-time):** On https://pypi.org, register a Trusted Publisher for the `decepticon` project pointing at this repo + workflow `release.yml` + the `publish-pypi` job. Note this in the PR description; the job will fail to publish until it's configured.

**Files:**
- Modify: `.github/workflows/release.yml` (add a job under `jobs:`)

- [ ] **Step 1: Add the job**

Append to `.github/workflows/release.yml` under `jobs:` (sibling of `launcher`/`docker`):

```yaml
  publish-pypi:
    name: Publish wheel to PyPI
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # PyPI Trusted Publishing (OIDC) — no API token
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Stamp version from the tag
        run: |
          version="${GITHUB_REF_NAME#v}"
          sed -i 's/^version = "[^"]*"/version = "'"$version"'"/' pyproject.toml

      - name: Build wheel + sdist
        run: |
          python -m pip install --upgrade hatch
          hatch build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: Verify the workflow is valid YAML and the job parses**

Run:
```bash
python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/release.yml')); assert 'publish-pypi' in d['jobs']; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Sanity-check the build locally (no publish)**

Run:
```bash
python -m pip install --upgrade hatch && hatch build
ls dist/*.whl dist/*.tar.gz
```
Expected: a wheel and sdist are produced. (This mirrors the job's build step without publishing.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): publish decepticon wheel to PyPI via Trusted Publishing"
```

---

### Task 6: Update distribution docs (git-pin → versioned dependency)

**Files:**
- Modify: `docs/library-usage.md:377-393` (Versioning section)
- Modify: `docs/contributing.md` (around the `pip install decepticon` note, line 114)

- [ ] **Step 1: Update the Versioning section**

In `docs/library-usage.md`, replace the closing "Versioning" guidance (the git-pin block + the "PyPI publication is on the roadmap" line, lines ~383-393) with:

```markdown
Install from PyPI and pin a compatible range in your `pyproject.toml`:

\```toml
[project]
dependencies = [
    "decepticon>=1.0,<2",   # core SDK
    # "decepticon[neo4j]>=1.0,<2",  # add the extra if you use the KG tools
]
\```

The published wheel bundles the `standard`/`shared`/`plugins` skill trees as
package data; benchmark skills are intentionally excluded. Heavy optional
deps (e.g. `neo4j`) live behind extras to keep the base install lean.
```

- [ ] **Step 2: Confirm the contributing note still reads correctly**

Open `docs/contributing.md:114`. The line `End-user installs that just \`pip install decepticon\` get the lean standard-only default.` is now accurate — leave it, or append `(neo4j and other heavy features are opt-in extras)` for clarity.

- [ ] **Step 3: Commit**

```bash
git add docs/library-usage.md docs/contributing.md
git commit -m "docs: switch consumer guidance from git-pin to PyPI versioned dependency"
```

---

## Self-Review

**Spec coverage:**
- §1 single wheel + extras → Task 3 (extras), Task 4 (wheel config). ✅
- §2 skills packaging (move, importlib, logical convention, benchmark exclusion, stale comment) → Task 1 (move/importlib), Task 4 (benchmark exclude), Task 2 (stale comment). ✅
- §3 versioning & release flow → Task 5 (publish-pypi, sed stamping, Trusted Publishing). ✅
- §4 OSS/EE boundary → preserved by Task 4 (only `decepticon/` + selected bundles ship); no code change needed (already clean post-#270). ✅
- §5 coexistence & migration → Task 6 (docs git-pin → versioned dep); Docker turnkey path untouched. ✅
- Risk "guarded optional imports" → Task 3 regression test. ✅
- Risk "importlib + editable installs" → Task 1 tests run under the editable dev install. ✅
- Risk "hatchling .md inclusion" → Task 4 `artifacts` glob + wheel-contents test. ✅

**Placeholder scan:** No TBD/TODO; every code/edit step shows exact content or an exact command with expected output.

**Type/name consistency:** `SKILLS_LOCAL_PATH` (Task 1) referenced consistently; `decepticon[neo4j]`/`decepticon[all]` extras (Task 3) match docs (Task 6); wheel paths `decepticon/skills/...` consistent across Tasks 1/4.

**Out of scope (deferred, per spec non-goals):** `decepticon[runtime]` local-sandbox convenience; switching Docker images to `pip install decepticon==X`.
