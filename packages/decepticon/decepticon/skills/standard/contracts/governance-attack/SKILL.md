---
name: contracts-governance-attack
description: "DAO governance attack — flash-loan-backed vote manipulation, delegation hijack, quorum dilution, proposal-spam DoS, time-lock bypass via emergency multisig, snapshot vs. on-chain vote desync, Compound/Aave/Uniswap-style GovernorBravo abuse."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "dao governance vote proposal governorbravo compound aave uniswap snapshot timelock multisig delegation flash loan quorum"
  subdomain: contracts
  tags: defi, dao, governance, flash-loan
  mitre_attack: T1565.001, T1190
---

# DAO Governance Attack

## Attack classes

### 1. Flash-loan-backed vote
DAOs that grant voting power = current token balance (not snapshot of past balance) are vulnerable:

```solidity
// Attack: borrow governance token, vote, return loan, all in one tx
function attack() external {
    // 1. Flash-borrow gov tokens
    IFlashLoan(aave).flashLoan(address(this), govToken, 1_000_000e18, "");
}
function executeOperation(...) external {
    // 2. Vote on the malicious proposal
    governor.castVote(proposalId, 1);   // 1 = for
    // 3. Repay loan + premium (automatic by flash-loan callback)
}
```

This is what happened to Beanstalk (April 2022, $182M loss) — attacker flash-borrowed Beanstalk gov tokens, voted to drain the treasury, repaid the loan. Same block.

**Defense check:** Does `getVotes(address, blockNumber)` reference a past snapshot? If yes (Compound's GovernorBravo pattern, OZ Governor with `ERC20Votes` + `getPastVotes`), flash-loan vote doesn't work.

### 2. Delegation hijack
ERC20Votes lets users delegate. If a contract holds gov tokens and delegates to itself, controlling that contract = controlling the votes.

```solidity
// If the target DAO has a contract holding tokens that delegates to itself,
// and that contract is upgradeable/has an admin function:
upgradeableContract.upgradeAndCall(newImpl, abi.encodeWithSelector(redelegate.selector, attacker));
// Now attacker controls those votes.
```

### 3. Quorum dilution attack
If quorum = % of total supply (not % of currently-active voters), an attacker can mint or stake extra tokens to push quorum out of reach:

```solidity
// Some DAOs base quorum on totalSupply()
// Attacker mints a bunch of tokens to themselves (via legit minting if they're holder)
// Quorum requirement now too high for real voters to meet → all proposals fail
```

### 4. Proposal spam DoS
GovernorBravo has a proposalThreshold. If low, attacker spams proposals to:
- Burn proposers' gas
- Confuse the UI
- Push real proposals out of the active window

### 5. Time-lock bypass via emergency multisig
Most DAOs have a "Security Council" or "Emergency Multisig" that can execute without time-lock for emergencies. If signers can be socially engineered, phished, or are compromised: instant treasury drain.

Check: `timelock.executor()` — if it's a multisig and you can compromise N-of-M signers, the time-lock is illusory.

### 6. Snapshot vs. on-chain desync
Off-chain Snapshot.org votes use signed messages. If the DAO trusts Snapshot results and executes via a relayer:
- Forge votes by sniping pending signed messages
- Bribe voters off-chain (cheaper than on-chain)
- Replay signed messages on a fork

### 7. Proposal-script slippage
GovernorBravo proposals execute calldata. If the proposal description and the actual calldata don't match, voters approve one thing while approving another:

```solidity
// Description: "Allocate 1000 USDC to grants"
// Actual calldata: transfer(attacker, 1_000_000e6)
// Voters who don't decode calldata get rugged.
```

## Recon

```bash
# Identify the governance contract
cast call --rpc-url $RPC $TIMELOCK "getMinDelay()(uint256)"
cast call --rpc-url $RPC $GOVERNOR "votingPeriod()(uint256)"
cast call --rpc-url $RPC $GOVERNOR "proposalThreshold()(uint256)"
cast call --rpc-url $RPC $GOVERNOR "quorum(uint256)(uint256)" $BLOCK

# Compound/Aave/Uniswap-style: Get GovernorBravo state
forge inspect GovernorBravoDelegate storage-layout

# List active proposals
cast logs --rpc-url $RPC --address $GOVERNOR \
  --from-block latest:-1000 \
  "ProposalCreated(uint256,address,address[],uint256[],string[],bytes[],uint256,uint256,string)"
```

## Defender's checklist (the audit you're trying to defeat)

| Defense | Bypass |
|---|---|
| `getVotes` uses past-block snapshot | Can't flash-loan-vote — find delegation-hijack instead |
| Two-step time-lock (queue + execute) | Can't bypass without compromised emergency multisig |
| `proposalThreshold > 0` | Can't spam — but might still be cheap |
| Off-chain vote (Snapshot) → on-chain by N-of-M multisig | Replace at the multisig layer |

## Tooling

```bash
# Tally, Boardroom — DAO dashboards (find target governance contracts)
# Forge / Foundry — simulate the attack on a fork
forge test --fork-url $RPC --match-test test_governance_drain
# Tenderly — live transaction simulation against fork
```

## References

- "Beanstalk Governance Attack" post-mortems (Beanstalk Farms, April 2022)
- Compound GovernorBravo audit reports (OpenZeppelin)
- "Slippage in Governance Proposals" — Trail of Bits research
- Devcon Bogota talks on governance security
