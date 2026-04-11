"""Smart contract audit package.

Offline pattern scanner + Slither JSON ingestion + Foundry harness
generator for Solidity/EVM targets. Focus on the DeFi bug classes that
actually win bounties:

- Reentrancy (classic + read-only)
- Oracle manipulation
- Flash loan abuse
- Access control gaps (missing onlyOwner / role checks)
- Upgradeable-proxy storage clashes
- Signature replay across chains
- Integer truncation / math rounding

Everything here runs in pure Python against source strings so tests
can cover the detection logic without a Foundry toolchain.
"""

from __future__ import annotations

from decepticon.tools.contracts.foundry import (
    FoundryHarness,
    generate_reentrancy_test,
)
from decepticon.tools.contracts.patterns import (
    ContractFinding,
    scan_solidity_source,
)
from decepticon.tools.contracts.slither import ingest_slither_json

__all__ = [
    "ContractFinding",
    "FoundryHarness",
    "generate_reentrancy_test",
    "ingest_slither_json",
    "scan_solidity_source",
]
