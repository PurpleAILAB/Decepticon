"""Unit tests for the CVE/EPSS scoring helpers (offline-only)."""

from __future__ import annotations

from decepticon.tools.research.cve import (
    Exploitability,
    _parse_epss,
    _parse_nvd,
    rank_exploitability,
)


class TestExploitabilityScore:
    def test_high_cvss_plus_high_epss_hits_ceiling(self) -> None:
        e = Exploitability(cve_id="CVE-A", cvss=9.8, epss=0.95)
        assert e.score >= 9.8

    def test_kev_floors_at_9(self) -> None:
        e = Exploitability(cve_id="CVE-B", cvss=5.0, kev=True)
        assert e.score >= 9.0

    def test_missing_cvss_uses_neutral_baseline(self) -> None:
        e = Exploitability(cve_id="CVE-C")
        # 5.0 baseline, no adjustment
        assert 4.0 <= e.score <= 6.0

    def test_low_epss_demotes_high_cvss_below_kev(self) -> None:
        high_cvss = Exploitability(cve_id="CVE-D", cvss=7.5, epss=0.001)
        kev_floor = Exploitability(cve_id="CVE-E", cvss=5.0, kev=True)
        # KEV wins because high CVSS with near-zero EPSS is demoted
        assert kev_floor.score > high_cvss.score

    def test_score_bounded_0_to_10(self) -> None:
        e_high = Exploitability(cve_id="CVE-Z", cvss=10.0, epss=1.0, kev=True)
        e_low = Exploitability(cve_id="CVE-Y", cvss=0.0, epss=0.0)
        assert e_high.score <= 10.0
        assert e_low.score >= 0.0


class TestRanking:
    def test_rank_sorts_descending(self) -> None:
        records = [
            Exploitability(cve_id="CVE-1", cvss=5.0),
            Exploitability(cve_id="CVE-2", cvss=9.8, epss=0.9),
            Exploitability(cve_id="CVE-3", cvss=7.5, kev=True),
        ]
        ranked = rank_exploitability(records)
        assert ranked[0].cve_id == "CVE-2"
        assert ranked[1].cve_id == "CVE-3"
        assert ranked[2].cve_id == "CVE-1"

    def test_rank_stable_for_equal_scores(self) -> None:
        records = [
            Exploitability(cve_id="CVE-A", cvss=7.0),
            Exploitability(cve_id="CVE-B", cvss=7.0),
        ]
        ranked = rank_exploitability(records)
        assert {r.cve_id for r in ranked} == {"CVE-A", "CVE-B"}


class TestNVDParser:
    def test_extracts_cvss_v31(self) -> None:
        data = {
            "vulnerabilities": [
                {
                    "cve": {
                        "published": "2024-01-01T00:00:00",
                        "descriptions": [{"lang": "en", "value": "Test bug"}],
                        "metrics": {
                            "cvssMetricV31": [
                                {
                                    "cvssData": {
                                        "baseScore": 9.8,
                                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                    }
                                }
                            ]
                        },
                        "weaknesses": [{"description": [{"lang": "en", "value": "CWE-89"}]}],
                        "references": [{"url": "https://example.com/advisory"}],
                    }
                }
            ]
        }
        parsed = _parse_nvd(data)
        assert parsed["cvss"] == 9.8
        assert parsed["cvss_vector"].startswith("CVSS:3.1/")
        assert parsed["cwe"] == ["CWE-89"]
        assert parsed["summary"] == "Test bug"
        assert parsed["references"] == ["https://example.com/advisory"]

    def test_falls_back_to_v30_then_v2(self) -> None:
        data = {
            "vulnerabilities": [
                {
                    "cve": {
                        "descriptions": [],
                        "metrics": {
                            "cvssMetricV2": [
                                {
                                    "cvssData": {
                                        "baseScore": 5.0,
                                        "vectorString": "AV:N/AC:M/Au:N/C:P/I:P/A:N",
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        }
        parsed = _parse_nvd(data)
        assert parsed["cvss"] == 5.0

    def test_empty_vulns_returns_empty_record(self) -> None:
        parsed = _parse_nvd({"vulnerabilities": []})
        assert parsed["cvss"] is None
        assert parsed["cwe"] == []


class TestEPSSParser:
    def test_valid_data(self) -> None:
        parsed = _parse_epss({"data": [{"epss": "0.85", "percentile": "0.97"}]})
        assert parsed["epss"] == 0.85
        assert parsed["epss_percentile"] == 0.97

    def test_empty_data(self) -> None:
        parsed = _parse_epss({"data": []})
        assert parsed["epss"] is None

    def test_bad_float_does_not_raise(self) -> None:
        parsed = _parse_epss({"data": [{"epss": "not-a-number"}]})
        assert parsed["epss"] is None
