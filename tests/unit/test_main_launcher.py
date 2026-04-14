"""Unit tests for the ``decepticon`` entry point env-resolution logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.__main__ import _parse_env_file, _resolve_env


class TestParseEnvFile:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert _parse_env_file(tmp_path / "nope.env") == {}

    def test_key_value_comments_and_quotes(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "# header comment\n"
            "FOO=bar\n"
            '  QUOTED  =  "hello world"  \n'
            "EMPTY=\n"
            "# commented=out\n"
            "WITH_EQUALS=a=b=c\n"
        )
        result = _parse_env_file(env)
        assert result == {
            "FOO": "bar",
            "QUOTED": "hello world",
            "EMPTY": "",
            "WITH_EQUALS": "a=b=c",
        }


class TestResolveEnv:
    def test_defaults_when_no_env_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LANGGRAPH_PORT", raising=False)
        monkeypatch.delenv("DECEPTICON_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))  # so ~ expansion is deterministic
        port, home = _resolve_env(tmp_path)
        assert port == 2024
        assert home == (tmp_path / ".decepticon").resolve()

    def test_env_file_supplies_port_and_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LANGGRAPH_PORT", raising=False)
        monkeypatch.delenv("DECEPTICON_HOME", raising=False)
        workspace = tmp_path / "custom"
        (tmp_path / ".env").write_text(f"LANGGRAPH_PORT=9999\nDECEPTICON_HOME={workspace}\n")
        port, home = _resolve_env(tmp_path)
        assert port == 9999
        assert home == workspace.resolve()

    def test_os_env_overrides_dotenv(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / ".env").write_text("LANGGRAPH_PORT=9999\n")
        monkeypatch.setenv("LANGGRAPH_PORT", "3030")
        port, _ = _resolve_env(tmp_path)
        assert port == 3030

    def test_tilde_is_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Compose cannot expand ~; the launcher must.
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("DECEPTICON_HOME", "~/.decepticon")
        _, home = _resolve_env(tmp_path)
        assert str(home).startswith(str(tmp_path))
        assert "~" not in str(home)

    def test_invalid_port_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGGRAPH_PORT", "not-a-number")
        with pytest.raises(SystemExit) as exc:
            _resolve_env(tmp_path)
        assert exc.value.code == 2
