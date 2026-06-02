---
name: chain-xss-to-takeover
description: Build chains from XSS into account takeover or privileged action execution.
metadata:
  subdomain: web-exploitation
  when_to_use: "xss chain account takeover privileged action cookie session csrf token theft post-message"
---

# Chain: XSS to Takeover

## Canonical path
1. Confirm script execution in victim context.
2. Steal session/CSRF token or trigger privileged action.
3. Use stolen material to access victim/admin account.
4. Demonstrate durable account impact.

## Validation
Include both browser-side evidence and server-side action confirmation.
