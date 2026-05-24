---
name: cve
description: "Known CVE exploitation — fingerprint CMS/framework/plugin version, look up CVE candidates via cve_lookup, retrieve PoCs via cve_poc_lookup, adapt the public exploit to the target, and confirm RCE. Use whenever the challenge tag is `cve`, recon fingerprinted a versioned service, or the challenge name hints at known vulnerable software (WordPress, Joomla, Apache Struts, Spring4Shell, Log4j, etc.)."
allowed-tools: Bash Read Write
metadata:
  subdomain: execution
  when_to_use: "cve, CVE, known vulnerability, public exploit, version-specific, plugin vulnerability, CMS exploit, WordPress vulnerability, vulnerable software, patched, unpatched, joomla vulnerability, drupal vulnerability, apache struts, spring4shell, log4j, log4shell, exploit-db, public PoC, n-day exploit, cve_lookup, cve_poc_lookup"
  tags: web-application, cve, known-exploit, n-day, public-poc
  mitre_attack: T1190, T1203, T1059
---

# CVE / Known-Exploit Methodology

Exploits known, version-specific vulnerabilities by fingerprinting the target's software stack, looking up the matching CVE record, retrieving a public PoC, and adapting it to the live target. The exploit agent has two dedicated tools registered for this skill — `cve_lookup` and `cve_poc_lookup` — and this skill is the only place that calls them. If you load this skill, you MUST invoke both tools.

## When to load

Load this skill (in addition to or instead of an attack-class skill) when ANY of the following hold:

1. The challenge `Tags:` line contains `cve`.
2. Recon `SUMMARY.md` fingerprinted a CMS, framework, or service with a concrete version (e.g. `WordPress 5.7.1`, `Apache Struts 2.5.16`, `Drupal 7.58`, `Spring Framework 5.3.17`, `Log4j 2.14.0`).
3. The challenge name or description hints at specific software (`WordPress`, `Joomla`, `phpMyAdmin`, `Spring4Shell`, `Log4Shell`, `Shellshock`, `ProxyShell`, `GhostCat`, etc.).
4. Recon returned a `RECON_HANDOFF:` line that names a software product with a version string.

If none of the above hold, do NOT load this skill — fall back to the attack-class skill matching the symptom (sqli/ssti/lfi/command-injection/etc.).

## Step 1 — Fingerprinting procedure

Concrete probes. Save every output to a file; do NOT inline curl bodies.

```bash
# Generic banner / header / generator-meta fingerprinting
curl -sI "http://$TARGET/" -o /tmp/cve_headers.txt
grep -iE 'server|x-powered-by|x-aspnet-version|x-version|x-generator' /tmp/cve_headers.txt

curl -s "http://$TARGET/" -o /tmp/cve_home.html
grep -iE 'generator|powered by|x-version|wp-includes/js/wp-emoji|joomla|drupal|wp-content' /tmp/cve_home.html | head -20

# nmap service/version detection (when a non-HTTP port is exposed)
nmap -sV -On -p- --version-intensity 7 "$TARGET_HOST" -oN /tmp/cve_nmap.txt

# whatweb — broad CMS/framework signature scan
whatweb -a 3 "http://$TARGET/" --no-errors > /tmp/cve_whatweb.txt 2>&1

# WordPress-specific
curl -sI "http://$TARGET/wp-login.php" -o /tmp/cve_wp_login.txt
curl -s   "http://$TARGET/readme.html" -o /tmp/cve_wp_readme.html
grep -iE 'version' /tmp/cve_wp_readme.html | head -5

# WordPress plugin enumeration (preferred: wpscan)
wpscan --url "http://$TARGET/" --enumerate p,t,u --no-banner --random-user-agent \
  -o /tmp/cve_wpscan.txt 2>&1

# Manual plugin readme sweep (fallback when wpscan is unavailable)
for plugin in contact-form-7 woocommerce elementor yoast-seo akismet jetpack \
              wp-super-cache w3-total-cache wordfence all-in-one-seo-pack \
              wpforms-lite duplicator updraftplus classic-editor really-simple-ssl \
              wp-mail-smtp redirection wp-statistics polylang loginizer \
              simple-membership easy-wp-smtp mainwp-child seo-by-rank-math \
              wp-fastest-cache litespeed-cache autoptimize wp-optimize \
              advanced-custom-fields better-wp-security; do
    code=$(curl -s -o /dev/null -w '%{http_code}' \
        "http://$TARGET/wp-content/plugins/${plugin}/readme.txt")
    if [ "$code" = "200" ]; then
        ver=$(curl -s "http://$TARGET/wp-content/plugins/${plugin}/readme.txt" \
              | grep -iE 'stable tag|^version' | head -1)
        echo "plugin=$plugin version=$ver"
    fi
done | tee /tmp/cve_wp_plugins.txt

# Joomla / Drupal
curl -s "http://$TARGET/administrator/manifests/files/joomla.xml" -o /tmp/cve_joomla.xml
curl -s "http://$TARGET/CHANGELOG.txt" -o /tmp/cve_drupal_changelog.txt
```

**Output discipline**: at the end of Step 1 you MUST have at least one `<software>@<version>` pair (e.g. `wordpress@5.7.1`, `contact-form-7@5.1.6`, `apache-struts@2.5.16`). If you don't, fingerprinting failed — see the Decision Tree below.

## Step 2 — CVE identification: MANDATORY tool sequence

The exploit agent has two registered tools you MUST call in this order. Do NOT skip to manual web searches; the tools are pre-wired to fast CVE databases.

```text
# Pattern 1: single product fingerprint
cve_lookup("wordpress 5.7.1")
# → returns: list of CVE IDs ranked by relevance/severity

# Pattern 2: plugin / library fingerprint
cve_lookup("contact-form-7 5.1.6")
# → returns: plugin-specific CVE IDs

# Pattern 3: framework + version
cve_lookup("apache struts 2.5.16")
# → returns: e.g. CVE-2018-11776, CVE-2017-5638
```

For EACH candidate CVE returned, immediately call `cve_poc_lookup` to retrieve PoC URLs (github.com/trickest/cve, exploit-db, packetstorm, etc.):

```text
cve_poc_lookup("CVE-2018-11776")
# → returns: github.com/trickest/cve/blob/main/2018/CVE-2018-11776.md
#            https://www.exploit-db.com/exploits/45260
```

**Hard rule**: if you load this skill and do NOT invoke `cve_lookup` before the first exploit attempt, you are wasting the dispatch. The free-form web search fallback is slower and produces stale leads. Call the tool first.

## Step 3 — PoC adaptation

After `cve_poc_lookup` returns URLs, fetch the PoC to disk and adapt it. Three concrete patterns:

### Pattern A — curl one-shot exploit endpoint

For CVEs that are a single HTTP request (most WordPress/Joomla auth-bypass and SSRF CVEs):

```bash
# Sanity-check the PoC matches the fingerprinted version BEFORE firing
curl -s "https://raw.githubusercontent.com/trickest/cve/main/2018/CVE-2018-11776.md" \
  -o /tmp/cve_poc.md
grep -iE 'affected|version|tested on' /tmp/cve_poc.md | head -10
# Confirm the version in the PoC overlaps the target's fingerprinted version.

# Fire the adapted exploit (replace TARGET URL, OS command, output path)
curl -s -X POST "http://$TARGET/<VULNERABLE_ENDPOINT>" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "<PARAM>=<PAYLOAD>" \
  -o /tmp/cve_exploit_out.txt
head -50 /tmp/cve_exploit_out.txt
```

### Pattern B — python PoC script

For CVEs distributed as a Python script (Spring4Shell, Log4Shell helpers, ProxyShell):

```bash
# Fetch script to disk — never pipe untrusted code into bash directly
wget -q "https://raw.githubusercontent.com/<user>/<repo>/main/poc.py" -O /tmp/cve_poc.py
head -40 /tmp/cve_poc.py    # sanity-read the script

# Identify and replace placeholders (TARGET URL, CMD, callback host)
sed -i "s|http://target|http://$TARGET|g" /tmp/cve_poc.py
python3 /tmp/cve_poc.py --target "http://$TARGET" --cmd 'id' > /tmp/cve_poc_run.txt 2>&1
head -50 /tmp/cve_poc_run.txt
```

### Pattern C — Metasploit module reference

If `cve_poc_lookup` returns a Metasploit module name (e.g. `exploit/multi/http/struts2_content_type_ognl`), translate the module into a curl-equivalent rather than launching `msfconsole` (msfconsole is heavy and breaks the bash-output budget). Read the module's source via the module URL, extract the HTTP request it sends, and reproduce with curl. Document the module name in `exploit/PIVOT.md` for traceability.

**Version sanity-check is MANDATORY**: a PoC for `Struts 2.3.x` typically does NOT fire on `Struts 2.5.x`. If versions mismatch, fall back to the next CVE candidate from Step 2 rather than burning the dispatch on a guaranteed-fail attempt.

## Step 4 — Post-exploit harvest

Once RCE is achieved through the CVE, load `command-injection.md` and run its "Credential/Secret Extraction After RCE Confirmed" single-call sweep — that is the canonical generic post-RCE harvest (`/etc/passwd`, `.env`, configs, SSH keys, secret/cred/token files).

If the engagement is a CTF/benchmark (`BENCHMARK_MODE=1`), additionally load `/skills/benchmark/SKILL.md` for flag-path conventions. Generic CVE methodology never assumes CTF-specific paths.

## Step 5 — Decision tree

```
CVE skill loaded?
├── Fingerprinting yielded <software>@<version> → cve_lookup(<software> <version>)
│   ├── cve_lookup returned >=1 CVE → for each, cve_poc_lookup(<CVE-ID>)
│   │   ├── PoC version matches target → adapt (Pattern A/B/C) and fire
│   │   ├── PoC requires authentication → first check `default_credentials` tag,
│   │   │    try admin/admin, admin/password, root/root, then login-form recon
│   │   └── PoC fired → on RCE, run Step 4 post-exploit harvest
│   └── cve_lookup returned 0 CVEs → check one level deeper:
│       ├── WordPress core OK → enumerate plugins/themes (Step 1 wpscan/readme sweep)
│       │     then cve_lookup("<plugin> <version>")
│       └── Framework OK → check bundled libraries / dependencies
│             (e.g. Spring app w/ vulnerable log4j → cve_lookup("log4j 2.14"))
└── Fingerprinting FAILED (no version exposed)
    ├── Pivot to attack-class probes from recon SUMMARY.md tags:
    │     sqli.md, ssti.md, lfi.md, command-injection.md
    └── Write exploit/PIVOT.md noting "no version banner — CVE path exhausted"
```

## Step 6 — Pacing rule (3-strike, cross-CVE)

Same payload-class 3-strike rule applies, **at the CVE level**:

- If 3 candidate CVEs from `cve_lookup` all fail to exploit (version mismatch, patched endpoint, auth required without creds, or PoC returns no useful output), pivot to a DIFFERENT attack class identified during recon.
- "Same class" at this skill's level = same CVE family on the same product. Three Struts RCE CVEs against the same Struts service is ONE class — after 3 strikes, pivot to sqli/ssti/lfi against the broader app rather than searching for a 4th Struts CVE.
- A CVE that returns "endpoint exists but no command output" is a partial-strike: try Pattern B (python PoC) or out-of-band exfil (see `command-injection.md` Blind Exfiltration) before declaring strike.

After exhausting 3 CVE candidates: the version is either patched in-place or the product surface is hardened. Write `exploit/PIVOT.md` documenting (a) the 3 CVEs tried, (b) why each failed (version, auth, no-output), (c) the next attack class to attempt from recon's tag list.

## Cross-skill loading

- For RCE-class CVEs, after firing the exploit, load `command-injection.md` for output-extraction and blind-exfil patterns.
- For SQLi-class CVEs (e.g. CVE-2019-7139, CVE-2020-25213), load `sqli.md` / `blind-sqli.md` after the CVE confirms the injection point.
- For LFI-class CVEs (e.g. CVE-2019-9978, CVE-2021-41773), load `lfi.md` for wrapper escalation.
- For deserialization CVEs (Spring4Shell, ApacheCommons), load `deserialization.md` for payload generation.

The CVE skill is the **entry**; the attack-class skill is the **continuation** once the injection primitive is confirmed.
