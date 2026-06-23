"""Skillogy - skill-as-a-service for Decepticon.

Skillogy externalizes Decepticon's skill catalog out of the agent process
and into a dedicated service that speaks both gRPC and REST. The current
file-system-backed ``SkillsMiddleware`` reads SKILL.md files at agent boot
and again at each ``load_skill()`` invocation; Skillogy replaces that with
a network call to a long-lived service that owns the canonical registry.

Why
---
1. Multi-tenant deployments need per-tenant skill subsets. File-system
   skills cannot be sliced per request without remounting volumes.
2. Hot-swap: dropping a new skill into a running engagement requires
   restarting the langgraph container today; Skillogy makes it an HTTP
   POST.
3. Non-Python agents: future Go / Rust / TypeScript agent runtimes need a
   wire protocol to consume the same skill corpus. gRPC + REST gives both.
4. Audit trail: every skill load becomes a logged API call instead of an
   invisible file read.

Layout
------
- ``proto/`` - canonical .proto definitions + the hand-rolled Python
  message types until protoc generation is wired into the build.
- ``server/`` - FastAPI app (REST) + grpcio service (gRPC). Backed by an
  in-memory registry that an ingester populates at startup.
- ``client/`` - REST and gRPC clients. Used by the middleware.
- The new ``SkillogyMiddleware`` lives in
  ``decepticon.middleware.skillogy`` to mirror the existing
  ``SkillsMiddleware`` location, with an opt-in switch via
  ``DECEPTICON_USE_SKILLOGY=1``.
"""

from decepticon.skillogy.proto import (
    SkillEnvelope,
    SkillListRequest,
    SkillListResponse,
    SkillLoadRequest,
    SkillMeta,
)

__all__ = [
    "SkillEnvelope",
    "SkillListRequest",
    "SkillListResponse",
    "SkillLoadRequest",
    "SkillMeta",
]
