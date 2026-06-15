"""Generic, domain-agnostic URL transforms for the fetch grid.

Transforms are *rules*, never site references (No-Site-Name rule). A transform
either applies (returns a new URL) or is skipped (returns ``None``). The grid
planner iterates an ordered list of transform names and dedupes the results.

Empirically useful (cross-site validated before adding):
  * ``mobile_subdomain`` — ``www.example.com`` → ``m.example.com``. Strong win
    on SSR mobile-first sites; can lose on SPA shells that serve a tiny mobile
    bootstrap.
  * ``am_prefix`` — apex ``example.com`` → ``m.example.com``.
  * ``drop_www`` — occasionally unblocks hosts that gate ``www`` but not apex.

Derived from ``fivetaku/insane-search`` (MIT), ``engine/url_transforms.py``.
Adding a transform requires proof it helps on >=2 unrelated sites.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit


def _replace_host(url: str, new_host: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(netloc=new_host))


def _original(url: str) -> str | None:
    return url


def _mobile_subdomain(url: str) -> str | None:
    """``https://www.example.com/a`` → ``https://m.example.com/a`` (host must start with ``www.``)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not host.startswith("www."):
        return None
    new_host = "m." + host[4:]
    if parts.port:
        new_host = f"{new_host}:{parts.port}"
    return _replace_host(url, new_host)


def _am_prefix(url: str) -> str | None:
    """``https://example.com/a`` → ``https://m.example.com/a`` (apex-like host only)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not host or host.startswith("m."):
        return None
    if host.startswith("www."):
        return None  # handled by mobile_subdomain
    # Only apply to apex-like hosts (<=2 dot-separated labels).
    if host.count(".") >= 2:
        return None
    return _replace_host(url, "m." + host)


def _drop_www(url: str) -> str | None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not host.startswith("www."):
        return None
    new_host = host[4:]
    if parts.port:
        new_host = f"{new_host}:{parts.port}"
    return _replace_host(url, new_host)


TRANSFORMS: dict[str, Callable[[str], str | None]] = {
    "original": _original,
    "mobile_subdomain": _mobile_subdomain,
    "am_prefix": _am_prefix,
    "drop_www": _drop_www,
}


def apply_transform(name: str, url: str) -> str | None:
    """Apply one transform by name. Returns the new URL, or ``None`` if skipped."""
    fn = TRANSFORMS.get(name)
    if fn is None:
        raise ValueError(f"Unknown transform: {name!r}. Known: {list(TRANSFORMS)}")
    return fn(url)


def iter_transformed(url: str, order: list[str]) -> list[tuple[str, str]]:
    """Yield ``(transform_name, transformed_url)`` for the given order.

    Skips transforms that do not apply (``None``) and dedupes URLs so e.g.
    ``original`` and ``drop_www`` of an apex URL do not both run.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name in order:
        new_url = apply_transform(name, url)
        if new_url is None or new_url in seen:
            continue
        seen.add(new_url)
        out.append((name, new_url))
    return out
