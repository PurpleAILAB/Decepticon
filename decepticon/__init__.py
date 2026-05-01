"""Decepticon — AI-powered autonomous red team testing framework."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    # pyproject.toml carries a "0.0.0" sentinel; release.yml stamps the
    # real tag into the package metadata at Docker build time, and
    # importlib.metadata reads it back here. Local checkouts read 0.0.0.
    __version__ = _version("decepticon")
except PackageNotFoundError:
    __version__ = "0.0.0"

__package_name__ = "decepticon"
