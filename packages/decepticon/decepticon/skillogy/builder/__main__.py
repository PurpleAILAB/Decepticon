"""``python -m decepticon.skillogy.builder`` entrypoint."""

from __future__ import annotations

import sys

from decepticon.skillogy.builder.cli import main

if __name__ == "__main__":
    sys.exit(int(main()))
