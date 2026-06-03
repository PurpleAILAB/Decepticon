"""IdentityProvider — source of attribution metadata for outbound traffic.

Used by the bugclaw orchestrator (and any future identity-attribution
middleware). Every outbound HTTP call gets a User-Agent + engagement
header derived from the active provider's outputs.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["IdentityProvider"]


@runtime_checkable
class IdentityProvider(Protocol):
    """Returns attribution strings for outbound traffic."""

    def outbound_user_agent(self, engagement_id: str) -> str:
        """RFC 7231-shaped User-Agent value.

        Examples:
            ``bugclaw/0.1 (+https://hackerone.com/purpleailab; eng=42)``
            ``decepticon/pentest (+contract=ACME-2026; eng=42)``
        """
        ...

    def callback_domain_prefix(self) -> str:
        """Hostname/suffix where blind-callback subdomains live.

        Lets triagers attribute callback traffic back to us.
        Example: ``callbacks.bugclaw.purpleailab.com``.
        """
        ...
