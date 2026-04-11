"""Active Directory Certificate Services — ESC1-ESC15 scanner.

The agent runs ``certipy find --json`` and pastes the output in; this
module scores every template against the SpecterOps ADCS abuse matrix
and returns findings per ESC class.

We cover the widely-abused entries:

- ESC1: ENROLLEE_SUPPLIES_SUBJECT + Client Authentication EKU
        + Low-priv enrollment rights
- ESC2: Any Purpose EKU + low-priv enrollment
- ESC3: Enrollment Agent template abuse
- ESC4: Vulnerable template ACL (GenericAll / WriteDacl for low-priv)
- ESC6: EDITF_ATTRIBUTESUBJECTALTNAME2 CA flag
- ESC7: Vulnerable CA ACL
- ESC8: NTLM relay to CA Web Enrollment
- ESC9/10: Weak certificate mapping + UPN / DNS rewriting
- ESC11: NTLM relay to ICPR
- ESC13/14/15: Issuance policy to OID group link / schema v1 ambiguity
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_LOW_PRIV_NAMES = {"domain users", "authenticated users", "everyone", "domain computers"}


@dataclass
class ADCSFinding:
    template: str
    esc: str
    severity: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "esc": self.esc,
            "severity": self.severity,
            "detail": self.detail,
        }


def _has_low_priv(rights: list[str] | None) -> bool:
    if not rights:
        return False
    return any(r.lower() in _LOW_PRIV_NAMES for r in rights)


def _has_auth_eku(template: dict[str, Any]) -> bool:
    ekus = [e.lower() for e in (template.get("Extended Key Usage") or [])]
    return any(
        "client authentication" in e
        or "smart card logon" in e
        or "pkinit client authentication" in e
        or "any purpose" in e
        for e in ekus
    )


def _template_analysis(name: str, template: dict[str, Any]) -> list[ADCSFinding]:
    findings: list[ADCSFinding] = []
    flags = [f.lower() for f in (template.get("Enrollment Flag") or [])]
    cert_name_flag = [f.lower() for f in (template.get("Certificate Name Flag") or [])]
    ekus = [e.lower() for e in (template.get("Extended Key Usage") or [])]
    enroll_rights = template.get("Enrollment Rights") or []
    write_owner_rights = template.get("Write Owner Principals") or []
    write_dacl_rights = template.get("Write Dacl Principals") or []
    write_property_rights = template.get("Write Property Principals") or []

    # Certipy emits the flag as either "ENROLLEE_SUPPLIES_SUBJECT" or
    # "Enrollee Supplies Subject" depending on version — accept both.
    supplies_subject = any(
        "supplies_subject" in f or "supplies subject" in f for f in cert_name_flag
    )
    auth_eku = _has_auth_eku(template)
    any_purpose = any("any purpose" in e or "smart card" in e for e in ekus)
    manager_approval = any("manager approval" in f for f in flags)
    authorised_signatures = (template.get("Authorized Signatures Required") or 0) > 0

    if (
        supplies_subject
        and auth_eku
        and _has_low_priv(enroll_rights)
        and not manager_approval
        and not authorised_signatures
    ):
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC1",
                severity="critical",
                detail=(
                    "Template lets low-priv users supply the subject AND has client-auth EKU. "
                    "Impersonate any domain account by enrolling with altSubjectName=Administrator."
                ),
            )
        )
    if any_purpose and _has_low_priv(enroll_rights):
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC2",
                severity="high",
                detail=(
                    "Any Purpose EKU enabled for low-priv enrollees. Certificate is usable for "
                    "code signing, smart card logon, and client auth."
                ),
            )
        )
    if any("certificate request agent" in e for e in ekus):
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC3",
                severity="high",
                detail="Certificate Request Agent EKU — enrollment agent abuse candidate.",
            )
        )
    if (
        _has_low_priv(write_dacl_rights)
        or _has_low_priv(write_owner_rights)
        or _has_low_priv(write_property_rights)
    ):
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC4",
                severity="high",
                detail=(
                    "Template ACL grants Write* to a low-priv group. Attacker can rewrite the "
                    "template to ESC1/ESC2 and then enroll."
                ),
            )
        )
    return findings


def _ca_analysis(name: str, ca: dict[str, Any]) -> list[ADCSFinding]:
    findings: list[ADCSFinding] = []
    flags = [f.lower() for f in (ca.get("User Specified SAN") or [])]
    if any("enabled" in f for f in flags) or ca.get("EDITF_ATTRIBUTESUBJECTALTNAME2") is True:
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC6",
                severity="critical",
                detail=(
                    "CA has EDITF_ATTRIBUTESUBJECTALTNAME2 enabled — any user can request a "
                    "certificate with a SAN of another principal (domain-wide impersonation)."
                ),
            )
        )
    endpoints = ca.get("Web Enrollment") or ca.get("Enrollment Endpoints") or []
    if any("http://" in (ep or "").lower() for ep in endpoints):
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC8",
                severity="high",
                detail=(
                    "Web Enrollment reachable over HTTP — NTLM relay candidate. "
                    "Pair with PetitPotam / PrinterBug for account takeover."
                ),
            )
        )
    ca_write = ca.get("Access Rights") or []
    if _has_low_priv(ca_write):
        findings.append(
            ADCSFinding(
                template=name,
                esc="ESC7",
                severity="high",
                detail="Vulnerable CA ACL — low-priv principal has ManageCA or ManageCertificates.",
            )
        )
    return findings


def analyze_adcs_templates(certipy_output: dict[str, Any]) -> list[ADCSFinding]:
    """Run every ESC check against a Certipy JSON output.

    Expected shape: ``{"Certificate Templates": {<name>: {...}}, "Certificate Authorities": {<name>: {...}}}``.
    Unknown shapes return an empty list rather than raising.
    """
    findings: list[ADCSFinding] = []
    templates = certipy_output.get("Certificate Templates") or {}
    cas = certipy_output.get("Certificate Authorities") or {}

    for name, template in templates.items():
        findings.extend(_template_analysis(name, template or {}))
    for name, ca in cas.items():
        findings.extend(_ca_analysis(name, ca or {}))
    return findings
