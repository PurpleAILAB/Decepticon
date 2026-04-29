"""Scratch-prune failures must produce warning logs (not silent pass)."""

import asyncio
import importlib
import logging
import time
from unittest.mock import MagicMock

bash_mod = importlib.import_module("decepticon.tools.bash.bash")


def test_prune_failure_logged_as_warning(caplog):
    sandbox = MagicMock()
    sandbox.execute = MagicMock(side_effect=RuntimeError("docker exec failed"))
    bash_mod.set_sandbox(sandbox)
    # Force the throttle to pass: place the last prune well before now-SCRATCH_PRUNE_INTERVAL.
    # Plain 0.0 fails on hosts where time.monotonic() < SCRATCH_PRUNE_INTERVAL (fresh boot).
    bash_mod._last_scratch_prune = time.monotonic() - bash_mod.SCRATCH_PRUNE_INTERVAL - 1

    # Project's "decepticon" parent logger sets propagate=False; restore for caplog.
    parent = logging.getLogger("decepticon")
    child = logging.getLogger("decepticon.tools.bash.bash")
    parent_was, child_was = parent.propagate, child.propagate
    parent.propagate = True
    child.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger="decepticon.tools.bash.bash"):
            asyncio.run(bash_mod._prune_old_scratch())
    finally:
        parent.propagate = parent_was
        child.propagate = child_was

    assert any("scratch prune failed" in rec.message.lower() for rec in caplog.records), (
        f"Expected warning log; got {[r.message for r in caplog.records]}"
    )
