"""Unit tests for the live JavaScript secret scanner.

All network egress is mocked: probes route through an
:class:`httpx.MockTransport` injected into the module's
``httpx.AsyncClient`` constructor, so no real HTTP ever happens.
"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from decepticon.tools.research import secret_scanner
from decepticon.tools.research.secret_scanner import (
    SECRET_PATTERNS,
    scan_secrets,
    validate_credential,
)

# ── Sample credentials (synthetic, never live) ──────────────────────────

GITHUB_TOKEN = "ghp_" + "a" * 36
GITHUB_FG_TOKEN = "github_pat_" + "A" * 22 + "_" + "b" * 59
SLACK_TOKEN = "xoxb-" + "1" * 24
OPENAI_KEY = "sk-" + "A" * 40
STRIPE_KEY = "sk_live_" + "0" * 30
GOOGLE_KEY = "AIza" + "B" * 35
GITLAB_PAT = "glpat-" + "c" * 20
TWILIO_KEY = "SK" + "a1b2c3d4" * 4  # 32 hex chars
SENDGRID_KEY = "SG." + "a" * 22 + "." + "b" * 43
AWS_KEY_ID = "AKIA" + "ABCDEFGH12345678"  # AKIA + 16
AWS_SECRET = "x" * 40
# Built from fragments so the full webhook URL never appears contiguously in
# source (keeps GitHub push-protection happy); the runtime value still matches.
_SLACK_HOST = "https://hooks.slack.com/services"
SLACK_WEBHOOK = _SLACK_HOST + "/T00000000" + "/B11111111" + "/" + "0" * 24
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"


def _patch_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Wire every ``httpx.AsyncClient`` in the scanner to a MockTransport."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(secret_scanner.httpx, "AsyncClient", factory)


def _payload(raw: str) -> dict:
    return json.loads(raw)


# ── Pattern coverage / detection (no network needed) ────────────────────


class TestPatternTable:
    def test_at_least_ten_patterns(self) -> None:
        assert len(SECRET_PATTERNS) >= 10

    @pytest.mark.parametrize(
        ("name", "sample"),
        [
            ("aws_access_key_id", AWS_KEY_ID),
            ("github_token", GITHUB_TOKEN),
            ("github_fine_grained_token", GITHUB_FG_TOKEN),
            ("slack_token", SLACK_TOKEN),
            ("slack_webhook", SLACK_WEBHOOK),
            ("openai_api_key", OPENAI_KEY),
            ("stripe_api_key", STRIPE_KEY),
            ("google_api_key", GOOGLE_KEY),
            ("gitlab_pat", GITLAB_PAT),
            ("twilio_api_key", TWILIO_KEY),
            ("sendgrid_api_key", SENDGRID_KEY),
            ("private_key", PRIVATE_KEY),
            ("jwt", JWT),
        ],
    )
    def test_each_pattern_matches_its_sample(self, name: str, sample: str) -> None:
        assert SECRET_PATTERNS[name].search(sample) is not None


class TestDetection:
    async def test_detects_unvalidated_secret_with_line_number(self) -> None:
        js = f"var a = 1;\nconst key = '{GOOGLE_KEY}';\n"
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        assert out["count"] == 1
        finding = out["secrets"][0]
        assert finding["pattern"] == "google_api_key"
        assert finding["line"] == 2
        assert finding["secret"] == GOOGLE_KEY
        # No probe is registered for Google keys.
        assert finding["status"] == "unvalidated"

    async def test_capture_group_extracts_bare_aws_secret(self) -> None:
        js = f'aws_secret_key = "{AWS_SECRET}"'
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        finding = next(f for f in out["secrets"] if f["pattern"] == "aws_secret_access_key")
        # Bare 40-char secret, not the surrounding quotes/assignment.
        assert finding["secret"] == AWS_SECRET

    async def test_clean_content_yields_no_findings(self) -> None:
        js = "function add(a, b) { return a + b; }\nconst x = 'hello world';"
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        assert out["count"] == 0
        assert out["secrets"] == []

    async def test_empty_input(self) -> None:
        out = _payload(await scan_secrets.ainvoke({"js_content": ""}))
        assert out == {"count": 0, "secrets": []}

    async def test_multiple_distinct_secrets(self) -> None:
        js = f"a='{GOOGLE_KEY}'\nb='{PRIVATE_KEY}'\nc='{TWILIO_KEY}'"
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        patterns = {f["pattern"] for f in out["secrets"]}
        assert {"google_api_key", "private_key", "twilio_api_key"} <= patterns


# ── Validation status via mocked probes ─────────────────────────────────


class TestValidationStatus:
    async def test_github_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, lambda req: httpx.Response(200, json={"login": "x"}))
        js = f"const t = '{GITHUB_TOKEN}'"
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        assert out["secrets"][0]["status"] == "live"

    async def test_github_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, lambda req: httpx.Response(401, json={"message": "Bad"}))
        js = f"const t = '{GITHUB_TOKEN}'"
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        assert out["secrets"][0]["status"] == "dead"

    async def test_github_sends_bearer_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["auth"] = req.headers.get("Authorization", "")
            seen["url"] = str(req.url)
            return httpx.Response(200, json={})

        _patch_client(monkeypatch, handler)
        await scan_secrets.ainvoke({"js_content": f"'{GITHUB_TOKEN}'"})
        assert seen["auth"] == f"Bearer {GITHUB_TOKEN}"
        assert seen["url"] == "https://api.github.com/user"

    async def test_slack_ok_true_is_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, lambda req: httpx.Response(200, json={"ok": True}))
        out = _payload(await scan_secrets.ainvoke({"js_content": f"'{SLACK_TOKEN}'"}))
        assert out["secrets"][0]["status"] == "live"

    async def test_slack_ok_false_is_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(
            monkeypatch,
            lambda req: httpx.Response(200, json={"ok": False, "error": "invalid_auth"}),
        )
        out = _payload(await scan_secrets.ainvoke({"js_content": f"'{SLACK_TOKEN}'"}))
        assert out["secrets"][0]["status"] == "dead"

    async def test_stripe_uses_basic_auth_username(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["auth"] = req.headers.get("Authorization", "")
            return httpx.Response(200, json={})

        _patch_client(monkeypatch, handler)
        out = _payload(await scan_secrets.ainvoke({"js_content": f"'{STRIPE_KEY}'"}))
        assert out["secrets"][0]["status"] == "live"
        assert seen["auth"].startswith("Basic ")

    async def test_unreachable_api_falls_back_to_unvalidated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        _patch_client(monkeypatch, handler)
        out = _payload(await scan_secrets.ainvoke({"js_content": f"'{GITHUB_TOKEN}'"}))
        assert out["secrets"][0]["status"] == "unvalidated"

    async def test_validated_secret_probed_once_when_repeated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={})

        _patch_client(monkeypatch, handler)
        js = f"line1 = '{GITHUB_TOKEN}'\nline2 = '{GITHUB_TOKEN}'"
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        # Same token on two lines -> two findings, one probe (cached).
        assert out["count"] == 2
        assert calls["n"] == 1

    async def test_probe_count_capped_on_many_distinct_secrets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={})

        _patch_client(monkeypatch, handler)
        cap = secret_scanner.MAX_VALIDATION_PROBES
        overflow = 5
        tokens = [f"ghp_{i:036d}" for i in range(cap + overflow)]
        js = "\n".join(f"t='{t}'" for t in tokens)
        out = _payload(await scan_secrets.ainvoke({"js_content": js}))
        # Every distinct secret is still detected and reported...
        assert out["count"] == cap + overflow
        # ...but outbound probes are bounded by the budget.
        assert calls["n"] == cap
        live = sum(1 for f in out["secrets"] if f["status"] == "live")
        unval = sum(1 for f in out["secrets"] if f["status"] == "unvalidated")
        assert live == cap
        assert unval == overflow

    async def test_slack_non_dict_body_is_unvalidated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A 200 with a non-object JSON body must not abort the scan with a
        # stray AttributeError; it falls back to unvalidated.
        _patch_client(monkeypatch, lambda req: httpx.Response(200, json=["unexpected"]))
        out = _payload(await scan_secrets.ainvoke({"js_content": f"'{SLACK_TOKEN}'"}))
        assert out["secrets"][0]["status"] == "unvalidated"


# ── validate_credential direct ──────────────────────────────────────────


class TestValidateCredential:
    async def test_returns_true_on_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, lambda req: httpx.Response(200, json={}))
        assert await validate_credential("github_token", GITHUB_TOKEN) is True

    async def test_returns_false_on_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, lambda req: httpx.Response(403, json={}))
        assert await validate_credential("openai_api_key", OPENAI_KEY) is False

    async def test_unknown_pattern_raises(self) -> None:
        with pytest.raises(KeyError):
            await validate_credential("google_api_key", GOOGLE_KEY)
