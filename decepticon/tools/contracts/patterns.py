"""Solidity pattern scanner — offline DeFi bug heuristics.

Regex-level detection is imprecise but *useful as a first pass*: every
finding is returned with a line number and a suggestion for the exact
Slither/Foundry follow-up. The agent promotes confirmed findings into
the knowledge graph as ``vulnerability`` nodes.

Patterns cover:
- Reentrancy: external calls before state writes, lack of nonReentrant
- tx.origin auth
- Unchecked low-level calls
- Uninitialized storage pointers (old but still yields)
- delegatecall to user-controlled addresses
- block.timestamp used as randomness
- Hardcoded slippage / min-out of zero
- ecrecover returning address(0) without check (sig-replay)
- Missing access modifier on sensitive functions
- Integer narrow casts truncating large values
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from decepticon.tools.research.graph import Severity


@dataclass
class ContractFinding:
    """A single pattern match."""

    id: str
    rule: str
    severity: Severity
    line: int
    snippet: str
    description: str
    cwe: str | None = None
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule": self.rule,
            "severity": self.severity.value,
            "line": self.line,
            "snippet": self.snippet,
            "description": self.description,
            "cwe": self.cwe,
            "recommendation": self.recommendation,
        }


# ── Patterns ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Pattern:
    rule: str
    regex: re.Pattern[str]
    severity: Severity
    description: str
    cwe: str | None = None
    recommendation: str = ""


_PATTERNS: tuple[_Pattern, ...] = (
    _Pattern(
        rule="reentrancy.external-call-before-write",
        regex=re.compile(
            r"\.call\s*\{[^}]*value\s*:\s*[^}]*\}\(",
            re.IGNORECASE,
        ),
        severity=Severity.HIGH,
        description=(
            "Low-level .call{value:...} is used. Ensure state updates happen BEFORE the external "
            "call (checks-effects-interactions) and add ReentrancyGuard."
        ),
        cwe="CWE-841",
        recommendation="Move state updates above the external call; add nonReentrant modifier.",
    ),
    _Pattern(
        rule="auth.tx-origin",
        regex=re.compile(r"\btx\.origin\b"),
        severity=Severity.HIGH,
        description=(
            "tx.origin used for authorization. Phishing contracts can impersonate users via "
            "relayed calls."
        ),
        cwe="CWE-290",
        recommendation="Use msg.sender with access-controlled roles.",
    ),
    _Pattern(
        rule="delegatecall.unchecked-target",
        regex=re.compile(r"delegatecall\s*\(", re.IGNORECASE),
        severity=Severity.CRITICAL,
        description=(
            "delegatecall to a non-constant address lets the callee read/write this contract's "
            "storage — often catastrophic (parity multisig class)."
        ),
        cwe="CWE-829",
        recommendation="Only delegatecall to an immutable, audited implementation.",
    ),
    _Pattern(
        rule="randomness.block-timestamp",
        regex=re.compile(r"\b(block\.timestamp|now)\b"),
        severity=Severity.MEDIUM,
        description=(
            "block.timestamp / now used as entropy. Miners can influence timestamps within a "
            "~15s window."
        ),
        cwe="CWE-338",
        recommendation="Use Chainlink VRF or commit-reveal for randomness.",
    ),
    _Pattern(
        rule="signature.ecrecover-unchecked",
        regex=re.compile(r"ecrecover\s*\("),
        severity=Severity.MEDIUM,
        description=(
            "ecrecover can return address(0) on malformed input. Unchecked callers accept "
            "zero-address signatures as valid."
        ),
        cwe="CWE-347",
        recommendation='require(recovered != address(0), "bad sig") immediately after ecrecover.',
    ),
    _Pattern(
        rule="proxy.uninitialized-impl",
        regex=re.compile(r"\binitialize\b\s*\([^)]*\)\s*(external|public)"),
        severity=Severity.HIGH,
        description=(
            "initialize() is public/external. Upgradeable proxies must invoke initialize() in the "
            "same transaction as deployment OR guard it with the Initializable modifier."
        ),
        cwe="CWE-665",
        recommendation="Add `initializer` modifier from OZ Initializable and call _disableInitializers() in the implementation constructor.",
    ),
    _Pattern(
        rule="access.missing-modifier",
        regex=re.compile(
            r"function\s+\w+\s*\([^)]*\)\s*(public|external)(?!.*(onlyOwner|onlyRole|onlyAdmin|nonReentrant|whenNotPaused|only\w+))",
        ),
        severity=Severity.MEDIUM,
        description=(
            "Public/external function without an access modifier. Confirm it is intentionally "
            "callable by anyone."
        ),
        cwe="CWE-284",
        recommendation="Add an access modifier, or comment why it is intentionally permissionless.",
    ),
    _Pattern(
        # Matches a narrowing cast expression like `uint128(big)` where the
        # argument is an identifier. We can't prove the source is uint256
        # from syntax alone, so this is a best-effort heuristic — the agent
        # confirms via Slither.
        rule="math.unchecked-cast",
        regex=re.compile(r"\buint(?:8|16|32|64|128)\s*\(\s*\w+\s*\)"),
        severity=Severity.MEDIUM,
        description=(
            "Narrowing uint → smaller uint without SafeCast. Values above the target range "
            "wrap silently and can bypass checks."
        ),
        cwe="CWE-197",
        recommendation="Use OZ SafeCast.toUintNN or explicit range check.",
    ),
    _Pattern(
        rule="flashloan.callback-no-auth",
        regex=re.compile(
            r"function\s+(executeOperation|onFlashLoan|flashLoanCallback)\s*\([^)]*\)\s*(external|public)"
        ),
        severity=Severity.HIGH,
        description=(
            "Flash loan callback without an initiator check. Attackers can directly call it to "
            "impersonate an in-progress flash loan."
        ),
        cwe="CWE-306",
        recommendation="require(msg.sender == address(LENDING_POOL)) and require(initiator == address(this)).",
    ),
    _Pattern(
        rule="oracle.single-source-price",
        regex=re.compile(r"(getPrice|latestAnswer|slot0|getReserves)\s*\("),
        severity=Severity.MEDIUM,
        description=(
            "Reads from a single on-chain price source without TWAP or secondary oracle. "
            "Manipulable via large swaps / flash loans."
        ),
        cwe="CWE-345",
        recommendation="Use Chainlink with heartbeat check + a TWAP fallback.",
    ),
    _Pattern(
        rule="call.return-ignored",
        regex=re.compile(r"\b(bool\s+success,\s*bytes\s+memory\s*\w*\s*=\s*)?\w+\.call\b[^;]*;"),
        severity=Severity.LOW,
        description=(
            "Low-level call result not explicitly required to be true. Failing external calls "
            "may be silently ignored."
        ),
        cwe="CWE-252",
        recommendation="require(success) after every .call().",
    ),
)


# ── Scanner ─────────────────────────────────────────────────────────────


def scan_solidity_source(source: str) -> list[ContractFinding]:
    """Run every pattern against ``source`` and return findings ordered by
    line number. The same span may trigger multiple rules; that's fine —
    the agent decides which to promote.
    """
    findings: list[ContractFinding] = []
    lines = source.splitlines()
    idx = 0
    for pat in _PATTERNS:
        for m in pat.regex.finditer(source):
            # Compute 1-based line number
            line_no = source[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:160] if line_no - 1 < len(lines) else ""
            idx += 1
            findings.append(
                ContractFinding(
                    id=f"sol-{idx:04d}",
                    rule=pat.rule,
                    severity=pat.severity,
                    line=line_no,
                    snippet=snippet,
                    description=pat.description,
                    cwe=pat.cwe,
                    recommendation=pat.recommendation,
                )
            )
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings
