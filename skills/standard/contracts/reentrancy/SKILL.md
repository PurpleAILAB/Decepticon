---
name: reentrancy
description: Hunt and validate reentrancy bugs — classic cross-function, same-function, read-only, and cross-contract variants.
---

# Reentrancy Playbook

## Variants
1. **Classic** — external call before state update (The DAO)
2. **Cross-function** — A calls out, reentered into B which reads/writes A's state
3. **Read-only** — view function reads stale state during reentrancy, consumed by a second contract making decisions
4. **Cross-contract** — same attack pattern across protocol boundaries
5. **ERC777 / ERC1155 hook** — `onERC*Received` callback re-enters

## Audit steps
1. `solidity_scan_file` flags every `.call{value:...}` and `delegatecall`
2. For each hit, check:
   - Is there a state write BEFORE the external call?
   - Is `ReentrancyGuard`'s `nonReentrant` modifier applied?
   - Does it follow checks-effects-interactions?
3. Trace call graph — if any function the call target can invoke reads
   or writes the same state slot, that's a reentrancy chain.

## PoC via Foundry
```
foundry_reentrancy_test(target="Vault", function="withdraw", target_path="src/Vault.sol")
```
Then:
```bash
cp generated.t.sol /workspace/foundry/test/
cd /workspace/foundry && forge test -vvv --match-contract Test_withdraw
```

## Success criteria
The attacker contract balance grows by more than its initial deposit
after the attack transaction. The Foundry test should assert this.

## CVSS
- Direct fund drain: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = 10.0
- Read-only with downstream impact: 8.1-9.1 depending on impact

## Known exemplars
- The DAO (2016)
- Lendf.Me (2020, ERC777 hook reentrancy, $25M)
- Cream Finance (2021)
- Rari Capital (2022)
- Curve pool read-only reentrancy (2023)
