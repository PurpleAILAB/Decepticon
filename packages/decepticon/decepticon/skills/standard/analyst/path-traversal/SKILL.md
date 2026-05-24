---
name: path-traversal
description: Hunt directory traversal and archive traversal (ZipSlip/TarSlip) from user input to filesystem operations.
---

# Path Traversal Playbook

## Find sinks
- `open(user_path)`, `send_file(user_path)`, file download endpoints, archive extraction APIs.

## Probe payload classes
- Relative traversal: `../../../../etc/passwd`
- Encoded traversal: `%2e%2e%2f`
- Mixed separators: `..\\..\\windows\\win.ini`
- Archive traversal: entries like `../../app/config.py`

## Verify controls
- Canonicalization done before allowlist check.
- Path confinement to intended root.

## Validation
Confirm unauthorized file read/write outside allowed directory with positive and negative controls.
