---
name: contracts-mev-sandwich
description: "MEV sandwich attacks — front-run + back-run a victim swap on Uniswap V2/V3, Curve, Balancer; mempool monitoring via Flashbots / private RPC, slippage tolerance exploitation, JIT liquidity sandwich, multi-block MEV."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "mev sandwich front-run back-run uniswap v2 v3 curve balancer slippage flashbots private mempool jit liquidity searcher"
  subdomain: contracts
  tags: defi, mev, front-running, dex
  mitre_attack: T1565.002
---

# MEV Sandwich Attack

You observe a victim's DEX swap in the mempool. Sandwich it: buy the same token before the victim (pushing price up), let the victim swap at a worse price, then sell after them.

## Detect a sandwichable swap

```python
# Stream pending transactions
from web3 import Web3
w3 = Web3(Web3.HTTPProvider("https://eth.merkle.io"))
# Or: subscribe to alchemy/blocknative streams

# Filter for Uniswap V2 swapExactTokensForTokens or V3 exactInputSingle
# Look at the swap amount + slippage tolerance (deadline + minAmountOut)
# Sandwichable when: swap_amount * slippage > sandwich_gas_cost * 2
```

Math: profitable when victim's slippage tolerance exceeds your gas cost. Typical threshold for ETH/USDC swaps: victim swap >$10k with >1% slippage.

## Construct the sandwich bundle

```solidity
// Bundle: 3 tx in same block, in order
// 1. attacker_tx_1: swap baseToken -> token (push price UP)
// 2. victim_tx:     swap baseToken -> token (worse price now)
// 3. attacker_tx_2: swap token -> baseToken (sell back at higher price)
```

```javascript
// Flashbots bundle (Ethereum mainnet — others have similar private RPCs)
const ethers = require("ethers");
const { FlashbotsBundleProvider } = require("@flashbots/ethers-provider-bundle");

const provider = new ethers.providers.JsonRpcProvider(process.env.RPC);
const wallet = new ethers.Wallet(process.env.PK, provider);
const fb = await FlashbotsBundleProvider.create(provider, wallet, "https://relay.flashbots.net");

const blockNumber = await provider.getBlockNumber();
const bundle = [
  { signer: wallet, transaction: attackerTx1 },  // front-run
  { signedTransaction: rawVictimTx },             // victim from mempool
  { signer: wallet, transaction: attackerTx2 },  // back-run
];

const signedBundle = await fb.signBundle(bundle);
await fb.sendRawBundle(signedBundle, blockNumber + 1);
```

## JIT (Just-In-Time) liquidity sandwich

Uniswap V3 concentrated liquidity lets you provide liquidity in a tight range for one block:

```solidity
// 1. Just before victim's swap: mint a position concentrated at victim's price
// 2. Victim swaps — your liquidity earns 100% of the fee
// 3. Just after: burn the position
// No price-impact risk; pure fee capture.
```

Works when victim's swap is large enough that the fee exceeds gas + capital cost.

## Multi-block MEV

Cross-block sandwiches when validator is also the searcher (or in collusion):

```
Block N:    attacker front-run TX
Block N+1:  victim's TX (separate user, expects same price)
Block N+2:  attacker back-run TX
```

Requires builder/searcher cooperation. PBS (proposer-builder separation) on Ethereum makes this harder; still works on chains with single-block validators.

## Defenses that break sandwiches (what to look for as "harder targets")

- Victim uses private mempool (Flashbots Protect, MEV-Blocker, bloXroute Private Tx)
- Victim contract has tight `minAmountOut` (low slippage like 0.1%)
- DEX uses commit-reveal (rare)
- Threshold encryption mempools (Shutter, etc.)

## Common pitfalls (sandwich-of-sandwich = your sandwich gets sandwiched)

- Don't broadcast your sandwich publicly — always use Flashbots / private relay
- Other searchers also see the victim — outbid them via gas price + priority fee
- Don't sandwich your own user's swap from same Address — easy attribution

## Tooling

- `mev-inspect-py` (Flashbots) — historical sandwich detection (defender + reverse research)
- `mev-share` — partial-order-flow ecosystem
- `searcher-sage` — open-source sandwich bot patterns
- `Eigenphi` — MEV analytics dashboard (for reconning known searcher patterns)

## OPSEC / ethics / legal

- Sandwich attacks are public mempool predation, generally legal but ethically grey. In bounty context: **only ever test on test networks or on a target you own.**
- For research / detection: use mev-inspect-py against historical blocks; no harm.
- Some chains (e.g., Solana / Jito) have different MEV architectures — adapt accordingly.

## References

- "Flash Boys 2.0" (Daian et al., 2019) — original MEV academic paper
- Flashbots docs — docs.flashbots.net
- "MEV Wiki" — github.com/flashbots/mev-research
- EthCC / Devcon talks: search "MEV" on YouTube
