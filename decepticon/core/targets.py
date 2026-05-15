"""Multi-target ingestion — Strix-style ``-t srccode -t live-url`` parity.

Decepticon today scopes one engagement to a single ``target_url``
(see :class:`decepticon.middleware.engagement.EngagementContext`). This
module adds a typed, validated multi-target set that the launcher / CLI
can construct from any combination of repo URLs, source paths, live URLs,
or IP ranges and pass through to recon + exploit agents.

Cross-correlation: when both source and live targets are present, the
recon agent should fan out across them and the exploit agent can use
:func:`correlate_targets` to match findings on a live URL back to file
paths in the corresponding source repo.

Wire format::

    [
      {"id": "src",  "kind": "source",      "value": "https://github.com/org/repo"},
      {"id": "web",  "kind": "live_url",    "value": "https://app.example.com"},
      {"id": "api",  "kind": "live_url",    "value": "https://api.example.com"}
    ]

The ``id`` is opaque but stable: tools that take a ``target_id`` filter
the active engagement's recon to one entry. Default behaviour
(no ``target_id``) iterates every target.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class TargetKind(str, Enum):
    """Discriminator for how the target should be approached.

    ``source`` and ``source_path`` indicate static analysis territory;
    ``live_url``/``ip_range``/``host`` are dynamic targets.
    """

    SOURCE = "source"
    SOURCE_PATH = "source_path"
    LIVE_URL = "live_url"
    IP_RANGE = "ip_range"
    HOST = "host"


_GITHUB_RE = re.compile(r"^https?://(www\.)?(github|gitlab|bitbucket)\.com/", re.IGNORECASE)
_IP_RANGE_RE = re.compile(
    r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$"  # IPv4 + optional CIDR
)
_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]?$",
    re.IGNORECASE,
)


def detect_kind(value: str) -> TargetKind:
    """Best-effort kind inference for a raw target string.

    The launcher passes ``--target`` values straight from the user — they
    don't need to spell out the kind, but the agents need to know whether
    to fire static or dynamic tools at each entry.
    """
    if not isinstance(value, str):
        raise TypeError("target value must be a string")
    raw = value.strip()
    if not raw:
        raise ValueError("target value is empty")
    # Repo URLs (GitHub/GitLab/Bitbucket) → source
    if _GITHUB_RE.match(raw):
        return TargetKind.SOURCE
    # File path / local repo → source_path
    if raw.startswith((".", "/", "~")) or raw.startswith("file://"):
        return TargetKind.SOURCE_PATH
    # http(s) URL → live_url
    if raw.startswith(("http://", "https://")):
        return TargetKind.LIVE_URL
    # IPv4[/CIDR] → ip_range
    if _IP_RANGE_RE.match(raw):
        return TargetKind.IP_RANGE
    # bare hostname → host
    if _HOST_RE.match(raw):
        return TargetKind.HOST
    raise ValueError(f"could not infer target kind for {raw!r}")


def _slug_from_url(url: str) -> str:
    """Stable short id derived from a URL or path."""
    parsed = urlparse(url) if "://" in url else None
    if parsed and parsed.netloc:
        host = parsed.netloc.split(":", 1)[0]
        # Drop the TLD suffix for readability — example.com → example
        host_parts = host.split(".")
        if len(host_parts) >= 2:
            return host_parts[-2].lower()
        return host.lower()
    # Fallback: use the last path segment
    name = Path(url.rstrip("/")).name
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "target"


class Target(BaseModel):
    """One in-scope asset for the engagement."""

    id: str = Field(description="Stable slug (alphanumeric + hyphen, max 32 chars).")
    kind: TargetKind = Field(description="Target classification.")
    value: str = Field(description="Raw target identifier (URL, path, IP, etc.)")
    label: str = Field(default="", description="Operator-friendly display name.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", v):
            raise ValueError(
                "target id must be lowercase alphanumeric/hyphen, 1-32 chars, "
                f"starting with alnum (got {v!r})"
            )
        return v

    @classmethod
    def parse(cls, raw: str, *, target_id: str | None = None, label: str = "") -> Target:
        """Build a Target from a raw CLI string, inferring the kind + id."""
        value = raw.strip()
        kind = detect_kind(value)
        slug = target_id or _slug_from_url(value)
        # Ensure slug satisfies the validator (truncate, normalise)
        slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:32] or "target"
        if not re.match(r"^[a-z0-9]", slug):
            slug = "t-" + slug.lstrip("-")
            slug = slug[:32]
        return cls(id=slug, kind=kind, value=value, label=label or value)

    @property
    def is_static(self) -> bool:
        """True when the target is approached via static analysis."""
        return self.kind in (TargetKind.SOURCE, TargetKind.SOURCE_PATH)

    @property
    def is_dynamic(self) -> bool:
        """True when the target is approached via dynamic / network probing."""
        return self.kind in (TargetKind.LIVE_URL, TargetKind.IP_RANGE, TargetKind.HOST)


class TargetSet(BaseModel):
    """Ordered, de-duplicated collection of :class:`Target` for an engagement."""

    targets: list[Target] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.targets)

    def __iter__(self) -> Iterator[Target]:  # type: ignore[override]
        return iter(self.targets)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return any(t.id == key or t.value == key for t in self.targets)
        return False

    def get(self, target_id: str) -> Target | None:
        return next((t for t in self.targets if t.id == target_id), None)

    @property
    def static(self) -> list[Target]:
        return [t for t in self.targets if t.is_static]

    @property
    def dynamic(self) -> list[Target]:
        return [t for t in self.targets if t.is_dynamic]

    def add(self, target: Target | str) -> Target:
        """Add a target. Strings are parsed via :meth:`Target.parse`.

        Returns the newly added :class:`Target`. Re-adding the same value
        returns the existing entry without mutation. ID collisions are
        resolved differently for the two callsites:

        * **String input** (CLI ``-t`` flag): the auto-derived id is
          suffix-numbered (``example`` → ``example-2``) so the operator
          never has to disambiguate by hand.
        * **Explicit Target object** with a hand-picked id: a colliding id
          mapped to a different value raises :exc:`ValueError`. This
          surfaces typos in launcher configs early.
        """
        explicit = isinstance(target, Target)
        t = target if explicit else Target.parse(target)
        for existing in self.targets:
            if existing.id == t.id:
                if existing.value == t.value:
                    return existing
                if explicit:
                    raise ValueError(
                        f"target id {t.id!r} already mapped to {existing.value!r}; "
                        "pass an explicit target_id to disambiguate"
                    )
                # String input: auto-rename below
                break
        if any(existing.id == t.id for existing in self.targets):
            base = t.id
            n = 2
            while any(existing.id == f"{base}-{n}" for existing in self.targets):
                n += 1
            t = t.model_copy(update={"id": f"{base}-{n}"[:32]})
        self.targets.append(t)
        return t

    @classmethod
    def from_strings(cls, values: list[str]) -> TargetSet:
        """Convenience builder used by the CLI ``-t``/``--target`` flag."""
        ts = cls()
        for v in values:
            ts.add(v)
        return ts

    @classmethod
    def from_json(cls, payload: str | bytes) -> TargetSet:
        data = json.loads(payload)
        if isinstance(data, list):
            return cls(targets=[Target(**item) for item in data])
        if isinstance(data, dict) and "targets" in data:
            return cls(targets=[Target(**item) for item in data["targets"]])
        raise ValueError("expected a JSON list or {'targets': [...]} object")

    def to_json(self) -> str:
        """Render as a JSON string suitable for OPPLAN persistence."""
        return json.dumps(
            [t.model_dump(mode="json") for t in self.targets],
            indent=2,
            ensure_ascii=False,
        )


def _host_of(t: Target) -> str:
    """Best-effort hostname extraction from a Target's value."""
    val = t.value
    if "://" in val:
        return urlparse(val).netloc.split(":", 1)[0].lower()
    if _HOST_RE.match(val):
        return val.lower()
    return ""


def correlate_targets(
    static: Target,
    dynamic: Target,
    *,
    finding_value: str | None = None,
) -> dict[str, Any]:
    """Correlate two targets by their hostnames.

    Naming follows the source-vs-live ergonomics of the bug-bounty workflow
    (``static`` = the side you read code on, ``dynamic`` = the side you
    fire requests at), but the function itself is symmetric on hostnames:
    if both targets carry resolvable hosts the link kind is computed
    regardless of their declared kinds.

    Returns a dict containing ``static_id``, ``dynamic_id``, ``link_kind``
    (``same_host``/``same_base_domain``/``unrelated``), and the optional
    ``finding_value``. The exploit agent persists this as an Edge between
    the two target nodes in the knowledge graph.
    """
    out: dict[str, Any] = {
        "static_id": static.id,
        "dynamic_id": dynamic.id,
        "static_kind": static.kind.value,
        "dynamic_kind": dynamic.kind.value,
        "link_kind": "unrelated",
    }
    repo_host = _host_of(static)
    dyn_host = _host_of(dynamic)
    if repo_host and dyn_host:
        if dyn_host == repo_host or dyn_host.endswith("." + repo_host):
            out["link_kind"] = "same_host"
        else:
            repo_base = ".".join(repo_host.split(".")[-2:]) if "." in repo_host else repo_host
            dyn_base = ".".join(dyn_host.split(".")[-2:]) if "." in dyn_host else dyn_host
            if repo_base and dyn_base and repo_base == dyn_base:
                out["link_kind"] = "same_base_domain"
    if finding_value:
        out["finding_value"] = finding_value
    return out


__all__ = [
    "Target",
    "TargetKind",
    "TargetSet",
    "correlate_targets",
    "detect_kind",
]
