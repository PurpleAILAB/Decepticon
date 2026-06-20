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
