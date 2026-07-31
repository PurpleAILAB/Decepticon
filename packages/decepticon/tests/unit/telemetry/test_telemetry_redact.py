"""Tests for decepticon.telemetry.redact — the identifier masking engine.

Safety-critical: the whole research corpus depends on these never leaking a real
target. The corpus is a realistic reasoning blob; the assertion is twofold —
NOTHING identifying survives, and the reasoning STRUCTURE (stable placeholders)
does survive.
"""

from __future__ import annotations

import json

from decepticon.telemetry.redact import Redactor


def test_stable_placeholders_preserve_reasoning() -> None:
    r = Redactor()
    out = r.redact("scan 10.0.0.5, then exploit 10.0.0.5, pivot 10.0.0.5 to 10.0.0.6")
    assert out.count("<IP_1>") == 3  # same IP → same placeholder across the trajectory
    assert "<IP_2>" in out
    assert "10.0.0.5" not in out and "10.0.0.6" not in out


def test_no_leak_on_realistic_blob() -> None:
    r = Redactor(known=["DC01"])
    blob = (
        "Objective: pwn DC01. Recon shows 192.168.1.10 running SMB and admin.corp.local. "
        "Found creds svc-sql:Wint3r!2024 in config. Kerberoast DC01, DCSync from 192.168.1.10. "
        "Token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4abcd."
    )
    out = r.redact(blob)
    for secret in [
        "DC01",
        "192.168.1.10",
        "admin.corp.local",
        "Wint3r!2024",
        "svc-sql:Wint3r",
        "eyJhbGci",
    ]:
        assert secret not in out, f"LEAK: {secret}"
    assert out.count("<IP_1>") == 2  # the repeated host stays coherent


def test_known_targets_masked_with_certainty() -> None:
    # A bare hostname with no TLD regex can't catch — `known` covers it.
    r = Redactor(known=["dc01", "fileserver"])
    out = r.redact("compromise dc01 then fileserver")
    assert "dc01" not in out and "fileserver" not in out


def test_add_known_closes_the_detector_gap() -> None:
    # Without a known list, a bare NetBIOS-style host LEAKS (no detector catches it).
    leaky = Redactor()
    assert "WIN-A8F3K2" in leaky.redact("pivot to WIN-A8F3K2")
    # Feeding the RoE target masks it with certainty.
    r = Redactor()
    r.add_known(["WIN-A8F3K2", "dc01"])
    out = r.redact("pivot to WIN-A8F3K2, then dc01")
    assert "WIN-A8F3K2" not in out and "dc01" not in out
    assert "<HOST_1>" in out and "<HOST_2>" in out


def test_does_not_over_mask_harmless_text() -> None:
    r = Redactor()
    keep = "connect web:8080 set mode:fast decepticon v1.2.3 x86_64 ran T1190 CWE-89 step 7"
    assert r.redact(keep) == keep  # ports, key:value, versions, technique ids survive


def test_redact_obj_recurses() -> None:
    r = Redactor()
    obj = {"reasoning": "hit 10.0.0.5", "steps": ["scan 10.0.0.5", {"note": "creds a:B@d2!"}]}
    out = r.redact_obj(obj)
    blob = json.dumps(out)
    assert "10.0.0.5" not in blob and "B@d2" not in blob
    assert "<IP_1>" in blob  # same IP stable across nested fields


def test_plain_credential_pairs_are_masked_value_only() -> None:
    """`login:bob senha:123456` shipped in the clear before this.

    `_CRED_SPECIAL` only fires when the password carries a special character and
    `_CRED_AT` only on `user:pass@host`, so the most common written form passed
    straight through both the masker and the Tier-C scanner.
    """
    from decepticon.telemetry.redact import Redactor
    from decepticon.telemetry.sanitizer import scan_tier_c

    out = Redactor().redact("hackeia http://x login:penisduro2 senha:123456")
    assert "penisduro2" not in out and "123456" not in out
    # The keyword survives so the reasoning still reads as a credential step.
    assert "login:<CRED_" in out and "senha:<CRED_" in out
    assert scan_tier_c(out) is None

    assert "Lotte@1234567" not in Redactor().redact("pass là Lotte@1234567")


def test_prose_is_not_mistaken_for_a_credential() -> None:
    from decepticon.telemetry.redact import Redactor

    text = "the user: the attacker had already moved on"
    assert Redactor().redact(text) == text


def test_dotted_code_is_neither_masked_nor_dropped() -> None:
    """Measured: 1,697 of 7,990 masked turns carried a mangled `<DOMAIN_n>(`.

    `module.function()` is not a host. The masker must leave it, and the Tier-C
    scanner must agree — otherwise the step is dropped whole instead of masked.
    """
    from decepticon.telemetry.redact import Redactor
    from decepticon.telemetry.sanitizer import scan_tier_c

    for code in (
        "python3 -c 'import os; print(os.uname().nodename)'",
        "GraphDatabase.driver('bolt://neo4j:7687')",
    ):
        out = Redactor().redact(code)
        assert out == code, f"code was mangled: {out}"
        assert scan_tier_c(out) is None, "masker keeps it but the scanner drops it"

    # A real bare host is still masked, and still caught if it somehow is not.
    assert Redactor().redact("pivot to app.corp.internal") == "pivot to <DOMAIN_1>"
    assert scan_tier_c("pivot to app.corp.internal") is not None


def test_credentials_passed_as_command_line_flags_are_masked() -> None:
    """Operators paste whole command lines; no key:value detector sees a flag.

    Observed leaking verbatim from a real engagement:
    ``nxc smb <ip> -u Administrator -p 'Ujmqaz5055'``.
    """
    from decepticon.telemetry.redact import Redactor

    out = Redactor().redact("nxc smb 10.0.0.5 -p 'Ujmqaz5055' --local-auth")
    assert "Ujmqaz5055" not in out and "<CRED_" in out
    assert "sshpass -p <CRED_1>" in Redactor().redact("sshpass -p Hunter2 ssh a@b")
    # `-u` only in its credential form.
    assert "s3cret" not in Redactor().redact("curl -u admin:s3cret https://x")


def test_port_flags_are_not_mistaken_for_passwords() -> None:
    """`-p` is nmap's port flag — the most-run tool in the corpus."""
    from decepticon.telemetry.redact import Redactor

    for cmd in ("nmap -p 80,443 host", "nmap -p- -T4 host", "nmap -p 1-65535 host"):
        assert Redactor().redact(cmd) == cmd, cmd
    # `-u` is heavily overloaded and must stay untouched without a colon.
    assert Redactor().redact("cat f | sort -u") == "cat f | sort -u"
    assert Redactor().redact("docker run -u 1000 img") == "docker run -u 1000 img"


def test_ip_glued_to_a_label_is_masked() -> None:
    """`\\b` is not a boundary between a letter and a digit.

    ``ESXI10.10.0.95`` reached production unmasked because both the maintained
    detector and the Tier-C scanner anchor on a word boundary.
    """
    from decepticon.telemetry.redact import Redactor
    from decepticon.telemetry.sanitizer import scan_tier_c

    out = Redactor().redact("ESXI10.10.0.95 and veeam 10.10.0.51")
    assert "10.10.0.95" not in out and "10.10.0.51" not in out
    assert scan_tier_c(out) is None
    # A longer dotted number is never sliced in half.
    assert Redactor().redact("version 1.2.3 build 4") == "version 1.2.3 build 4"


def test_wall_clock_time_is_not_an_ipv6_address() -> None:
    """`21:35:00` is three colon-separated groups — so was every timestamp.

    Found in the exported corpus as `"saved_at": "2026-07-21T21:<CRED_1>:00"`.
    Tool output is full of timestamps, so this corrupted text at scale.
    """
    from decepticon.telemetry.redact import Redactor
    from decepticon.telemetry.sanitizer import scan_tier_c

    for text in ('"saved_at": "2026-07-21T21:35:00"', "completed at 21:35:00 UTC"):
        assert Redactor().redact(text) == text, text
        assert scan_tier_c(text) is None, text

    # A real address is still masked.
    v6 = "2001:db8:85a3:8d3:1319:8a2e:370:7348"
    assert v6 not in Redactor().redact(f"pivot via {v6}")
