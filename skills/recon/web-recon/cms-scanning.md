---
name: web-cms-scanning
description: "CMS-specific scans — WordPress (wpscan), Joomla, Drupal version detection."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "WordPress, wpscan, Joomla, Drupal, CMS scan, CMS detection"
  tags: cms-scan, wpscan
  mitre_attack: T1592.004
---

# CMS-Specific Scanning

Once tech fingerprinting (or HTML inspection) confirms a CMS, switch from generic discovery to CMS-aware tooling — version, plugins/themes, user enum, and CMS-specific RCE entry points.

## WordPress

```bash
# wpscan (comprehensive)
wpscan --url https://<target> --enumerate vp,vt,u,dbe --api-token <WP_API_TOKEN>

# Quick checks
curl -s "https://<target>/wp-json/wp/v2/users" | python3 -m json.tool
curl -s "https://<target>/xmlrpc.php" -d '<methodCall><methodName>system.listMethods</methodName></methodCall>'
curl -s "https://<target>/?author=1" -I | grep Location
```

## Joomla

```bash
# Version detection
curl -s "https://<target>/administrator/manifests/files/joomla.xml" | grep -oP '<version>\K[^<]+'
```

## Drupal

```bash
curl -s "https://<target>/CHANGELOG.txt" | head -5
```
