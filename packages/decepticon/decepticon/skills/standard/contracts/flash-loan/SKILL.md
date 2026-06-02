---
name: flash-loan
description: Flash-loan exploit patterns — callback reentrancy, oracle amplification, governance attacks, unauthenticated callback handlers.
metadata:
  subdomain: smart-contracts
  when_to_use: "flash loan aave dydx balancer composition"
  mitre_attack:
    - T1190
    - T1565.001
---

# Flash Loan Attack Playbook

Flash loans give the attacker uncollateralized capital for a single
transaction. They're not vulnerabilities themselves — they're a force
multiplier for existing bugs. Sources: Aave, Balancer, Uniswap V2/V3,
Maker, dYdX (deprecated).

## Common attack patterns

### 1. Oracle amplification (most common)
Use loan to push a price, then trigger price-dependent action.
**Cross-reference**: see `oracle-manipulation/SKILL.md`.

### 2. Unauthenticated callback handler
```solidity
function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,                     // ← UNVALIDATED in many contracts
    bytes calldata params
) external returns (bool) {
    // Anyone can call this with fake `initiator`
    // and have the contract do whatever the params say
}
```
**Bug**: `initiator` and `msg.sender == pool` checks are missing.
**Attack**: call `executeOperation` directly with no actual loan, malicious `params` → contract does the operation anyway.

### 3. Governance attack via flash loan
```solidity
// Vulnerable governance:
function propose() external {
    require(getVotes(msg.sender) > THRESHOLD);
    // ...
}
function getVotes(address user) public view returns (uint256) {
    return token.balanceOf(user);  // ← reads SPOT balance, not snapshot
}
```
**Attack**: flash-loan governance tokens, propose malicious change (e.g., upgrade contract to drain), vote with the loaned tokens, execute, repay loan. **MakerDAO** had this pattern; mitigated by checkpoint-based voting.

### 4. Liquidity manipulation
Pool that uses `totalSupply()` or `balanceOf(pool)` for share math:
```solidity
function deposit(uint256 amt) external {
    uint256 shares = (amt * totalSupply()) / underlying.balanceOf(address(this));
    _mint(msg.sender, shares);
    underlying.transferFrom(msg.sender, address(this), amt);
}
```
Attacker:
1. Flash-loan and deposit (becomes 99% of pool)
2. Donate underlying to inflate `underlying.balanceOf` artificially
3. Next depositor's shares = `amt * totalSupply / inflatedBalance` ≈ 0
4. Withdraw → drain
This is the **ERC4626 inflation attack** (also covered in `reentrancy/` overlap).

### 5. Liquidation arbitrage gone wrong
A liquidator that uses flash loans to repay debt before claiming
collateral — usually benign. The bug: liquidation health check happens
*before* the seizure, but the seizure happens via callback into a
manipulable function. Reentrancy + oracle dependent.

## Audit steps

### 1. Locate flash-loan integrations
```bash
grep -rn 'executeOperation\|flashLoan\|onFlashLoan\|flashCallback\|aaveFlashLoan' src/
```

### 2. For each handler
Check:
- `msg.sender == known_pool` (whitelist callback origin)
- `initiator == address(this)` (only respond to your own loans)
- ReentrancyGuard on the public function that *takes* the loan
- The fee is correctly accounted (`amounts[i] + premiums[i]` is repaid)

### 3. For each price-reading function
See `oracle-manipulation/SKILL.md`.

### 4. For each share-mint / share-burn function
Check `ERC4626` virtual-shares mitigation:
```solidity
// OpenZeppelin ERC4626 v4.7+
function _convertToShares(uint256 assets, MathUpgradeable.Rounding rounding) internal view virtual override returns (uint256) {
    return _initialConvertToShares(assets, rounding);  // adds 10**18 to total supply for share calc
}
```
If using legacy ERC4626 or custom vault math, write a Foundry test that:
1. Attacker deposits 1 wei → gets 1 share
2. Attacker direct-transfers 1e18 underlying to vault
3. Victim deposits 1e18 → gets 0 shares (rounding)
4. Attacker withdraws 1 share → gets 100% of pool

```
foundry_inflation_test(vault_address="...", underlying="...", target_path="src/Vault.sol")
```

## Severity calibration

| Pattern | Severity if confirmed |
|---|---|
| Unauth callback handler → arbitrary execution | Critical 10.0 |
| Flash-loan oracle manipulation drains protocol | Critical 9-10 |
| Governance attack possible | Critical 9-10 (if exec results in fund loss) |
| ERC4626 inflation attack on live vault | Critical 9 |
| Liquidation reentrancy via callback | High 8 |
| Theoretical (low liquidity, manipulation cost > attack profit) | Medium-Low |

## PoC template (Foundry)
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";
import "@aave-v3/interfaces/IPool.sol";

contract Test_FlashAttack is Test {
    IPool constant AAVE = IPool(0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2);
    address constant TARGET = 0x...;
    address constant ATTACKER = address(0xBEEF);

    function setUp() public {
        vm.createSelectFork("https://eth-mainnet.../<block>");
    }

    function test_drain() public {
        vm.startPrank(ATTACKER);
        uint256 beforeBal = WETH.balanceOf(ATTACKER);

        // Request 10000 WETH flash loan
        address[] memory assets = new address[](1);
        assets[0] = address(WETH);
        uint256[] memory amts = new uint256[](1);
        amts[0] = 10000 ether;
        uint256[] memory modes = new uint256[](1);  // 0 = repay full

        AAVE.flashLoan(address(this), assets, amts, modes, address(this), "", 0);

        uint256 afterBal = WETH.balanceOf(ATTACKER);
        assertGt(afterBal, beforeBal + 100 ether, "should profit");
    }

    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata
    ) external returns (bool) {
        // 1. Use loaned funds to manipulate TARGET
        // 2. Profit
        // 3. Repay
        IERC20(assets[0]).approve(address(AAVE), amts[0] + premiums[0]);
        return true;
    }
}
```

## OPSEC (operational, not blue team — this is on-chain)
Flash-loan attacks leave a single transaction trail visible to:
- Mempool watchers / Flashbots inspectors
- MEV bots that may front-run if not using private mempool
- Risk dashboards (DefiLlama, Forta, Cyfrin)

For audit-PoC purposes (not live exploit) just use a forked anvil.

## Defender remediation
1. **Snapshot-based governance** — vote based on historical balance, not spot
2. **TWAP oracles only** — never spot price for trust-critical decisions
3. **Validate flash callback origin** — `require(msg.sender == knownPool && initiator == address(this))`
4. **ERC4626 OpenZeppelin v4.7+** — virtual shares mitigation
5. **Initial deposit by deployer** — seed the vault with 10**18 underlying before opening, makes inflation impractical

## Known exemplars
- bZx 1 (Feb 2020): $350k flash-loan oracle attack
- bZx 2 (Feb 2020): $645k Synthetix sUSD attack
- Beanstalk (Apr 2022): $182M flash-loan governance attack
- Euler (Mar 2023): $197M; donateToReserves bug + flash loan
- Mango (Oct 2022): $114M oracle + flash loan
- Cream (Oct 2021): $130M via yUSD oracle
- KyberSwap (Nov 2023): $48.5M via concentrated-liquidity edge case + flash loan
