"""Plugin loader contract tests.

The plugin loader is the OSS↔downstream extension surface. These tests pin its
behavior so future refactors don't silently break the contract external
plugin packages depend on.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from decepticon_core import plugin_loader


class _FakeEntryPoint:
    """Stand-in for ``importlib.metadata.EntryPoint`` used in tests."""

    def __init__(self, name: str, value: str, loaded):
        self.name = name
        self.value = value
        self._loaded = loaded

    def load(self):
        return self._loaded


def test_empty_discovery_returns_empty():
    """No entry-points → empty list/dict, no exception."""
    with patch.object(plugin_loader, "entry_points", return_value=[]):
        assert plugin_loader.load_plugin_tools() == []
        assert plugin_loader.load_plugin_middleware() == []
        assert plugin_loader.load_plugin_callbacks() == []
        assert plugin_loader.load_plugin_agents() == {}


def test_list_export_passes_through():
    """A plugin exporting a list is returned as-is (list is not callable)."""
    tool_a = MagicMock(invoke=MagicMock())
    tool_b = MagicMock(invoke=MagicMock())
    ep = _FakeEntryPoint("my-tools", "my_pkg:TOOLS", [tool_a, tool_b])
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_plugin_tools(role="recon")
    assert result == [tool_a, tool_b]


def test_factory_export_is_called_with_role_and_deps():
    """A non-runtime callable export is invoked with role + dep kwargs."""
    captured: dict = {}

    def factory(*, role=None, backend=None):
        captured["role"] = role
        captured["backend"] = backend
        return [MagicMock(invoke=MagicMock())]

    ep = _FakeEntryPoint("my-factory", "my_pkg:factory", factory)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_plugin_tools(role="exploit", backend="sentinel")

    assert captured == {"role": "exploit", "backend": "sentinel"}
    assert len(result) == 1


def test_single_runtime_object_is_wrapped_in_list():
    """A single tool instance (callable but has runtime attrs) is wrapped."""
    tool = MagicMock(invoke=MagicMock())  # passes the runtime-object heuristic
    ep = _FakeEntryPoint("single", "my_pkg:tool", tool)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        assert plugin_loader.load_plugin_tools() == [tool]


def test_broken_load_is_logged_and_skipped(monkeypatch):
    """A plugin that raises in ``.load()`` is skipped; siblings still load."""
    logged: list[str] = []
    monkeypatch.setattr(
        plugin_loader.logger,
        "exception",
        lambda msg, *args, **kw: logged.append(str(msg) % args if args else str(msg)),
    )

    class BrokenEP:
        name = "broken"
        value = "broken_pkg:thing"

        def load(self):
            raise RuntimeError("boom")

    good = MagicMock(invoke=MagicMock())
    eps = [BrokenEP(), _FakeEntryPoint("good", "good:thing", good)]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_plugin_tools()

    assert result == [good]
    assert any("broken" in m for m in logged)


def test_broken_factory_call_is_logged_and_skipped(monkeypatch):
    """A factory that raises at invocation time is skipped; siblings load."""
    logged: list[str] = []
    monkeypatch.setattr(
        plugin_loader.logger,
        "exception",
        lambda msg, *args, **kw: logged.append(str(msg) % args if args else str(msg)),
    )

    def broken_factory(**kwargs):
        raise RuntimeError("nope")

    good_obj = MagicMock(invoke=MagicMock())
    eps = [
        _FakeEntryPoint("broken-factory", "pkg:f", broken_factory),
        _FakeEntryPoint("good", "pkg:t", good_obj),
    ]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_plugin_tools()

    assert result == [good_obj]
    assert any("broken-factory" in m for m in logged)


def test_load_plugin_agents_normalizes_to_module_graph():
    """Plugin agent entry-points are normalized to ``module:graph`` paths."""

    class EP:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    eps = [
        EP("compliance", "my_pkg.agents.compliance:create_agent"),
        EP("audit", "my_pkg.agents.audit"),  # module-only form
    ]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_plugin_agents()

    assert result == {
        "compliance": "my_pkg.agents.compliance:graph",
        "audit": "my_pkg.agents.audit:graph",
    }


def test_none_result_from_factory_is_dropped():
    """A factory returning None doesn't pollute the output list."""

    def factory(**kwargs):
        return None

    ep = _FakeEntryPoint("noop", "pkg:f", factory)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        assert plugin_loader.load_plugin_tools() == []


# ---------------------------------------------------------------------------
# Subagent discovery — load_subagents_for_parent
# ---------------------------------------------------------------------------


def _spec(name: str, parents=("decepticon",), priority: int = 100, bundle: str | None = None):
    """Construct a SubAgentSpec for tests with a stub factory."""
    return plugin_loader.SubAgentSpec(
        name=name,
        description=f"{name} description",
        factory=lambda: f"{name}-agent",
        parent_agents=tuple(parents),
        bundle=bundle,
        priority=priority,
    )


def test_load_subagents_filters_by_parent():
    """Only specs whose parent_agents includes the requested parent are returned."""
    specs = [
        _spec("recon", parents=("decepticon",)),
        _spec("scanner", parents=("vulnresearch",)),
        _spec("shared-tool", parents=("decepticon", "vulnresearch")),
    ]
    eps = [_FakeEntryPoint(s.name, f"pkg.{s.name}:SUBAGENT_SPEC", s) for s in specs]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        decepticon_specs = plugin_loader.load_subagents_for_parent("decepticon")
        vulnresearch_specs = plugin_loader.load_subagents_for_parent("vulnresearch")

    assert {s.name for s in decepticon_specs} == {"recon", "shared-tool"}
    assert {s.name for s in vulnresearch_specs} == {"scanner", "shared-tool"}


def test_load_subagents_sorted_by_priority_then_name():
    """Returned specs follow (priority asc, name asc) order."""
    specs = [
        _spec("b-late", priority=50),
        _spec("a-early", priority=10),
        _spec("c-also-early", priority=10),
    ]
    eps = [_FakeEntryPoint(s.name, f"pkg.{s.name}:SUBAGENT_SPEC", s) for s in specs]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_subagents_for_parent("decepticon")

    assert [s.name for s in result] == ["a-early", "c-also-early", "b-late"]


def test_load_subagents_supports_list_export():
    """Entry-points exporting a list of specs are flattened."""
    bundle = [
        _spec("alpha", priority=10),
        _spec("beta", priority=20),
    ]
    ep = _FakeEntryPoint("bundle", "pkg:BUNDLE", bundle)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_subagents_for_parent("decepticon")

    assert [s.name for s in result] == ["alpha", "beta"]


def test_load_subagents_supports_factory_callable():
    """A callable that returns a SubAgentSpec is invoked."""

    def make_spec():
        return _spec("dynamic", priority=5)

    ep = _FakeEntryPoint("dyn", "pkg:make_spec", make_spec)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_subagents_for_parent("decepticon")

    assert [s.name for s in result] == ["dynamic"]


def test_load_subagents_broken_plugin_is_logged_and_skipped(monkeypatch):
    """A broken subagent plugin is skipped; siblings still load."""
    logged: list[str] = []
    monkeypatch.setattr(
        plugin_loader.logger,
        "exception",
        lambda msg, *args, **kw: logged.append(str(msg) % args if args else str(msg)),
    )

    class BrokenEP:
        name = "broken"
        value = "broken:thing"

        def load(self):
            raise RuntimeError("boom")

    good = _spec("good")
    eps = [BrokenEP(), _FakeEntryPoint("good", "pkg.good:SUBAGENT_SPEC", good)]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_subagents_for_parent("decepticon")

    assert [s.name for s in result] == ["good"]
    assert any("broken" in m for m in logged)


def test_load_subagents_no_match_returns_empty():
    """Requesting a parent with no matching specs yields an empty list."""
    eps = [_FakeEntryPoint("recon", "pkg.recon:SUBAGENT_SPEC", _spec("recon"))]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_subagents_for_parent("nonexistent")

    assert result == []


def test_load_subagents_factory_is_lazy():
    """SubAgentSpec.factory is NOT invoked during discovery — caller decides."""
    invocations = {"count": 0}

    def factory():
        invocations["count"] += 1
        return "agent-instance"

    spec = plugin_loader.SubAgentSpec(
        name="lazy",
        description="...",
        factory=factory,
        parent_agents=("decepticon",),
    )
    ep = _FakeEntryPoint("lazy", "pkg:SUBAGENT_SPEC", spec)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_subagents_for_parent("decepticon")

    assert invocations["count"] == 0  # factory not yet called
    # caller invokes when ready
    assert result[0].factory() == "agent-instance"
    assert invocations["count"] == 1


# ---------------------------------------------------------------------------
# Bundle activation — 4-tier hierarchy
#   1 (highest) DECEPTICON_PLUGINS env var
#   2           .decepticon.toml [plugins].enabled
#   3           pyproject.toml [tool.decepticon.plugins].enabled
#   4 (lowest)  hardcoded ``DEFAULT_BUNDLES``
# ---------------------------------------------------------------------------


def test_enabled_bundles_default_is_standard_only(monkeypatch, tmp_path):
    """No env, no config file → DEFAULT_BUNDLES (standard)."""
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset({"standard"})


def test_enabled_bundles_env_overrides_default(monkeypatch, tmp_path):
    """Env var beats hardcoded default."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "standard,plugins,vendor")
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset({"standard", "plugins", "vendor"})


def test_enabled_bundles_env_wildcard(monkeypatch, tmp_path):
    """``*`` returns wildcard sentinel (empty frozenset)."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "*")
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset()


def test_enabled_bundles_env_strips_whitespace(monkeypatch, tmp_path):
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, " standard , plugins ,, ")
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset({"standard", "plugins"})


def test_enabled_bundles_pyproject_used_when_no_env(monkeypatch, tmp_path):
    """pyproject.toml ``[tool.decepticon.plugins].enabled`` used if env unset."""
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.decepticon.plugins]\nenabled = ["standard", "plugins"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset({"standard", "plugins"})


def test_enabled_bundles_decepticon_toml_beats_pyproject(monkeypatch, tmp_path):
    """``.decepticon.toml`` is higher precedence than pyproject.toml."""
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.decepticon.plugins]\nenabled = ["standard", "plugins"]\n',
        encoding="utf-8",
    )
    (tmp_path / ".decepticon.toml").write_text(
        '[plugins]\nenabled = ["standard"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset({"standard"})


def test_enabled_bundles_env_beats_config_files(monkeypatch, tmp_path):
    """Env var is top of the hierarchy — beats both config files."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "vendor")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.decepticon.plugins]\nenabled = ["standard", "plugins"]\n',
        encoding="utf-8",
    )
    (tmp_path / ".decepticon.toml").write_text(
        '[plugins]\nenabled = ["standard", "premium"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset({"vendor"})


def test_enabled_bundles_config_wildcard(monkeypatch, tmp_path):
    """``enabled = "*"`` or ``["*"]`` in config file → wildcard."""
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    (tmp_path / ".decepticon.toml").write_text(
        '[plugins]\nenabled = "*"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert plugin_loader._enabled_bundles() == frozenset()


def test_enabled_bundles_broken_config_falls_through(monkeypatch, tmp_path):
    """Malformed config file → logged + skipped, falls through to default."""
    logged: list[str] = []
    monkeypatch.setattr(
        plugin_loader.logger,
        "exception",
        lambda msg, *args, **kw: logged.append(str(msg) % args if args else str(msg)),
    )
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    (tmp_path / ".decepticon.toml").write_text(
        "this is not valid toml [\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = plugin_loader._enabled_bundles()
    assert result == frozenset({"standard"})
    assert any(".decepticon.toml" in m for m in logged)


def test_is_bundle_enabled_semantics(monkeypatch, tmp_path):
    """bundle=None always passes; explicit bundle gated by allowlist."""
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    assert plugin_loader.is_bundle_enabled("standard") is True
    assert plugin_loader.is_bundle_enabled("plugins") is False  # not in default
    assert plugin_loader.is_bundle_enabled(None) is True


def test_is_bundle_enabled_wildcard_passes_everything(monkeypatch, tmp_path):
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "*")
    monkeypatch.chdir(tmp_path)
    assert plugin_loader.is_bundle_enabled("standard") is True
    assert plugin_loader.is_bundle_enabled("anything") is True
    assert plugin_loader.is_bundle_enabled(None) is True


# ---------------------------------------------------------------------------
# Bundle filter applies to subagents
# ---------------------------------------------------------------------------


def test_load_subagents_filters_by_default_bundle(monkeypatch, tmp_path):
    """With default DECEPTICON_PLUGINS=standard, only standard specs returned."""
    monkeypatch.delenv(plugin_loader.PLUGINS_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    specs = [
        _spec("recon", parents=("decepticon",), bundle="standard", priority=10),
        _spec("scanner", parents=("decepticon",), bundle="plugins", priority=20),
        _spec("audit", parents=("decepticon",), bundle="vendor", priority=30),
    ]
    eps = [_FakeEntryPoint(s.name, f"pkg.{s.name}", s) for s in specs]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_subagents_for_parent("decepticon")
    assert [s.name for s in result] == ["recon"]


def test_load_subagents_filter_opts_in_via_env(monkeypatch, tmp_path):
    """Explicit env opt-in pulls in matching bundles."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "standard,plugins")
    monkeypatch.chdir(tmp_path)
    specs = [
        _spec("recon", parents=("decepticon",), bundle="standard", priority=10),
        _spec("scanner", parents=("decepticon",), bundle="plugins", priority=20),
        _spec("audit", parents=("decepticon",), bundle="vendor", priority=30),
    ]
    eps = [_FakeEntryPoint(s.name, f"pkg.{s.name}", s) for s in specs]
    with patch.object(plugin_loader, "entry_points", return_value=eps):
        result = plugin_loader.load_subagents_for_parent("decepticon")
    assert [s.name for s in result] == ["recon", "scanner"]


def test_load_subagents_no_bundle_always_loads(monkeypatch, tmp_path):
    """SubAgentSpec(bundle=None) loads even with restrictive env."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "standard")
    monkeypatch.chdir(tmp_path)
    spec = _spec("free", parents=("decepticon",), bundle=None, priority=10)
    ep = _FakeEntryPoint("free", "pkg.free", spec)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_subagents_for_parent("decepticon")
    assert [s.name for s in result] == ["free"]


# ---------------------------------------------------------------------------
# PluginBundle wrapper — applied to tools/middleware/callbacks discovery
# ---------------------------------------------------------------------------


def test_plugin_bundle_filtered_when_inactive(monkeypatch, tmp_path):
    """PluginBundle(bundle='premium') is dropped when env disables it."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "standard")
    monkeypatch.chdir(tmp_path)
    tool_a = MagicMock(invoke=MagicMock())
    bundle = plugin_loader.PluginBundle(items=(tool_a,), bundle="premium")
    ep = _FakeEntryPoint("premium-tools", "pkg:TOOLS", bundle)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        assert plugin_loader.load_plugin_tools() == []


def test_plugin_bundle_loaded_when_active(monkeypatch, tmp_path):
    """PluginBundle items unpacked when bundle is in the allowlist."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "standard,premium")
    monkeypatch.chdir(tmp_path)
    tool_a = MagicMock(invoke=MagicMock())
    tool_b = MagicMock(invoke=MagicMock())
    bundle = plugin_loader.PluginBundle(items=(tool_a, tool_b), bundle="premium")
    ep = _FakeEntryPoint("premium-tools", "pkg:TOOLS", bundle)
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_plugin_tools()
    assert result == [tool_a, tool_b]


def test_plain_list_export_always_loads(monkeypatch, tmp_path):
    """Plain list (no PluginBundle wrapper) loads regardless of env."""
    monkeypatch.setenv(plugin_loader.PLUGINS_ENV_VAR, "standard")
    monkeypatch.chdir(tmp_path)
    tool_a = MagicMock(invoke=MagicMock())
    ep = _FakeEntryPoint("compat-tools", "pkg:tools", [tool_a])
    with patch.object(plugin_loader, "entry_points", return_value=[ep]):
        result = plugin_loader.load_plugin_tools()
    assert result == [tool_a]
