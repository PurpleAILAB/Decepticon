# Arsenal — declarative pentest-tool registry

## Why

Decepticon's existing tool layer is hand-coded per-tool: every binary
agents call (nmap, ffuf, sqlmap, nxc, hashcat, etc.) needs its own
Python module under `decepticon/tools/{ad,web,reversing,...}/`. That
scales linearly with the tool count — adding nuclei is a ~50 LOC
wrapper, adding kerbrute is a ~40 LOC wrapper, adding 150 binaries is
~7,500 LOC of boilerplate.

The Arsenal layer flips it: every tool is **one declarative ToolSpec**
in `decepticon/arsenal/registry.py`. ArgSchema describes typed args
that render to CLI flags. A FastMCP server (or any LangChain adapter)
auto-generates the MCP/tool surface from the registry.

## Comparison

| Aspect | Hand-coded module | Arsenal ToolSpec |
|---|---|---|
| Add a tool | New `.py` file, ~50 LOC | One dict entry, ~10 LOC |
| Add an arg | Edit Python signature + ENV plumbing | Add an ArgSchema row |
| Discover all tools | grep + read 10 modules | Iterate REGISTRY |
| Categorize tools | Folder layout | `category` field |
| Validate args | Custom per-tool | `required`/`choices`/`type` declarative |
| Stay in sync w/ binary's CLI | Manual code change | Update ArgSchema |
| LLM tool-discovery format | Per-module docstrings | Auto-generated from spec |

## Registry shape

```python
ToolSpec(
    name="nmap",
    binary="nmap",
    category="recon",
    description="Network scanner — port enum, service detection, OS fingerprint, NSE scripts.",
    args=[
        ArgSchema("target", str, required=True),
        ArgSchema("ports", str, flag="-p", default="-"),
        ArgSchema("service_detection", bool, flag="-sV"),
        ArgSchema("scripts", str, flag="--script"),
        # ...
    ],
    examples=["nmap -sV -p 1-65535 10.0.0.1"],
    install_hint="apt install nmap",
)
```

`build_command(args: dict)` → `list[str]` ready to exec via the
sandbox.

## Current coverage (v0.1)

31 tools across 7 categories:

| Category | Tools |
|---|---|
| recon | nmap, masscan, subfinder, httpx, nuclei, katana, dnsx |
| web | ffuf, sqlmap, dalfox, commix, feroxbuster |
| ad | nxc (NetExec), bloodhound-python, impacket-GetUserSPNs / GetNPUsers / secretsdump, certipy, kerbrute |
| crypto | hashcat, john, hydra, ciphey, hashid |
| re | binwalk, strings, r2 |
| mobile | jadx, apktool |
| cloud | aws, kubectl |

Target for v0.2: 80 tools (adding `commix`, `nikto`, `wfuzz`, `wpscan`,
`amass`, `gobuster`, `dirsearch`, `gau`, `waybackurls`, `aquatone`,
`gowitness`, `naabu`, `enum4linux-ng`, `evil-winrm`, `responder`,
`mitm6`, `chisel`, `socat`, `frida`, `objection`, `mob-sf`, `apksigner`,
`apkanalyzer`, `pacu`, `scoutsuite`, `cloudfox`, `pwntools-cli`,
`pwninit`, `gef`/`pwndbg` commands, ... ).

## Integration options

### A. Sidecar MCP container (preferred for production)

1. Add a new `arsenal` service to `docker-compose.yml` running
   `python -m decepticon.arsenal --transport stdio` (or `--transport sse`
   for HTTP)
2. Mount the same DockerSandbox so the arsenal MCP server has the same
   execution substrate
3. Register the arsenal MCP server in LiteLLM config or each agent's
   middleware so tools become callable

### B. Direct in-process LangChain adapter

```python
from decepticon.arsenal import REGISTRY
from langchain_core.tools import StructuredTool

def make_langchain_tool(spec):
    def _run(**kwargs):
        cmd = spec.build_command(kwargs)
        return sandbox.run(cmd)  # existing DockerSandbox
    return StructuredTool.from_function(
        func=_run,
        name=spec.name,
        description=spec.description + "\n\nExamples:\n  " + "\n  ".join(spec.examples),
    )

tools = [make_langchain_tool(s) for s in REGISTRY if s.category in ("recon", "web")]
# Pass `tools` to the recon / exploit sub-agent constructors
```

This integrates without needing a separate MCP server process.

## Adding a tool

1. Open `decepticon/arsenal/registry.py`
2. Append a `ToolSpec(...)` entry. Fill in:
   - `name`: short MCP/tool name (lowercase, no spaces)
   - `binary`: actual binary path (assumes `$PATH` resolution)
   - `category`: one of `recon`/`web`/`ad`/`crypto`/`re`/`mobile`/
     `cloud`/`utility`
   - `description`: 1-line, agent-facing
   - `args`: each ArgSchema declares one arg
   - `examples`: 1-3 invocation patterns
   - `install_hint`: `apt install x` / `pipx install x` / `go install ...`
3. Run `pytest tests/unit/arsenal/` — the registry-coverage tests will
   reject your addition if it's missing `examples` or `install_hint`,
   or if the name duplicates an existing tool
4. Open a PR

## Anti-patterns

- **ArgSchema for every possible CLI flag** — declare ONLY the args
  agents actually need. Over-declaration creates surface area for
  hallucinated calls.
- **Long descriptions** — keep ≤ 1 line. Examples carry the detail.
- **No examples** — LLMs use examples to pattern-match; missing them
  means worse tool selection.
- **`requires_root=True` without docs** — flag it AND explain in
  description (e.g. "needs root for ARP / raw socket").

## Roadmap

| Version | Adds |
|---|---|
| 0.1 (this PR) | Registry + 31 tools + FastMCP server builder + tests |
| 0.2 | 50+ more tools; output parsers (per-tool stdout → structured findings) |
| 0.3 | Success-signal regex per tool (auto-classify exit status); retry hints |
| 0.4 | YAML loader so `arsenal.yml` adds tools without code changes |
| 0.5 | Per-tool wordlist + payload references → corpus integration |

## License

Same as Decepticon. Each underlying binary has its own license — install
hints point at the upstream where applicable.
