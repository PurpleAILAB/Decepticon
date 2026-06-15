from __future__ import annotations

import os

import pytest

from decepticon.cli import auth
from decepticon.cli.auth import main as auth_main
from decepticon.llm import factory
from decepticon.llm.factory import AuthInventory, AuthMethod, AuthMethodStatus

_PROVIDER_ENV_VARS = (
    *factory._API_METHOD_ENV.values(),
    *factory._OAUTH_METHOD_ENV.values(),
    *factory._LOCAL_METHOD_ENV.values(),
    "DECEPTICON_AUTH_PRIORITY",
    "DECEPTICON_HOME",
    "OLLAMA_MODEL",
    "OLLAMA_CLOUD_MODEL",
    "LMSTUDIO_MODEL",
    "LLAMACPP_MODEL",
    "CUSTOM_OPENAI_API_KEY",
    "CLAUDE_CODE_CREDENTIALS_PATH",
    "CODEX_AUTH_PATH",
    "GEMINI_TOKENS_PATH",
    "COPILOT_TOKENS_PATH",
    "GROK_TOKENS_PATH",
    "PERPLEXITY_TOKENS_PATH",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return monkeypatch


def _make_status(
    method: AuthMethod = AuthMethod.OPENAI_API,
    kind: str = "api",
    label: str = "OpenAI API",
    env_var: str = "OPENAI_API_KEY",
    configured: bool = False,
    in_priority: bool = False,
    active: bool = False,
    detail: str = "set OPENAI_API_KEY",
) -> AuthMethodStatus:
    return AuthMethodStatus(
        method=method,
        kind=kind,
        label=label,
        env_var=env_var,
        configured=configured,
        in_priority=in_priority,
        active=active,
        detail=detail,
    )


def _make_inventory(
    statuses: tuple[AuthMethodStatus, ...] = (),
    resolved_chain: tuple[AuthMethod, ...] = (),
    priority_explicit: bool = False,
) -> AuthInventory:
    return AuthInventory(
        statuses=statuses,
        resolved_chain=resolved_chain,
        priority_explicit=priority_explicit,
    )


def test_glyph_not_configured_not_active():
    assert auth._glyph(configured=False, active=False) == "·       "


def test_glyph_configured_not_active():
    assert auth._glyph(configured=True, active=False) == "✓ idle  "


def test_glyph_configured_and_active():
    assert auth._glyph(configured=True, active=True) == "✓ active"


def test_glyph_active_overrides_configured_false():
    assert auth._glyph(configured=False, active=True) == "✓ active"


def test_load_env_file_happy_path(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n# comment line\nexport FOO=bar\nQUOTED=\"qval\"\nSINGLE='sval'\nNOSEP_LINE\nPLAIN=p\n",
        encoding="utf-8",
    )
    for k in ("FOO", "QUOTED", "SINGLE", "PLAIN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("NOSEP_LINE", raising=False)
    result = auth._load_env_file(env_file)
    assert result == 4
    assert os.environ["FOO"] == "bar"
    assert os.environ["QUOTED"] == "qval"
    assert os.environ["SINGLE"] == "sval"
    assert os.environ["PLAIN"] == "p"
    assert "NOSEP_LINE" not in os.environ


def test_load_env_file_never_overrides_live_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=fromfile\nNEWKEY=new\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "live")
    monkeypatch.delenv("NEWKEY", raising=False)
    result = auth._load_env_file(env_file)
    assert result == 1
    assert os.environ["EXISTING"] == "live"
    assert os.environ["NEWKEY"] == "new"


def test_load_env_file_empty_key_guard(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("=value\nexport =x\nVALIDKEY=yes\n", encoding="utf-8")
    monkeypatch.delenv("VALIDKEY", raising=False)
    result = auth._load_env_file(env_file)
    assert result == 1
    assert "" not in os.environ


def test_load_env_file_oserror_returns_zero(tmp_path):
    missing = tmp_path / "missing.env"
    result = auth._load_env_file(missing)
    assert result == 0


def test_default_env_path_with_decepticon_home(monkeypatch, tmp_path):
    monkeypatch.setenv("DECEPTICON_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "emptyhome"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "emptyhome"))
    env_file = tmp_path / ".env"
    env_file.write_text("K=v\n", encoding="utf-8")
    result = auth._default_env_path()
    assert result == env_file


def test_default_env_path_decepticon_home_whitespace_falls_through(monkeypatch, tmp_path):
    monkeypatch.setenv("DECEPTICON_HOME", "   ")
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    decepticon_dir = fake_home / ".decepticon"
    decepticon_dir.mkdir()
    env_file = decepticon_dir / ".env"
    env_file.write_text("K=v\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    result = auth._default_env_path()
    assert result == env_file


def test_default_env_path_returns_none_when_nothing_exists(monkeypatch, tmp_path):
    monkeypatch.delenv("DECEPTICON_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    result = auth._default_env_path()
    assert result is None


def test_render_text_no_resolved_chain_shows_warning():
    statuses = (
        _make_status(
            method=AuthMethod.OPENAI_API,
            kind="api",
            label="OpenAI API",
            env_var="OPENAI_API_KEY",
            configured=True,
            in_priority=False,
            active=False,
            detail="set OPENAI_API_KEY (starts with 'sk-')",
        ),
        _make_status(
            method=AuthMethod.GOOGLE_OAUTH,
            kind="subscription",
            label="Google OAuth",
            env_var="DECEPTICON_AUTH_GEMINI",
            configured=False,
            in_priority=False,
            active=False,
            detail="set DECEPTICON_AUTH_GEMINI",
        ),
        _make_status(
            method=AuthMethod.OLLAMA_LOCAL,
            kind="local",
            label="Ollama Local",
            env_var="OLLAMA_API_BASE",
            configured=False,
            in_priority=False,
            active=False,
            detail="set OLLAMA_API_BASE",
        ),
    )
    inv = _make_inventory(statuses=statuses, resolved_chain=(), priority_explicit=False)
    output = auth._render_text(inv)
    assert "⚠ No usable credential detected." in output
    assert "decepticon onboard" in output
    assert "Subscriptions (OAuth)" in output
    assert "API keys" in output
    assert "Local / custom endpoints" in output
    assert "OpenAI API" in output
    assert "⚠ Configured but NOT routed" in output
    assert output.endswith("\n")


def test_render_text_with_resolved_chain_no_idle():
    statuses = (
        _make_status(
            method=AuthMethod.OPENAI_API,
            kind="api",
            label="OpenAI API",
            env_var="OPENAI_API_KEY",
            configured=True,
            in_priority=True,
            active=True,
            detail="set OPENAI_API_KEY",
        ),
        _make_status(
            method=AuthMethod.GROQ_API,
            kind="api",
            label="Groq API",
            env_var="GROQ_API_KEY",
            configured=True,
            in_priority=True,
            active=True,
            detail="set GROQ_API_KEY",
        ),
    )
    inv = _make_inventory(
        statuses=statuses,
        resolved_chain=(AuthMethod.OPENAI_API, AuthMethod.GROQ_API),
        priority_explicit=False,
    )
    output = auth._render_text(inv)
    assert "Resolved fallback chain (priority order):" in output
    assert "openai_api" in output
    assert "groq_api" in output
    assert "⚠ No usable credential" not in output
    assert "⚠ Configured but NOT routed" not in output


def test_render_text_empty_group_skipped():
    statuses = (
        _make_status(
            method=AuthMethod.OPENAI_API,
            kind="api",
            label="OpenAI API",
            env_var="OPENAI_API_KEY",
            configured=False,
            in_priority=False,
            active=False,
            detail="set OPENAI_API_KEY",
        ),
    )
    inv = _make_inventory(statuses=statuses, resolved_chain=(), priority_explicit=False)
    output = auth._render_text(inv)
    assert "Subscriptions (OAuth)" not in output
    assert "Local / custom endpoints" not in output
    assert "API keys" in output


def test_main_env_file_not_found_returns_exit_config(tmp_path, capsys):
    rc = auth_main(["status", "--env-file", str(tmp_path / "nope.env")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "error: env file not found" in captured.err


def test_main_env_file_existing_is_loaded(clean_env, tmp_path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-" + "y" * 48 + "\n", encoding="utf-8")
    rc = auth_main(["status", "--env-file", str(env_file)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "openai_api" in out.lower() or "active" in out.lower()


def test_main_default_env_discovery_loads_env(clean_env, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DECEPTICON_HOME", str(tmp_path))
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-" + "z" * 48 + "\n", encoding="utf-8")
    rc = auth_main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "openai_api" in out.lower() or "active" in out.lower()


def test_main_doctor_fake_inventory_no_active(monkeypatch, capsys):
    fake_inv = _make_inventory(statuses=(), resolved_chain=(), priority_explicit=False)
    monkeypatch.setattr(factory, "auth_inventory", lambda: fake_inv)
    rc = auth_main(["doctor", "--no-env-file"])
    assert rc == 2
    capsys.readouterr()


def test_main_doctor_fake_inventory_with_active(monkeypatch, capsys):
    statuses = (
        _make_status(
            method=AuthMethod.OPENAI_API,
            kind="api",
            label="OpenAI API",
            env_var="OPENAI_API_KEY",
            configured=True,
            in_priority=True,
            active=True,
            detail="set OPENAI_API_KEY",
        ),
    )
    fake_inv = _make_inventory(
        statuses=statuses,
        resolved_chain=(AuthMethod.OPENAI_API,),
        priority_explicit=False,
    )
    monkeypatch.setattr(factory, "auth_inventory", lambda: fake_inv)
    rc = auth_main(["doctor", "--no-env-file"])
    assert rc == 0
    capsys.readouterr()


def test_load_env_file_non_utf8_returns_zero_without_raising(tmp_path):
    # A corrupt / binary .env must not crash the CLI with a raw UnicodeDecodeError
    # (which is a ValueError, not an OSError) — it degrades to "nothing loaded".
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"OPENAI_API_KEY=\xff\xfe\x00bad\x80value")
    assert auth._load_env_file(env_file) == 0


def test_main_inventory_failure_reports_cleanly(monkeypatch, capsys):
    # A misconfiguration surfacing from the factory probe (e.g. a malformed
    # credential file) must yield an actionable message + EXIT_CONFIG, never a
    # bare traceback at the operator.
    def _boom():
        raise RuntimeError("malformed credential file")

    monkeypatch.setattr(factory, "auth_inventory", _boom)
    rc = auth_main(["status", "--no-env-file"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "could not inspect auth configuration" in captured.err
    assert "malformed credential file" in captured.err
    assert "Traceback" not in captured.err
