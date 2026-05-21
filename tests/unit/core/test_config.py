"""Unit tests for decepticon.core.config"""

from decepticon.core.config import DecepticonConfig, load_config


class TestDecepticonConfig:
    def test_default_values(self):
        config = DecepticonConfig()
        assert config.debug is False

    def test_llm_defaults(self):
        config = DecepticonConfig()
        assert config.llm.proxy_url == "http://localhost:4000"
        assert config.llm.proxy_api_key == "sk-decepticon-master"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DECEPTICON_DEBUG", "true")
        config = DecepticonConfig()
        assert config.debug is True


class TestLoadConfig:
    def test_returns_defaults(self):
        config = load_config()
        assert config.llm.proxy_url == "http://localhost:4000"
