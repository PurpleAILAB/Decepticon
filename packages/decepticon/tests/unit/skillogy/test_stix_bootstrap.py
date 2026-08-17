from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from decepticon.skillogy.builder.stix_bootstrap import STIX_SHA256, STIX_URL, ensure_stix_bundle


class _Response(BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def test_pinned_release_checksum_is_current() -> None:
    assert STIX_URL.startswith(
        "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/6c3719993d0401de199203ecc3f369544d9e091c/"
    )
    assert STIX_SHA256 == "bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"


def test_bootstrap_downloads_verifies_and_reuses_pinned_bundle(tmp_path: Path, monkeypatch) -> None:
    payload = b'{"type":"bundle"}'
    expected = hashlib.sha256(payload).hexdigest()
    calls: list[str] = []

    def opener(url: str, timeout: int) -> _Response:
        calls.append(url)
        assert timeout == 30
        return _Response(payload)

    monkeypatch.setattr("decepticon.skillogy.builder.stix_bootstrap.urlopen", opener)
    destination = tmp_path / "cache" / "enterprise.json"

    assert (
        ensure_stix_bundle(destination, url="https://example.test/stix", expected_sha256=expected)
        == destination
    )
    assert destination.read_bytes() == payload
    assert (
        ensure_stix_bundle(destination, url="https://example.test/stix", expected_sha256=expected)
        == destination
    )
    assert calls == ["https://example.test/stix"]


def test_bootstrap_rejects_corrupt_existing_bundle_without_network(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "enterprise.json"
    destination.write_text("bad", encoding="utf-8")

    def opener(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("network must not be used for a corrupt existing cache")

    monkeypatch.setattr("decepticon.skillogy.builder.stix_bootstrap.urlopen", opener)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ensure_stix_bundle(destination, expected_sha256="0" * 64)
