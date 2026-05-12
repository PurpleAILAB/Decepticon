"""Local-filesystem atomic write helper.

Scope: host / local filesystem only.

Intended callers:
  - EngagementBundle.save() (fixtures / tests)
  - Go launcher migration (the launcher reads this indirectly via the host
    bind-mount into the sandbox container)

NOT for use inside in-container tools such as complete_engagement_planning,
which writes the .bundle_complete marker via DockerSandbox (docker exec / cp)
so the write lands on the sandbox container filesystem — the only filesystem
where mtime ordering with roe.json / conops.json / deconfliction.json is
guaranteed to be consistent.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically via a temp file + os.replace.

    Creates parent directories if they do not exist. On POSIX, os.replace is
    a guaranteed atomic rename as long as the source and destination are on the
    same filesystem (guaranteed here because the temp file is created in the
    same directory as *path*). Callers reading *path* from another process will
    never observe a partially written file.

    On failure the temp file is cleaned up before the exception propagates.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_str, path)
    except Exception:
        try:
            os.unlink(tmp_str)
        except OSError:
            pass  # best-effort cleanup; suppress so original exception propagates
        raise
