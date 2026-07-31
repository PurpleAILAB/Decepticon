"""Engagement scoping is a boundary, not a convention.

One graph can hold several engagements — a shared LangGraph plane, a hosted
control plane, a team instance. When it does, the ``$engagement`` predicate is
the only thing separating them, so these tests assert the two ways that
separation used to be bypassable:

* raw Cypher that simply omits the predicate reads every engagement's nodes, and
* caller-supplied ``params`` that carry their own ``engagement`` key override
  the trusted value the store resolved.

Both were reachable from an agent tool (``plan_attack_chains`` issues raw
Cypher through ``query_custom``), which is why they are guarded at the store
boundary rather than left to each caller.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from decepticon.middleware.kg_internal.store import KGStore, KGStoreConfig


def _fake_driver() -> MagicMock:
    driver = MagicMock(name="Driver")
    session = MagicMock(name="Session")
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = None
    session.execute_read.return_value = []
    session.execute_write.return_value = []
    return driver


def _make_store(driver: Any | None = None) -> KGStore:
    cfg = KGStoreConfig(uri="bolt://x", user="u", password="p", database="neo4j")
    return KGStore(cfg, driver=driver or _fake_driver())


SCOPED = "MATCH (n:Host) WHERE n.engagement = $engagement RETURN n"
UNSCOPED = "MATCH (n:Host) RETURN n"


@pytest.mark.parametrize("method", ["execute_read", "execute_write"])
def test_cypher_without_the_engagement_predicate_is_rejected(method: str) -> None:
    """The failure is loud and at the boundary — not a silently wider result set."""
    store = _make_store()
    with pytest.raises(ValueError, match="engagement"):
        getattr(store, method)(UNSCOPED, {}, engagement="eng_a")


@pytest.mark.parametrize("method", ["execute_read", "execute_write"])
def test_scoped_cypher_passes(method: str) -> None:
    store = _make_store()
    getattr(store, method)(SCOPED, {}, engagement="eng_a")


def test_caller_params_cannot_override_the_trusted_engagement() -> None:
    """A caller naming someone else's engagement must not win.

    The value the store resolved is authoritative; ``params`` may add to it but
    never replace it. Asserted on what actually reaches the driver, because the
    old bug was a dict-merge order — trusted value first, caller's spread over
    the top of it — which no return-value assertion would have caught.
    """
    driver = _fake_driver()
    store = _make_store(driver)
    session = driver.session.return_value.__enter__.return_value

    store.execute_read(SCOPED, {"engagement": "eng_victim"}, engagement="eng_caller")

    session.execute_read.assert_called_once()
    # The store hands the driver a callable; the params it closed over are what
    # the query will actually run with.
    sent = _params_sent_to_driver(session.execute_read.call_args)
    assert sent["engagement"] == "eng_caller"


def test_unrelated_caller_params_are_preserved() -> None:
    """Guarding the engagement key must not throw away the caller's own params."""
    driver = _fake_driver()
    store = _make_store(driver)
    session = driver.session.return_value.__enter__.return_value

    store.execute_read(
        "MATCH (n:Host) WHERE n.engagement = $engagement AND n.ip = $ip RETURN n",
        {"ip": "10.0.0.1", "engagement": "eng_victim"},
        engagement="eng_caller",
    )

    sent = _params_sent_to_driver(session.execute_read.call_args)
    assert sent["ip"] == "10.0.0.1"
    assert sent["engagement"] == "eng_caller"


def _params_sent_to_driver(call_args: Any) -> dict[str, Any]:
    """Run the unit-of-work the store passed to the session and capture its params."""
    work = call_args.args[0]
    tx = MagicMock(name="Transaction")
    tx.run.return_value = []
    work(tx)
    tx.run.assert_called_once()
    return dict(tx.run.call_args.kwargs) or dict(tx.run.call_args.args[1])
