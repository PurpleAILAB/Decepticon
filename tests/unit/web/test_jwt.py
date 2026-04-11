"""Tests for the JWT helpers."""

from __future__ import annotations

import pytest

from decepticon.tools.web.jwt import (
    DEFAULT_WEAK_SECRETS,
    crack_hs_secret,
    forge_token,
    parse_token,
    verify_hs,
)


class TestParse:
    def test_valid_token(self) -> None:
        t = forge_token({"sub": "alice", "exp": 9999999999}, alg="HS256", secret="secret")
        parsed = parse_token(t)
        assert parsed.header.alg == "HS256"
        assert parsed.claims.sub == "alice"
        assert parsed.claims.expired is False
        assert not any("malformed" in f for f in parsed.findings)

    def test_malformed_segments(self) -> None:
        parsed = parse_token("only-one-segment")
        assert any("malformed" in f for f in parsed.findings)

    def test_alg_none_is_flagged(self) -> None:
        t = forge_token({"sub": "bob"}, alg="none")
        parsed = parse_token(t)
        assert any("alg=none" in f for f in parsed.findings)

    def test_no_exp_flagged(self) -> None:
        t = forge_token({"sub": "charlie"}, alg="HS256", secret="x")
        parsed = parse_token(t)
        assert any("no exp claim" in f for f in parsed.findings)

    def test_expired_flagged(self) -> None:
        t = forge_token({"sub": "dan", "exp": 100}, alg="HS256", secret="x")
        parsed = parse_token(t)
        assert parsed.claims.expired is True
        assert any("expired" in f for f in parsed.findings)

    def test_kid_traversal_flagged(self) -> None:
        t = forge_token(
            {"sub": "e"},
            alg="HS256",
            secret="k",
            header={"kid": "../../../etc/passwd"},
        )
        parsed = parse_token(t)
        assert any("path traversal" in f for f in parsed.findings)

    def test_jku_non_https_flagged(self) -> None:
        t = forge_token(
            {"sub": "f"},
            alg="HS256",
            secret="k",
            header={"jku": "http://evil.com/jwks"},
        )
        parsed = parse_token(t)
        assert any("jku" in f for f in parsed.findings)


class TestForgeVerify:
    @pytest.mark.parametrize("alg", ["HS256", "HS384", "HS512"])
    def test_hmac_roundtrip(self, alg: str) -> None:
        t = forge_token({"sub": "u"}, alg=alg, secret="password")
        parsed = parse_token(t)
        assert verify_hs(parsed, "password") is True
        assert verify_hs(parsed, "wrong") is False

    def test_forge_none_has_empty_signature(self) -> None:
        t = forge_token({"sub": "u"}, alg="none")
        assert t.endswith(".")  # empty signature segment

    def test_forge_unknown_alg_raises(self) -> None:
        with pytest.raises(ValueError):
            forge_token({"sub": "u"}, alg="RS256")

    def test_forge_hs_without_secret_raises(self) -> None:
        with pytest.raises(ValueError):
            forge_token({"sub": "u"}, alg="HS256")


class TestCrack:
    def test_cracks_weak_secret(self) -> None:
        t = forge_token({"sub": "u"}, alg="HS256", secret="secret")
        parsed = parse_token(t)
        assert crack_hs_secret(parsed, DEFAULT_WEAK_SECRETS) == "secret"

    def test_no_hit_returns_none(self) -> None:
        t = forge_token({"sub": "u"}, alg="HS256", secret="verysecretx!Z9")
        parsed = parse_token(t)
        assert crack_hs_secret(parsed, ["password", "admin"]) is None

    def test_returns_none_for_non_hmac(self) -> None:
        t = forge_token({"sub": "u"}, alg="none")
        parsed = parse_token(t)
        assert crack_hs_secret(parsed, ["anything"]) is None
