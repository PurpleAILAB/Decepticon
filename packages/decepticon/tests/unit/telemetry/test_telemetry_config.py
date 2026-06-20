"""Tests for decepticon.telemetry.config — consent resolution + identity."""

from __future__ import annotations

from decepticon.telemetry.config import (
    TelemetryMode,
    install_id,
    resolve_config,
    resolve_mode,
)


def test_default_is_off_opt_in() -> None:
    assert resolve_mode({}) is TelemetryMode.OFF


def test_explicit_modes() -> None:
    assert resolve_mode({"DECEPTICON_TELEMETRY": "basic"}) is TelemetryMode.BASIC
    assert resolve_mode({"DECEPTICON_TELEMETRY": "research"}) is TelemetryMode.RESEARCH
    assert resolve_mode({"DECEPTICON_TELEMETRY": "off"}) is TelemetryMode.OFF


def test_do_not_track_forces_off() -> None:
    env = {"DECEPTICON_TELEMETRY": "research", "DO_NOT_TRACK": "1"}
    assert resolve_mode(env) is TelemetryMode.OFF


def test_unrecognized_value_fails_closed_to_off() -> None:
    assert resolve_mode({"DECEPTICON_TELEMETRY": "verbose"}) is TelemetryMode.OFF


def test_enabled_requires_mode_and_endpoint() -> None:
    # mode on but no endpoint -> not enabled
    cfg = resolve_config({"DECEPTICON_TELEMETRY": "basic"})
    assert cfg.enabled is False
    # off but endpoint set -> not enabled
    cfg = resolve_config({"DECEPTICON_TELEMETRY_ENDPOINT": "https://gw.example"})
    assert cfg.enabled is False
    # both -> enabled
    cfg = resolve_config(
        {"DECEPTICON_TELEMETRY": "basic", "DECEPTICON_TELEMETRY_ENDPOINT": "https://gw.example"}
    )
    assert cfg.enabled is True


def test_install_id_persists(tmp_path) -> None:
    env = {"DECEPTICON_HOME": str(tmp_path)}
    first = install_id(env)
    second = install_id(env)
    assert first == second
    assert (tmp_path / "telemetry" / "install_id").read_text().strip() == first


def test_off_config_does_not_mint_install_id(tmp_path) -> None:
    cfg = resolve_config({"DECEPTICON_HOME": str(tmp_path)})  # off by default
    assert cfg.install_id == "00000000-0000-0000-0000-000000000000"
    assert not (tmp_path / "telemetry").exists()  # purely side-effect-free when off
