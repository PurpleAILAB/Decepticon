"""Unit tests for the DNS subdomain-takeover verifier (offline-only).

All network hops (DoH resolution, live HTTP body fetch, registration
availability probe) are mocked, so these tests never touch the wire.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from decepticon.tools.research import dns_takeover
from decepticon.tools.research.dns_takeover import (
    Fingerprint,
    _classify_cname,
    _extract_records,
    _is_nxdomain,
    _match_fingerprint,
    dns_takeover_verifier,
)

# ── DoH payload builders ─────────────────────────────────────────────────


def _answer(name: str, rtype: str, data: str) -> dict[str, Any]:
    return {"name": name, "type": dns_takeover.DNS_TYPE[rtype], "TTL": 300, "data": data}


def _doh(answers: list[dict[str, Any]] | None = None, status: int = 0) -> dict[str, Any]:
    return {"Status": status, "Answer": answers or []}


def _nxdomain() -> dict[str, Any]:
    return {"Status": dns_takeover.NXDOMAIN_STATUS, "Answer": []}


# ── Pure parsing helpers ─────────────────────────────────────────────────


class TestExtractRecords:
    def test_extracts_matching_type_and_strips_trailing_dot(self) -> None:
        doh = _doh([_answer("x.com", "CNAME", "foo.github.io.")])
        assert _extract_records(doh, "CNAME") == ["foo.github.io"]

    def test_filters_by_record_type(self) -> None:
        doh = _doh(
            [
                _answer("x.com", "CNAME", "foo.github.io."),
                _answer("x.com", "A", "1.2.3.4"),
            ]
        )
        assert _extract_records(doh, "A") == ["1.2.3.4"]
        assert _extract_records(doh, "CNAME") == ["foo.github.io"]

    def test_strips_txt_quotes(self) -> None:
        doh = _doh([_answer("x.com", "TXT", '"v=spf1 -all"')])
        assert _extract_records(doh, "TXT") == ["v=spf1 -all"]

    def test_empty_envelope(self) -> None:
        assert _extract_records({}, "CNAME") == []
        assert _extract_records(_doh([]), "NS") == []


class TestNxdomain:
    def test_status_three_is_nxdomain(self) -> None:
        assert _is_nxdomain(_nxdomain()) is True

    def test_status_zero_is_not(self) -> None:
        assert _is_nxdomain(_doh()) is False

    def test_missing_status(self) -> None:
        assert _is_nxdomain({}) is False


class TestMatchFingerprint:
    def test_matches_s3_case_insensitively(self) -> None:
        fp = _match_fingerprint("MyBucket.S3.amazonaws.com")
        assert fp is not None
        assert fp.service == "aws-s3"

    def test_matches_github_pages(self) -> None:
        fp = _match_fingerprint("org.github.io")
        assert fp is not None and fp.service == "github-pages"

    def test_no_match_for_unknown_cdn(self) -> None:
        assert _match_fingerprint("legit.cloudfront.net") is None


class TestClassifyCname:
    fp = Fingerprint(
        service="aws-s3",
        cname_patterns=("s3.amazonaws.com",),
        signatures=("NoSuchBucket",),
    )

    def test_live_signature_is_confirmed(self) -> None:
        body = "<Error><Code>NoSuchBucket</Code></Error>"
        assert _classify_cname(self.fp, body, claimable=None) == "confirmed-takeover"

    def test_orphaned_resource_is_likely(self) -> None:
        assert _classify_cname(self.fp, "", claimable=True) == "likely-takeover"

    def test_owned_resource_is_secure(self) -> None:
        # False-positive mitigation: backing resource still resolves.
        assert _classify_cname(self.fp, "", claimable=False) == "secure"

    def test_indeterminate_is_manual_review(self) -> None:
        assert _classify_cname(self.fp, "", claimable=None) == "manual-review"

    def test_non_nxdomain_service_orphan_is_manual_review(self) -> None:
        fastly = Fingerprint(
            service="fastly",
            cname_patterns=("fastly.net",),
            signatures=("Fastly error: unknown domain",),
            nxdomain_is_takeover=False,
        )
        assert _classify_cname(fastly, "", claimable=True) == "manual-review"


# ── _resource_claimable (active registration probe) ──────────────────────


class TestResourceClaimable:
    def _run(self, doh_return: dict[str, Any]) -> bool | None:
        async def _go() -> bool | None:
            with patch.object(dns_takeover, "_doh_query", new_callable=AsyncMock) as q:
                q.return_value = doh_return
                return await dns_takeover._resource_claimable(AsyncMock(), "foo.s3.amazonaws.com")

        return asyncio.run(_go())

    def test_nxdomain_target_is_claimable(self) -> None:
        assert self._run(_nxdomain()) is True

    def test_resolving_target_is_owned(self) -> None:
        assert self._run(_doh([_answer("foo", "A", "52.0.0.1")])) is False

    def test_resolver_error_is_indeterminate(self) -> None:
        assert self._run({}) is None


# ── _analyze_domain end-to-end (helpers mocked) ──────────────────────────


def _doh_side_effect(mapping: dict[str, dict[str, Any]]):
    async def _fn(_client: Any, _name: str, rtype: str) -> dict[str, Any]:
        return mapping.get(rtype, _doh([]))

    return _fn


class TestAnalyzeDomain:
    def test_confirmed_takeover_with_live_signature(self) -> None:
        mapping = {
            "CNAME": _doh([_answer("t.x.com", "CNAME", "victim.s3.amazonaws.com.")]),
            "NS": _doh([]),
            "MX": _doh([]),
            "TXT": _doh([]),
        }

        async def _go() -> dict[str, Any]:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_fetch_http_body", new_callable=AsyncMock) as body,
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                body.return_value = "<Code>NoSuchBucket</Code>"
                claim.return_value = True
                return await dns_takeover._analyze_domain(AsyncMock(), "t.x.com")

        report = asyncio.run(_go())
        assert report["verdict"] == "confirmed-takeover"
        assert report["cname_pointers"] == ["victim.s3.amazonaws.com"]
        assert report["records"]["cname"] == ["victim.s3.amazonaws.com"]
        assert report["findings"][0]["service"] == "aws-s3"
        assert report["findings"][0]["signature_matched"] is True

    def test_likely_takeover_dangling_no_signature(self) -> None:
        mapping = {
            "CNAME": _doh([_answer("t.x.com", "CNAME", "ghost.github.io.")]),
        }

        async def _go() -> dict[str, Any]:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_fetch_http_body", new_callable=AsyncMock) as body,
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                body.return_value = ""
                claim.return_value = True
                return await dns_takeover._analyze_domain(AsyncMock(), "t.x.com")

        report = asyncio.run(_go())
        assert report["verdict"] == "likely-takeover"
        assert report["findings"][0]["claimable"] is True

    def test_false_positive_suppressed_when_resource_owned(self) -> None:
        mapping = {
            "CNAME": _doh([_answer("t.x.com", "CNAME", "owned.s3.amazonaws.com.")]),
        }

        async def _go() -> dict[str, Any]:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_fetch_http_body", new_callable=AsyncMock) as body,
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                body.return_value = "<html>real site content</html>"
                claim.return_value = False
                return await dns_takeover._analyze_domain(AsyncMock(), "t.x.com")

        report = asyncio.run(_go())
        assert report["verdict"] == "secure"
        assert report["findings"][0]["verdict"] == "secure"

    def test_no_fingerprint_match_is_secure_with_no_findings(self) -> None:
        mapping = {
            "CNAME": _doh([_answer("t.x.com", "CNAME", "legit.cloudfront.net.")]),
            "MX": _doh([_answer("t.x.com", "MX", "10 mail.x.com.")]),
            "TXT": _doh([_answer("t.x.com", "TXT", '"v=spf1 -all"')]),
        }

        async def _go() -> dict[str, Any]:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_fetch_http_body", new_callable=AsyncMock) as body,
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                body.return_value = ""
                claim.return_value = False
                return await dns_takeover._analyze_domain(AsyncMock(), "t.x.com")

        report = asyncio.run(_go())
        assert report["verdict"] == "secure"
        assert report["findings"] == []
        assert report["records"]["mx"] == ["10 mail.x.com"]
        assert report["records"]["txt"] == ["v=spf1 -all"]

    def test_expired_nameserver_delegation(self) -> None:
        mapping = {
            "NS": _doh([_answer("x.com", "NS", "ns1.deadhost.com.")]),
        }

        async def _go() -> dict[str, Any]:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                claim.return_value = True
                return await dns_takeover._analyze_domain(AsyncMock(), "x.com")

        report = asyncio.run(_go())
        assert report["verdict"] == "likely-takeover"
        ns_finding = report["findings"][0]
        assert ns_finding["type"] == "NS"
        assert ns_finding["record"] == "ns1.deadhost.com"

    def test_owned_nameserver_is_secure(self) -> None:
        mapping = {"NS": _doh([_answer("x.com", "NS", "ns1.livehost.com.")])}

        async def _go() -> dict[str, Any]:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                claim.return_value = False
                return await dns_takeover._analyze_domain(AsyncMock(), "x.com")

        report = asyncio.run(_go())
        assert report["verdict"] == "secure"
        assert report["findings"] == []


# ── @tool surface ────────────────────────────────────────────────────────


class TestToolSurface:
    def test_empty_domain_returns_error(self) -> None:
        result = json.loads(asyncio.run(dns_takeover_verifier.ainvoke({"domain": "   "})))
        assert result["error"] == "empty domain"

    def test_tool_returns_json_report(self) -> None:
        mapping = {
            "CNAME": _doh([_answer("t.x.com", "CNAME", "victim.herokuapp.com.")]),
        }

        async def _go() -> str:
            with (
                patch.object(dns_takeover, "_doh_query", side_effect=_doh_side_effect(mapping)),
                patch.object(dns_takeover, "_fetch_http_body", new_callable=AsyncMock) as body,
                patch.object(dns_takeover, "_resource_claimable", new_callable=AsyncMock) as claim,
            ):
                body.return_value = "No such app"
                claim.return_value = True
                return await dns_takeover_verifier.ainvoke({"domain": "T.X.com."})

        report = json.loads(asyncio.run(_go()))
        # Domain is normalised (lower-cased, trailing dot trimmed).
        assert report["domain"] == "t.x.com"
        assert report["verdict"] == "confirmed-takeover"
        assert report["findings"][0]["service"] == "heroku"

    def test_registered_in_research_tools(self) -> None:
        from decepticon.tools.research.tools import RESEARCH_TOOLS

        names = {t.name for t in RESEARCH_TOOLS}
        assert "dns_takeover_verifier" in names


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
