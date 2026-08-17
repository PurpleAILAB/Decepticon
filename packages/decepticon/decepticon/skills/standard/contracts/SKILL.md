---
name: contracts-overview
description: Smart contract audit lane — Solidity/EVM pattern scanner, Slither ingestion, Foundry PoC generation, DeFi attack playbooks.
metadata:
  subdomain: smart-contracts
  when_to_use: "smart contract solidity evm slither foundry defi audit lane overview routing"
  mitre_attack:
    - T1190
    - T1565
    - T1565.001
  capability_contract:
    lane: web3
    scope: isolated-lab
    environment: [anvil, forked-chain]
    required_tools: [forge, slither]
    evidence: [foundry-poc, evm-trace, patched-build-result]
    verification: "run the exploit test against the exact deployment or pinned fork"
    negative_control: "run the baseline test without the exploit precondition"
    scorecard: [validated-rate, patched-build-non-repro-rate, unique-root-causes]
    benchmark: held-out-web3
---

# Smart Contract Audit Catalog

## Playbooks
| Skill | Use for |
|---|---|
| `/skills/standard/contracts/reentrancy/SKILL.md`         | Classic + read-only reentrancy |
| `/skills/standard/contracts/oracle-manipulation/SKILL.md`| Single-block TWAP / spot price abuse |
| `/skills/standard/contracts/flash-loan/SKILL.md`         | Flash-loan callback + unauth gadgets |
| `/skills/standard/contracts/access-control/SKILL.md`     | Missing modifiers, wrong msg.sender |
| `/skills/standard/contracts/upgradeable-proxy/SKILL.md`  | Uninitialized impl, storage clash |
| `/skills/standard/contracts/signature-replay/SKILL.md`   | Cross-chain, ecrecover zero address |

## Workflow
1. Map the target: `bash("find /workspace/src -name '*.sol' | head -50")`
2. `solidity_scan_file` on each file
3. Run slither: `bash("cd /workspace && slither . --json slither.json")`
4. `slither_ingest("/workspace/slither.json")`
5. `kg_query(kind="vulnerability", min_severity="high")` to see the highs
6. For each high, generate a Foundry PoC via `foundry_reentrancy_test` etc.
7. `bash("forge test -vvv --match-contract Test_")` to run
8. Promote passing PoCs as validated findings

## Default severity floor
| Impact                         | CVSS / Reward tier |
|--------------------------------|--------------------|
| Loss of user funds             | Critical (9.8+)    |
| Locked funds / permanent DoS   | High (7.5-9.0)     |
| Temporary DoS / griefing       | Medium (5-7)       |
| View-only data leak            | Low (3-5)          |
