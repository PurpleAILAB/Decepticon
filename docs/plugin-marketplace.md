# Plugin Marketplace

The Decepticon plugin marketplace provides a curated registry of
community and first-party extensions. Plugins add new agents, tool
integrations, report formats, and detection capabilities without
modifying the core platform.

## Architecture

```
registry.json          Marketplace           graph_registry
  (static)     --->    (discovery)    --->   (runtime activation)
                           |
                     pip / uv install
```

Plugins ship as standard Python packages with a `decepticon.subagents`
entry-point group. The marketplace reads `registry.json` for discovery
metadata; actual installation uses `pip install` (or `uv pip install`).

## Quick Start

### List available plugins

```python
from decepticon.plugins.marketplace import Marketplace

mp = Marketplace()
for plugin in mp.list_plugins():
    print(f"{plugin.name} v{plugin.version} [{plugin.category}]")
    print(f"  {plugin.description}")
```

### Search plugins

```python
results = mp.search("cve")
# Returns plugins matching "cve" in name, description, or tags
```

### Filter by category

```python
enrichment_plugins = mp.list_plugins(category="enrichment")
```

### Check status

```python
status = mp.check_status("vuln-enricher")
# PluginStatus.AVAILABLE | .INSTALLED | .ACTIVE | .INCOMPATIBLE
```

## Installing a Plugin

```bash
# Install from PyPI (or GitHub)
pip install decepticon-vuln-enricher

# Or with uv
uv pip install decepticon-vuln-enricher
```

After installation, activate the plugin bundle:

```bash
# Via environment variable (persists across restarts)
DECEPTICON_PLUGINS=standard,vuln-enricher decepticon start

# Or at runtime via the API
curl -X POST http://localhost:2024/_decepticon/bundles/vuln-enricher/enable
```

## Plugin Categories

| Category | Description |
|----------|-------------|
| `enrichment` | CVE/CPE enrichment, EPSS scoring, threat intel |
| `c2` | Command-and-control framework integrations |
| `reporting` | Report generation (PDF, DOCX, HTML) |
| `scanner` | Vulnerability scanner integrations |
| `emulation` | Adversary emulation frameworks |
| `integration` | Third-party tool sync (Jira, Slack, etc.) |
| `detection` | Detection rule generation (Sigma, YARA) |

## Writing a Plugin

A plugin is a Python package that:

1. Declares agent specs with `bundle="<your-bundle>"` in each
   `SUBAGENT_SPEC`.
2. Registers the `decepticon.subagents` entry-point group in
   `pyproject.toml`.
3. Ships a `register()` function at the declared `entry_point`.

### Minimal `pyproject.toml`

```toml
[project]
name = "decepticon-my-plugin"
version = "0.1.0"
dependencies = ["decepticon-core>=1.0.0"]

[project.entry-points."decepticon.subagents"]
my_agent = "decepticon_my_plugin.agent:SUBAGENT_SPEC"
```

### Minimal agent

```python
from decepticon_core.plugin_loader import SubagentSpec

SUBAGENT_SPEC = SubagentSpec(
    name="my_agent",
    bundle="my-plugin",
    graph_module="decepticon_my_plugin.agent",
    graph_attr="graph",
    parent_agents=("decepticon",),
    description="My custom agent",
)
```

See `packages/decepticon/decepticon/agents/plugins/` for the canonical
reference implementation (vulnresearch family).

## Registry Format

The `registry.json` file uses a flat schema:

```json
{
  "version": "1.0.0",
  "plugins": [
    {
      "name": "plugin-name",
      "version": "0.1.0",
      "description": "What it does",
      "author": "Author",
      "license": "MIT",
      "category": "enrichment",
      "entry_point": "package.module:register",
      "min_decepticon_version": "1.0.0",
      "dependencies": ["decepticon-core>=1.0.0"],
      "tags": ["tag1", "tag2"],
      "homepage": "https://github.com/...",
      "sha256": ""
    }
  ]
}
```

To submit a plugin to the registry, open a PR adding your entry to
`packages/decepticon/decepticon/plugins/registry.json`.
