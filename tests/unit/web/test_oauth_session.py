"""Tests for OAuth analyser + cookie session helpers."""

from __future__ import annotations

from decepticon.tools.web.oauth import analyze_oauth_callback
from decepticon.tools.web.session import analyze_cookie, shannon_entropy


class TestOAuth:
    def test_missing_state_flagged(self) -> None:
        findings = analyze_oauth_callback("https://app.example.com/cb?code=abc")
        ids = [f.id for f in findings]
        assert "oauth.state-missing" in ids

    def test_short_low_entropy_state(self) -> None:
        findings = analyze_oauth_callback("https://app.example.com/cb?code=abc&state=aaaa")
        ids = [f.id for f in findings]
        assert "oauth.state-short" in ids

    def test_implicit_flow_flagged(self) -> None:
        findings = analyze_oauth_callback(
            "https://app.example.com/cb#access_token=xyz&state=abcd1234567890xyz",
            initial_request_url="https://auth.example.com/authorize?response_type=token&state=abcd1234567890xyz",
        )
        assert any(f.id == "oauth.implicit-flow" for f in findings)

    def test_pkce_missing_on_public_client(self) -> None:
        findings = analyze_oauth_callback(
            "https://app.example.com/cb?code=abc&state=abcdefg123456",
            initial_request_url="https://auth.example.com/authorize?response_type=code&state=abcdefg123456",
            public_client=True,
        )
        assert any(f.id == "oauth.pkce-missing" for f in findings)

    def test_state_mismatch_critical(self) -> None:
        findings = analyze_oauth_callback(
            "https://app.example.com/cb?code=abc&state=SERVER_RETURNED_abcdefghij",
            initial_request_url="https://auth.example.com/authorize?response_type=code&state=CLIENT_SENT_0123456789",
        )
        assert any(f.id == "oauth.state-mismatch" for f in findings)

    def test_wildcard_scope_flagged(self) -> None:
        findings = analyze_oauth_callback(
            "https://app.example.com/cb?code=abc&state=abcdefghij12345",
            initial_request_url="https://auth.example.com/authorize?response_type=code&scope=* admin",
        )
        assert any(f.id == "oauth.scope-wildcard" for f in findings)

    def test_traversal_in_redirect_uri(self) -> None:
        findings = analyze_oauth_callback(
            "https://app.example.com/cb?code=abc&state=abcdefghij12345",
            initial_request_url="https://auth.example.com/authorize?redirect_uri=https://app.com/..%2f..%2fevil",
        )
        assert any(f.id == "oauth.redirect-uri-traversal" for f in findings)


class TestCookie:
    def test_framework_detection(self) -> None:
        a = analyze_cookie(
            "sessionid",
            "abcdefghij1234567890abcdef",
            secure=True,
            http_only=True,
            same_site="Strict",
        )
        assert a.framework == "Django"

    def test_short_and_low_entropy(self) -> None:
        a = analyze_cookie("session", "aaaa", secure=False)
        assert any("too short" in f for f in a.findings)
        # entropy of all same char is 0
        assert a.shannon_entropy == 0.0

    def test_jwt_detection(self) -> None:
        jwt_val = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.ZGVmNDU2"
        a = analyze_cookie("session", jwt_val, secure=True, http_only=True, same_site="Strict")
        assert a.format == "jwt"
        assert any("JWT" in f for f in a.findings)

    def test_base64_json_detection(self) -> None:
        import base64
        import json as _json

        blob = base64.urlsafe_b64encode(_json.dumps({"user": "bob"}).encode()).decode().rstrip("=")
        a = analyze_cookie("app", blob, secure=True, http_only=True, same_site="Strict")
        assert a.format == "base64-json"

    def test_transport_flags(self) -> None:
        a = analyze_cookie("sessionid", "a" * 30, secure=False, http_only=False, same_site=None)
        joined = " ".join(a.findings)
        assert "Secure" in joined
        assert "HttpOnly" in joined
        assert "SameSite" in joined

    def test_hex_characters_are_counted(self) -> None:
        a = analyze_cookie(
            "session", "deadBEEF1234", secure=True, http_only=True, same_site="Strict"
        )
        assert a.char_classes["hex"] == len("deadBEEF1234")
        assert a.char_classes["lower"] == 4
        assert a.char_classes["upper"] == 4
        assert a.char_classes["digit"] == 4


def test_shannon_entropy_bounds() -> None:
    assert shannon_entropy("") == 0.0
    assert shannon_entropy("aaaa") == 0.0
    assert shannon_entropy("abcd") > 1.9  # 2.0 bits/char for 4 unique symbols
