---
name: oracle-manipulation
description: Hunt single-block oracle manipulation — spot-price AMM oracles, manipulable TWAP, dependent calculations, missing staleness checks.
metadata:
  subdomain: smart-contracts
  when_to_use: "oracle manipulation twap price bypass"
  mitre_attack:
    - T1565.001
    - T1190
---

# Oracle Manipulation Playbook

DeFi protocols that read a price from an on-chain source are
vulnerable when the source can be moved within a single transaction
or block. Classic vectors:

1. **Spot-price AMM oracle** — `reserve1 / reserve0` of a Uniswap V2 pool. Anyone with enough capital (or a flash loan) can push the price for one block.
2. **Manipulable TWAP** — short window TWAP, or TWAP over a low-liquidity pool.
3. **Single Chainlink feed without staleness check** — feed returns 0 / stale → uses 0 in math.
4. **Custom oracle reading from manipulable storage** — e.g., a "fair-price" oracle that reads `totalSupply()` of an LP token alongside reserves.
5. **L2 sequencer offline** — L2 oracles need a "is sequencer up?" check or attacker can exploit when sequencer downs and feeds freeze.

## Audit steps

### 1. Locate price-reading code
```bash
# Common patterns
grep -rn 'getReserves\|getAmountsOut\|getPriceFromSqrtPriceX96\|latestAnswer\|latestRoundData' src/

# Custom oracle reads
grep -rn 'IPriceOracle\|getPrice\|consult' src/
```

### 2. Trace each price use
For each call:
- Is the price read from a Uniswap V2 / Sushi / Camelot pool's reserves?
  → spot price = manipulable
- Is the price read from a Uniswap V3 pool's `slot0.sqrtPriceX96`?
  → manipulable
- Is it a Uniswap V3 TWAP via `OracleLibrary.consult`?
  → check the secondsAgo window (>= 1800s = 30 min is the safe minimum)
- Is it a Chainlink `latestRoundData()` call?
  → check: is `updatedAt` validated? Is `answeredInRound >= roundId`? Is `answer > 0`? Are L2 sequencer feeds checked?

### 3. Validate staleness handling
```solidity
// MISSING — vulnerable
(, int256 price, , , ) = priceFeed.latestRoundData();

// GOOD — explicit staleness + sequencer
(uint80 roundId, int256 price, , uint256 updatedAt, uint80 answeredInRound) = priceFeed.latestRoundData();
require(price > 0, "ORACLE_NEGATIVE");
require(updatedAt > block.timestamp - MAX_DELAY, "ORACLE_STALE");
require(answeredInRound >= roundId, "ORACLE_OLD_ROUND");
// On L2: also check sequencer uptime feed (L2 SequencerUptimeFeed)
```

### 4. Trace the price's use
The bug isn't oracle-reading — it's oracle-trusting. Find where the
price drives a state change:
- Liquidation thresholds
- Collateral valuation
- Borrow limits
- Swap output amounts (slippage check)
- LP token pricing for vaults

## PoC via Foundry

### Flash-loan price push (Uniswap V2 reserves)
```solidity
// Pseudo:
contract Test_oracle is Test {
    function test_manipulate() public {
        // 1. Flash-loan WETH from Aave / Balancer / Uniswap V3
        // 2. Swap WETH → token in target pool, draining one side
        // 3. Reserves now skewed → spot price way off
        // 4. Call vulnerable protocol's price-dependent function
        //    (e.g., borrow USDC against overvalued collateral)
        // 5. Reverse the swap, repay flash loan
        // 6. Profit = whatever was extracted in step 4
        assertGt(USDC.balanceOf(attacker), 0, "should profit");
    }
}
```

Decepticon helper:
```
foundry_oracle_test(target="LendingPool", price_feed="UniV2Pair",
                    token0="WETH", token1="TARGETTOKEN", target_path="src/LendingPool.sol")
```

### Chainlink stale check missing
```solidity
function test_stale_price() public {
    // mock the feed to return updatedAt that's 24h old
    vm.mockCall(
        address(priceFeed),
        abi.encodeWithSignature("latestRoundData()"),
        abi.encode(uint80(1), int256(STALE_PRICE), uint256(0), block.timestamp - 86400, uint80(1))
    );

    // call function — should revert if staleness checked, should proceed if not
    target.priceDependentFunction();
    // If we reach here w/o revert → bug
}
```

## Severity calibration

| Manipulation surface | Typical impact | Severity |
|---|---|---|
| Spot-price oracle drives liquidation | Drain LPs via fake liquidations | Critical |
| Spot-price drives borrow limit | Borrow more than collateral worth | Critical |
| TWAP < 30 min | Still manipulable on low-liquidity pairs | High |
| TWAP 30 min+ on high-liquidity ETH-USDC | Hard to exploit profitably | Medium-Low |
| Missing staleness check, but feed updates often | Edge-case impact during outages | Medium |
| L2 sequencer not checked | Exploitable during sequencer downtime | High (timing-dependent) |

## CVSS
- Spot-oracle + flash-loan available + drains protocol: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = 10.0 (Crit)
- 30-min TWAP on illiquid pair: 7-8 (High)
- Missing staleness + Chainlink usually fresh: 5-6 (Medium)

## Defender remediation
```solidity
// Use Chainlink properly, not spot-price
function getPrice() internal view returns (uint256) {
    (uint80 roundId, int256 answer, , uint256 updatedAt, uint80 answeredInRound)
        = priceFeed.latestRoundData();
    require(answer > 0, "neg price");
    require(updatedAt > block.timestamp - 1 hours, "stale");
    require(answeredInRound >= roundId, "old round");
    // L2 only:
    (, int256 sequencerStatus, , uint256 sequencerStart, ) = sequencerFeed.latestRoundData();
    require(sequencerStatus == 0, "sequencer down");
    require(block.timestamp - sequencerStart > 1 hours, "grace period");
    return uint256(answer);
}

// Where Chainlink unavailable: use 30+ min Uniswap V3 TWAP w/ deep-liquidity pool
function getTwap(uint32 secondsAgo) internal view returns (uint160 sqrtPriceX96) {
    (int24 arithmeticMeanTick, ) = OracleLibrary.consult(pool, secondsAgo);
    return TickMath.getSqrtRatioAtTick(arithmeticMeanTick);
}
```

## Known exemplars
- bZx Feb 2020: $645k via Synthetix sUSD spot-price oracle
- Harvest Finance Oct 2020: $24M via Curve pool spot price
- Cream Oct 2021: $130M via Yearn share-price manipulation
- Mango Markets Oct 2022: $114M via MNGO spot price on AMM
- Avraham Eisenberg's pattern, exactly: deposit small collateral, manipulate oracle, borrow against inflated value
- Inverse Finance Apr 2022: $15M via INV/ETH spot price
- Beanstalk Apr 2022: $182M via governance + flash-loan oracle (different but related)
