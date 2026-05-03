# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in Decepticon, please report it responsibly:

1. **GitHub Security Advisories** (preferred): Use [GitHub's private vulnerability reporting](https://github.com/PurpleAILAB/Decepticon/security/advisories/new) to submit a report directly. If this link returns a 404, the feature may be pending enablement — use the email method below instead.

2. **Email**: Contact the maintainers at **purpleailab@gmail.com** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)

## What to Report

- Vulnerabilities in Decepticon's code (agent logic, sandbox escapes, credential handling)
- Docker container security issues (privilege escalation, network isolation bypass)
- Dependency vulnerabilities that directly affect Decepticon
- Insecure default configurations

## What NOT to Report

- Vulnerabilities in target systems that Decepticon is designed to test (that's the point)
- General security best practices or hardening suggestions (open a regular issue instead)
- Vulnerabilities in third-party services not bundled with Decepticon

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 7 days
- **Fix or mitigation**: Dependent on severity, typically within 30 days

## Responsible Use

Decepticon is an offensive security tool designed for **authorized** red team engagements only. Users are responsible for ensuring they have proper authorization before using Decepticon against any target. See the [LICENSE](LICENSE) for terms of use.
