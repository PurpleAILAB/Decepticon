---
name: trust-boundary-analysis
description: Trust boundary mapping and startup sequence audit for developer tools, CLI apps, and plugin systems. Load when the target is a developer tool, CLI, IDE extension, or any application that loads config from the current directory.
---

# Trust Boundary Analysis

This skill targets the vulnerability class that produced 5 RCE vectors in
Google Gemini CLI from a single architectural flaw: missing workspace trust.
Developer tools that auto-load configuration from untrusted directories are
a rich attack surface.

## When to Use

Apply this skill when the target:
- Loads `.env`, `settings.json`, or config files from the current working directory
- Has a plugin/extension system that auto-discovers and loads code
- Spawns child processes with configuration-controlled commands
- Is a CLI tool, IDE extension, language server, or build tool
- Uses MCP (Model Context Protocol) servers configured via project files

## Startup Sequence Audit

For any CLI tool or developer application, trace the full initialization:

### 1. Config file discovery
```bash
grep -rn 'readFile\|readFileSync\|fs.read\|open(' --include='*.ts' --include='*.js' \
  /workspace/target/src/ | grep -i 'config\|settings\|env\|rc\|\.json'
```

Map the search order. Common dangerous patterns:
- `cwd/.tool/config.json` → `cwd/.env` → `~/.tool/config` → `/etc/tool/config`
- If the local (cwd) config is loaded BEFORE the user's global config, the
  attacker's repo-level config wins.

Record each config loading point:
```
kg_add_node("code_location", "loadConfig() reads .env from cwd",
  props={"file": "src/config/settings.ts", "line": 42, "trust_level": "untrusted"})
```

### 2. Environment variable injection
```bash
grep -rn 'process\.env\|os\.environ\|env::var\|getenv' --include='*.ts' \
  --include='*.py' --include='*.rs' /workspace/target/src/
```

Check: Are env vars from `.env` files injected into `process.env`? Which vars
control dangerous behavior? Look for:
- `*_COMMAND`, `*_CMD`, `*_EXEC` → shell execution
- `*_PROXY` → SSRF / network interception
- `*_PATH`, `*_DIR` → path traversal
- `*_URL` → open redirect / SSRF
- `DEBUG`, `NODE_ENV` → bypass security controls

### 3. Workspace trust check
```bash
grep -rn 'trust\|isTrusted\|workspace.*safe\|folder.*trust' --include='*.ts' \
  --include='*.js' /workspace/target/src/
```

Look for the pattern:
```javascript
// DANGEROUS: trust disabled by default
if (!settings.folderTrustEnabled) {
  return { isTrusted: true };  // ← All workspaces trusted
}
```

If no trust check exists, every config is loaded blindly. This is the root cause.

### 4. Command execution from config
```bash
grep -rn 'spawn\|exec\|execSync\|child_process\|subprocess\|os\.system\|Popen' \
  --include='*.ts' --include='*.js' --include='*.py' /workspace/target/src/
```

For each `spawn`/`exec` call, check:
- Is `shell: true` set? → shell injection via crafted values
- Does the command come from config? → attacker-controlled execution
- Is there any validation/allowlist on the command?

### 5. Plugin/tool auto-discovery
```bash
grep -rn 'discoverTools\|loadPlugins\|autoDiscover\|mcpServers\|toolDiscovery' \
  --include='*.ts' --include='*.js' /workspace/target/src/
```

Check: Are plugins/tools loaded from project-level config BEFORE any user
confirmation? MCP servers, language server plugins, and build tool extensions
are common vectors.

## Trust Boundary Graph Modeling

Map the attack flow as a chain in the knowledge graph:

```
ENTRYPOINT (malicious .env file in cloned repo)
  → enables → ENV_INJECT (process.env poisoned)
    → enables → SHELL_EXEC (spawn with shell:true)
      → reaches → CROWN_JEWEL (arbitrary code execution)
```

Use low edge weights (0.2–0.4) for automatic/silent steps. Use higher weights
(1.0+) for steps requiring user interaction.

Then call `plan_attack_chains(top_k=5)` to surface the cheapest paths.

## Shell Quoting Vulnerabilities

When config values flow into shell commands, check for:

1. **Direct interpolation**: `` `command ${userValue}` `` → injection via `; id`
2. **Single-quote escape**: `osascript -e '${path}'` → escape via `'` in path
3. **Env var in shell context**: `PROXY_CMD="curl evil.com"` → executed as-is
4. **Argument injection**: `spawn('git', ['clone', userUrl])` → `--upload-pack=` prefix

For each, the PoC pattern is:
- Craft input that breaks out of the quoting context
- Inject a command that proves execution (`id`, `env`, write a sentinel file)
- Use `validate_finding` with the sentinel as the success pattern

## Negative Control

Always test: does the same code path execute WITHOUT the malicious config?
The negative control is the same operation with a clean/empty config directory.
If the behavior occurs regardless, it's not a vulnerability — it's expected.
