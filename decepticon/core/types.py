"""Decepticon common types and enums."""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """Roles for specialized agents."""

    RECON = "recon"
    EXPLOIT = "exploit"
    POSTEXPLOIT = "postexploit"
    DECEPTICON = "decepticon"
