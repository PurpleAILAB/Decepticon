"""Tests for the Arsenal declarative pentest-tool registry."""

from __future__ import annotations

import pytest

from decepticon.arsenal.registry import REGISTRY, ArgSchema, ToolSpec


class TestArgSchema:
    def test_render_required_missing_raises_via_toolspec(self) -> None:
        spec = ToolSpec(
            name="x",
            binary="x",
            description="x",
            category="recon",
            args=[ArgSchema("target", required=True, flag="-t")],
        )
        with pytest.raises(ValueError, match="required arg 'target'"):
            spec.build_command({})

    def test_render_bool_flag(self) -> None:
        schema = ArgSchema("v", bool, flag="-v")
        assert schema.render(True) == ["-v"]
        assert schema.render(False) == []

    def test_render_positional(self) -> None:
        schema = ArgSchema("target", str)  # no flag = positional
        assert schema.render("10.0.0.1") == ["10.0.0.1"]

    def test_render_multi(self) -> None:
        schema = ArgSchema("templates", multi=True, flag="-t")
        out = schema.render(["a", "b", "c"])
        assert out == ["-t", "a", "-t", "b", "-t", "c"]

    def test_render_none_omitted(self) -> None:
        schema = ArgSchema("opt", flag="-o")
        assert schema.render(None) == []
        assert schema.render("") == []

    def test_choices_validation(self) -> None:
        spec = ToolSpec(
            name="x",
            binary="x",
            description="x",
            category="recon",
            args=[ArgSchema("mode", choices=["a", "b"], default="a")],
        )
        with pytest.raises(ValueError, match=r"not in \['a', 'b'\]"):
            spec.build_command({"mode": "c"})


class TestToolSpecBuildCommand:
    def test_nmap_typical(self) -> None:
        nmap = next(t for t in REGISTRY if t.name == "nmap")
        cmd = nmap.build_command(
            {"target": "10.0.0.1", "ports": "80,443", "service_detection": True}
        )
        assert cmd[0] == "nmap"
        assert "10.0.0.1" in cmd
        assert "-p" in cmd and "80,443" in cmd
        assert "-sV" in cmd

    def test_ffuf_minimum(self) -> None:
        ffuf = next(t for t in REGISTRY if t.name == "ffuf")
        cmd = ffuf.build_command(
            {"url": "https://target.com/FUZZ", "wordlist": "/usr/share/wordlists/common.txt"}
        )
        assert "-u" in cmd
        assert "-w" in cmd

    def test_ffuf_missing_required(self) -> None:
        ffuf = next(t for t in REGISTRY if t.name == "ffuf")
        with pytest.raises(ValueError, match="url"):
            ffuf.build_command({"wordlist": "/wl.txt"})

    def test_nuclei_multi_template(self) -> None:
        nuclei = next(t for t in REGISTRY if t.name == "nuclei")
        cmd = nuclei.build_command(
            {"target": "https://target.com", "templates": ["cves/", "exposures/"]}
        )
        # Each -t comes with its own value
        assert cmd.count("-t") == 2
        assert "cves/" in cmd and "exposures/" in cmd


class TestRegistryCoverage:
    def test_minimum_categories_present(self) -> None:
        categories = {spec.category for spec in REGISTRY}
        # Decepticon advertises 6 specialist domains — ensure each has at
        # least one tool in the arsenal.
        for required in {"recon", "web", "ad", "crypto", "re", "mobile", "cloud"}:
            assert required in categories, f"missing category: {required}"

    def test_each_tool_has_examples(self) -> None:
        # Examples drive the LLM's pattern matching — every tool must have
        # at least one runnable example.
        missing = [s.name for s in REGISTRY if not s.examples]
        assert not missing, f"tools missing examples: {missing}"

    def test_each_tool_has_install_hint(self) -> None:
        missing = [s.name for s in REGISTRY if not s.install_hint]
        assert not missing, f"tools missing install_hint: {missing}"

    def test_no_duplicate_names(self) -> None:
        names = [s.name for s in REGISTRY]
        assert len(names) == len(set(names)), "duplicate tool names in REGISTRY"
