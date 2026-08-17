---
name: reverser-thick-client
description: Security testing of desktop thick clients — trust-boundary mapping, local storage and credential exposure, IPC authentication, traffic interception, client-side check bypass, and update-channel/supply-chain review.
metadata:
  subdomain: reverse-engineering
  when_to_use: "thick client desktop application electron qt wpf winforms ipc named pipe local storage config credentials update channel certificate pinning dll hijack client-side"
  mitre_attack: T1552.001, T1040
  upstream_ref: "reverse-skill:skills/thick-client (github.com/zhaoxuya520/reverse-skill @ ea582f3, MIT)"
---

# Thick Client Security Testing

For authorized testing of desktop clients (C/S apps, Electron, Qt,
.NET WinForms/WPF) where the server trusts client-side decisions. Pure
web targets go to the web lane; this skill covers the surfaces that only
exist because code runs on the operator's host.

Confirm scope before touching the app: installer source and test
accounts belong in the engagement record, and any traffic interception
targets only in-scope infrastructure.

## 1. Map the trust boundary

```text
□ Process tree: child processes, bundled services/drivers
□ Listening ports and outbound domains
□ Local sensitive paths: %APPDATA% / ~/.config / Keychain / registry
```

Procmon or `strace -f` on first run shows which files and keys the
client actually touches.

## 2. Local attack surface

```text
□ Plaintext configs, hardcoded keys, debug switches
□ DLL search-order / hijack opportunities (Windows)
□ Local databases: SQLite file permissions, encryption-at-rest keys
□ IPC endpoints (named pipes, domain sockets, localhost RPC):
  who can connect, and is the caller authenticated?
```

Strings + import review on the main binary covers most of this:

```
bin_strings(path="/workspace/client", category_filter="secret")
bin_strings(path="/workspace/client", category_filter="crypto")
bin_symbols_report(path="/workspace/client")
```

## 3. Network surface

```text
□ System proxy honored, or app-custom TLS stack?
□ Certificate pinning → bypass via Frida/objection, or follow the
  mobile lane's pinning playbooks
□ Hidden/privileged API endpoints the UI never exposes — replay with
  a low-privilege token and check server-side authorization
```

Run the client behind Burp/mitmproxy; log every endpoint to
`/workspace/thickclient/endpoints.md`.

## 4. Reverse to verify

| Client stack | Go to |
|---|---|
| .NET | `/skills/standard/reverser/dotnet-malware/SKILL.md` methodology (dnSpy/de4dot) |
| Native | `/skills/standard/reverser/ghidra/SKILL.md` |
| Electron | unpack `app.asar`, then `/skills/standard/reverser/js-reverse/SKILL.md` |

Verify each suspected client-side check (license, role, feature flag)
in the binary — server-side enforcement is what matters, client checks
are cosmetic.

## 5. Update channel and supply chain

```text
□ Update transport: signed packages? TLS? Signature verified before exec?
□ Update manifest fetch: can it be redirected on a hostile network?
□ Installer/write permissions on install dir (pre-req for DLL planting)
```

## 6. Record

```
kg_add_node("entrypoint", label="<client> IPC/API surface",
  props={"ipc_auth": "none|token|mutual", "pinning": true,
         "findings": "/workspace/thickclient/",
         "key": "thickclient:<target>"})
```

Each confirmed finding (plaintext creds, unauthenticated IPC, missing
server-side authz) gets its own `vulnerability` node with repro steps.
