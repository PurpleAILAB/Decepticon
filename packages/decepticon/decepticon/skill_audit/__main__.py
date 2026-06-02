"""``python -m decepticon.skill_audit`` entrypoint."""

from __future__ import annotations

import sys

from decepticon.skill_audit.cli import main

if __name__ == "__main__":
    sys.exit(int(main()))
