"""Spec §14 acceptance — make_agent_backend(extra_routes=).

Verifies acceptance criterion #11 from
``docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md``:

  ``make_agent_backend(sandbox, extra_routes={"/foo/": some_backend})``
  is exercised by a test that reads from ``/foo/x.txt`` and the vendor
  overlay pattern from the previous PR is a one-liner.

Also verifies the spec §16.4 #5 longest-prefix-wins ordering — a
tenant-specific ``/skills/tenant/<id>/`` route must override the
generic ``/skills/`` default deterministically.
"""

from __future__ import annotations

from decepticon.backends import make_agent_backend
from decepticon_sdk.testing import FakeBackend, FakeSandbox


def test_extra_routes_adds_caller_supplied_prefix() -> None:
    """Caller-supplied ``extra_routes`` mount on top of the OSS default."""
    sandbox = FakeSandbox()
    overlay = FakeBackend({"/foo/x.txt": "overlay content"})

    backend = make_agent_backend(sandbox, extra_routes={"/foo/": overlay})

    assert "/skills/" in backend.routes
    assert "/foo/" in backend.routes


def test_longest_prefix_wins() -> None:
    """Spec §16.4 #5: tenant paths override the generic ``/skills/`` default.

    The route iteration order must place the longer prefix first so a
    request for ``/skills/tenant/abc/skill.md`` doesn't fall through
    to the generic OSS skill backend.
    """
    sandbox = FakeSandbox()
    tenant = FakeBackend({"/skills/tenant/abc/skill.md": "tenant"})

    backend = make_agent_backend(sandbox, extra_routes={"/skills/tenant/abc/": tenant})

    route_prefixes = list(backend.routes.keys())
    assert route_prefixes[0] == "/skills/tenant/abc/", (
        f"longest prefix should be first, got {route_prefixes!r}"
    )
    assert route_prefixes[1] == "/skills/"


def test_baseline_without_extra_routes() -> None:
    """Calling without extra_routes preserves the OSS default surface."""
    sandbox = FakeSandbox()
    backend = make_agent_backend(sandbox)
    assert list(backend.routes.keys()) == ["/skills/"]


def test_reserved_prefix_skills_root_rejected() -> None:
    """Caller cannot shadow the OSS ``/skills/`` route wholesale.

    Without this guard a downstream consumer passing
    ``extra_routes={"/skills/": evil}`` would substitute attacker-
    controlled content into every model turn (security review B2).
    """
    import pytest

    sandbox = FakeSandbox()
    overlay = FakeBackend({"/skills/recon/index.md": "attacker"})
    with pytest.raises(ValueError, match=r"reserved"):
        make_agent_backend(sandbox, extra_routes={"/skills/": overlay})


def test_reserved_prefix_root_rejected() -> None:
    """Empty or bare-slash prefixes are rejected — would route ALL
    paths through the caller's backend."""
    import pytest

    sandbox = FakeSandbox()
    overlay = FakeBackend({})
    for bad in ("", "/"):
        with pytest.raises(ValueError, match=r"reserved"):
            make_agent_backend(sandbox, extra_routes={bad: overlay})


def test_path_traversal_rejected() -> None:
    """``..`` in a route key is rejected as a path-traversal attempt."""
    import pytest

    sandbox = FakeSandbox()
    overlay = FakeBackend({})
    with pytest.raises(ValueError, match=r"traversal|'\\.\\.'"):
        make_agent_backend(sandbox, extra_routes={"/skills/../etc/": overlay})


def test_missing_slash_rejected() -> None:
    """Keys must be in ``/.../`` form (leading + trailing slash)."""
    import pytest

    sandbox = FakeSandbox()
    overlay = FakeBackend({})
    for bad in ("skills/tenant/x/", "/skills/tenant/x", "skills"):
        with pytest.raises(ValueError, match=r"absolute prefix"):
            make_agent_backend(sandbox, extra_routes={bad: overlay})


def test_valid_subprefix_passes() -> None:
    """Valid ``/skills/tenant/<id>/`` sub-prefix passes validation."""
    sandbox = FakeSandbox()
    overlay = FakeBackend({"/skills/tenant/abc/skill.md": "tenant"})
    backend = make_agent_backend(sandbox, extra_routes={"/skills/tenant/abc/": overlay})
    assert "/skills/tenant/abc/" in backend.routes


def test_extra_routes_actually_serves_content() -> None:
    """Spec §14 acceptance #11 literal text: the test reads from
    ``/foo/x.txt`` through the composed backend and gets the
    extra_routes-supplied content.

    The previous ordering-only test verified the route LIST; this one
    verifies the runtime DISPATCH — proving longest-prefix routing
    actually delivers caller-mounted content for filesystem-shaped
    operations.

    Note: ``CompositeBackend`` strips the matching prefix before
    delegating to the sub-backend (deepagents convention), so the
    FakeBackend stores the suffix key ``/x.txt`` even though the
    composite call uses the full ``/skills/plugins/apt/x.txt``.
    """
    sandbox = FakeSandbox()
    overlay = FakeBackend({"/x.txt": "overlay-content"})
    backend = make_agent_backend(
        sandbox,
        extra_routes={"/skills/plugins/apt/": overlay},
    )
    # CompositeBackend's read dispatch hits the matching prefix backend.
    content = backend.read("/skills/plugins/apt/x.txt")
    assert content == "overlay-content"
