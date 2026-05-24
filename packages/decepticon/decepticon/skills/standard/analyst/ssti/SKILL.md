---
name: ssti
description: Hunt server-side template injection across Jinja2/Twig/Freemarker/Velocity/Handlebars and validate progression from expression injection to code execution.
---

# SSTI Playbook

## High-signal checks
- Look for template rendering with user input in `render_template_string`, `Template(...)`, `twig->createTemplate`, `Freemarker Template.process`.
- Confirm user-controlled payload reaches a template context key or template source string.

## Fast probes
- Jinja2: `{{7*7}}`, `{{config}}`, `{{request}}`
- Twig: `{{7*7}}`, `{{_self}}`
- Freemarker: `${7*7}`
- Velocity: `#set($x=7*7)$x`

## Escalation path
1. Detect expression evaluation.
2. Enumerate available objects and filters.
3. Attempt file read / env leak.
4. Attempt command execution via framework-specific gadget chain.

## Validation
Use `validate_finding` with a positive execution signal and a benign negative control.
