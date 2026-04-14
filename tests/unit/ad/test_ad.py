"""Tests for AD package: BloodHound import, Kerberos classification, ADCS, DCSync."""

from __future__ import annotations

from decepticon.tools.ad.adcs import analyze_adcs_templates
from decepticon.tools.ad.bloodhound import merge_bloodhound_json
from decepticon.tools.ad.dcsync import dcsync_candidates
from decepticon.tools.ad.kerberos import classify_hashcat_hash, parse_ticket
from decepticon.tools.research.graph import KnowledgeGraph


class TestBloodHoundIngest:
    def test_imports_users_with_aces(self) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                    "Properties": {
                        "name": "admin@corp.local",
                        "admincount": True,
                        "hasspn": True,
                    },
                    "Aces": [{"RightName": "GenericAll", "PrincipalSID": "S-1-5-21-1-1-1-1106"}],
                }
            ],
        }
        g = KnowledgeGraph()
        stats = merge_bloodhound_json(bh, g)
        assert stats.users == 1
        assert stats.edges >= 1

    def test_rejects_top_level_array(self) -> None:
        import pytest

        g = KnowledgeGraph()
        with pytest.raises(ValueError, match="top level"):
            merge_bloodhound_json("[]", g)

    def test_rejects_top_level_scalar(self) -> None:
        import pytest

        g = KnowledgeGraph()
        with pytest.raises(ValueError, match="top level"):
            merge_bloodhound_json("42", g)

    def test_rejects_invalid_json(self) -> None:
        import pytest

        g = KnowledgeGraph()
        with pytest.raises(ValueError, match="invalid JSON"):
            merge_bloodhound_json("{not json", g)

    def test_rejects_non_array_data_field(self) -> None:
        import pytest

        g = KnowledgeGraph()
        with pytest.raises(ValueError, match="'data'/'items' must be an array"):
            merge_bloodhound_json({"meta": {"type": "users"}, "data": "oops"}, g)

    def test_missing_meta_is_tolerated(self) -> None:
        # Historical behavior: meta is optional. Verify it still works
        # and doesn't crash on the new shape-check path.
        g = KnowledgeGraph()
        stats = merge_bloodhound_json(
            {
                "data": [
                    {
                        "ObjectIdentifier": "S-1-5-21-1-1-1-500",
                        "Properties": {"name": "admin@corp.local"},
                    }
                ]
            },
            g,
        )
        assert stats.users == 1

    def test_dcsync_detection(self) -> None:
        bh = {
            "meta": {"type": "users"},
            "data": [
                {
                    "ObjectIdentifier": "S-1-5-21-1-1-1-1106",
                    "Properties": {"name": "svcadmin@corp.local"},
                    "Aces": [
                        {"RightName": "GetChanges", "PrincipalSID": "S-1-5-21-1-1-1-1107"},
                        {
                            "RightName": "GetChangesAll",
                            "PrincipalSID": "S-1-5-21-1-1-1-1107",
                        },
                    ],
                }
            ],
        }
        g = KnowledgeGraph()
        merge_bloodhound_json(bh, g)
        assert len(dcsync_candidates(g)) == 1


class TestKerberos:
    def test_classifies_tgs_rc4(self) -> None:
        h = classify_hashcat_hash("$krb5tgs$23$*svc$CORP.LOCAL$http/web*$abc$def")
        assert h.kind == "tgs"
        assert h.etype == "rc4"
        assert h.hashcat_mode == 13100
        assert h.principal == "svc"
        assert h.realm == "CORP.LOCAL"

    def test_classifies_asrep_aes256(self) -> None:
        h = classify_hashcat_hash("$krb5asrep$18$user@DOMAIN:abc$def")
        assert h.kind == "asrep"
        assert h.etype == "aes256"

    def test_unknown_format(self) -> None:
        h = classify_hashcat_hash("not-a-hash")
        assert h.kind == "unknown"

    def test_parse_ticket_kirbi(self) -> None:
        # Long base64-ish blob
        t = parse_ticket("A" * 200)
        assert t.kind == "kirbi"


class TestADCS:
    def test_esc1_fires(self) -> None:
        certipy = {
            "Certificate Templates": {
                "User": {
                    "Certificate Name Flag": ["ENROLLEE_SUPPLIES_SUBJECT"],
                    "Extended Key Usage": ["Client Authentication"],
                    "Enrollment Rights": ["Domain Users"],
                    "Enrollment Flag": [],
                    "Authorized Signatures Required": 0,
                }
            },
            "Certificate Authorities": {},
        }
        findings = analyze_adcs_templates(certipy)
        assert any(f.esc == "ESC1" for f in findings)
        assert any(f.severity == "critical" for f in findings)

    def test_esc6_san_flag(self) -> None:
        certipy = {
            "Certificate Templates": {},
            "Certificate Authorities": {"CA": {"EDITF_ATTRIBUTESUBJECTALTNAME2": True}},
        }
        findings = analyze_adcs_templates(certipy)
        assert any(f.esc == "ESC6" for f in findings)

    def test_esc8_http_web_enrollment(self) -> None:
        certipy = {
            "Certificate Templates": {},
            "Certificate Authorities": {
                "CA": {"Web Enrollment": ["http://ca.corp.local/certsrv/"]}
            },
        }
        findings = analyze_adcs_templates(certipy)
        assert any(f.esc == "ESC8" for f in findings)

    def test_esc4_low_priv_write_dacl(self) -> None:
        certipy = {
            "Certificate Templates": {
                "T": {
                    "Certificate Name Flag": [],
                    "Extended Key Usage": [],
                    "Enrollment Rights": [],
                    "Write Dacl Principals": ["Domain Users"],
                    "Enrollment Flag": [],
                }
            },
            "Certificate Authorities": {},
        }
        findings = analyze_adcs_templates(certipy)
        assert any(f.esc == "ESC4" for f in findings)
