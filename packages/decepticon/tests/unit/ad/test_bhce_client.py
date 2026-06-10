"""Unit tests for the BHCE v9.2.2 REST client.

The signature test vectors are NOT computed by re-running our own
algorithm against itself.  They were extracted from a verbatim
``crypto/hmac`` reproduction of BHCE's ``NewRequestSignature``
(``cmd/api/src/api/signature.go:97-145``, commit ``1a7b3df``) using
``go run`` — see /tmp/bhce-sign-vector/main.go in dev notes.  Pinning
the Go-generated base64 here gives us byte-precision compatibility
with the BHCE server-side validator.
"""

from __future__ import annotations

from decepticon.tools.ad.bhce_client import (
    BHCEClient,
    BHCEConfigError,
    sign_request,
)

# ── HMAC 3-chain reference vectors (Go-generated, do not edit) ──────


def test_sign_empty_get_self_matches_go_reference() -> None:
    headers = sign_request(
        token_id="my-id",
        token_secret="test-secret-aaaa",
        method="GET",
        url="http://bhce.local/api/v2/self",
        body=b"",
        request_date="2026-06-05T07:00:00Z",
    )
    assert headers["Signature"] == "Ppy6aC4h43xQOxf9TwE/wPFnFU5oU/imtIIZXI3m0NI="
    assert headers["Authorization"] == "bhesignature my-id"
    assert headers["RequestDate"] == "2026-06-05T07:00:00Z"


def test_sign_post_cypher_with_offset_tz_matches_go_reference() -> None:
    body = b'{"query":"MATCH (n) RETURN n LIMIT 1","include_properties":true}'
    headers = sign_request(
        token_id="id-2",
        token_secret="test-secret-bbbb",
        method="POST",
        url="http://bhce.local/api/v2/graphs/cypher",
        body=body,
        request_date="2026-06-05T07:00:00+09:00",
    )
    assert headers["Signature"] == "9G0Uf1XQ5h0uKg0ebv/HkVMJyWQf9wkRlxltAZfn4c4="


def test_sign_post_empty_body_negative_offset_matches_go_reference() -> None:
    headers = sign_request(
        token_id="id-3",
        token_secret="another-secret",
        method="POST",
        url="http://bhce.local/api/v2/file-upload/42/end",
        body=b"",
        request_date="2026-01-15T23:59:59-05:00",
    )
    assert headers["Signature"] == "CPaTRCh7gZf+z0hsYRMV8CHDjIKvIXnl0kzmKVcUjuA="


# ── Behavioural contracts on the sign_request helper ────────────────


def test_sign_includes_query_string_in_signature() -> None:
    """BHCE's *server-side* verifier feeds ``request.RequestURI`` —
    path + query — into the signature (``cmd/api/src/api/auth.go:355``),
    even though its Go *client* signs only ``request.URL.Path``
    (``signature.go:160``).  We match the server because that is what
    decides accept/reject.  Verified empirically against the live
    v9.2.2 sidecar on the paginated ``GET /api/v2/file-upload?skip=…``
    poll path (signature mismatched when we stripped query, matched
    when we included it).
    """
    without_query = sign_request(
        "id", "s", "GET", "http://h/api/v2/self", b"", request_date="2026-06-05T07:00:00Z"
    )["Signature"]
    with_query = sign_request(
        "id",
        "s",
        "GET",
        "http://h/api/v2/self?a=1&b=2",
        b"",
        request_date="2026-06-05T07:00:00Z",
    )["Signature"]
    assert without_query != with_query


def test_sign_truncates_datetime_to_hour_for_signature_only() -> None:
    """Minute / second changes within the same hour produce the same
    signature (per ``signature.go:123`` ``datetime[:13]``), but the
    ``RequestDate`` header carries the **full** datetime."""
    h1 = sign_request("id", "s", "GET", "http://h/p", b"", request_date="2026-06-05T07:00:00Z")
    h2 = sign_request("id", "s", "GET", "http://h/p", b"", request_date="2026-06-05T07:59:59Z")
    assert h1["Signature"] == h2["Signature"]
    assert h1["RequestDate"] != h2["RequestDate"]


def test_sign_changes_when_hour_rolls() -> None:
    """Crossing the hour boundary changes the DateKey and so the sig."""
    h1 = sign_request("id", "s", "GET", "http://h/p", b"", request_date="2026-06-05T07:59:59Z")
    h2 = sign_request("id", "s", "GET", "http://h/p", b"", request_date="2026-06-05T08:00:00Z")
    assert h1["Signature"] != h2["Signature"]


def test_sign_body_changes_signature() -> None:
    h1 = sign_request("id", "s", "POST", "http://h/p", b"{}", request_date="2026-06-05T07:00:00Z")
    h2 = sign_request(
        "id", "s", "POST", "http://h/p", b'{"a":1}', request_date="2026-06-05T07:00:00Z"
    )
    assert h1["Signature"] != h2["Signature"]


# ── Client wiring (env / errors) ────────────────────────────────────


def test_from_env_requires_url(monkeypatch) -> None:
    monkeypatch.delenv("BHCE_URL", raising=False)
    try:
        BHCEClient.from_env()
    except BHCEConfigError as exc:
        assert "BHCE_URL" in str(exc)
    else:
        raise AssertionError("BHCEConfigError not raised on missing BHCE_URL")


def test_from_env_invalid_timeout(monkeypatch) -> None:
    monkeypatch.setenv("BHCE_URL", "http://bhce.local:8080")
    monkeypatch.setenv("BHCE_TIMEOUT", "not-a-number")
    try:
        BHCEClient.from_env()
    except BHCEConfigError as exc:
        assert "BHCE_TIMEOUT" in str(exc)
    else:
        raise AssertionError("BHCEConfigError not raised on bad BHCE_TIMEOUT")


def test_signed_call_without_token_raises(monkeypatch) -> None:
    monkeypatch.setenv("BHCE_URL", "http://bhce.local:8080")
    monkeypatch.delenv("BHCE_TOKEN_ID", raising=False)
    monkeypatch.delenv("BHCE_TOKEN_KEY", raising=False)
    client = BHCEClient.from_env()
    try:
        client.get_self()
    except BHCEConfigError as exc:
        assert "BHCE_TOKEN" in str(exc)
    else:
        raise AssertionError("BHCEConfigError not raised on missing token")
    finally:
        client.close()
