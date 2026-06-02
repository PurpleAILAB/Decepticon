---
name: signature-replay
description: Signature replay attacks — missing nonces, missing chain ID, ecrecover zero address, signature malleability, cross-chain replay.
metadata:
  subdomain: smart-contracts
  when_to_use: "signature replay eip-712 nonce smart contract"
  mitre_attack:
    - T1556
    - T1190
---

# Signature Replay Playbook

EIP-712 signatures, permits, meta-transactions, and cross-chain bridges
all use `ecrecover` (or its variants). Each has well-known bugs.

## Bug classes

### 1. Missing nonce → replay
```solidity
function execute(uint256 amount, bytes calldata sig) external {
    bytes32 h = keccak256(abi.encodePacked(msg.sender, amount));
    address signer = ecrecover(h, ...);
    require(signer == owner);
    // ... withdraw amount
}
```
A valid signature can be replayed forever — anyone who saw it once can
re-submit it. **Fix**: include a per-user / per-message nonce:
```solidity
mapping(address => uint256) public nonces;
function execute(uint256 amount, uint256 nonce, bytes calldata sig) external {
    require(nonce == nonces[msg.sender]);
    nonces[msg.sender]++;
    bytes32 h = keccak256(abi.encodePacked(msg.sender, amount, nonce));
    // ...
}
```

### 2. Missing chain ID → cross-chain replay
A signature valid on Ethereum mainnet shouldn't work on Optimism, Base,
Arbitrum, etc. If `chainid()` not in the signed payload, signatures
replay across chains:
```solidity
// VULNERABLE
bytes32 h = keccak256(abi.encodePacked(amount, deadline, nonce));

// SAFE — EIP-712 domain separator includes chainid
bytes32 h = _hashTypedDataV4(...);  // OZ helper
```

This is especially bad for **bridges** — a signed message intended for
chain A executes on chain B.

### 3. Signature malleability (ecrecover variants)
`ecrecover` accepts two valid `s` values for any signed message
(`s` and `-s mod n`). This means each signature has two valid forms.
If your contract uses the signature itself as a uniqueness key
(e.g., `usedSigs[sig] = true`), an attacker can find the malleable
version and bypass:
```solidity
// VULNERABLE — uses sig as uniqueness key
mapping(bytes => bool) public used;
function execute(bytes calldata sig) external {
    require(!used[sig]);
    used[sig] = true;
    address signer = ecrecover(...);
    // ...
}
```
**Fix**: use the message hash (not the signature) as uniqueness key.
Modern OZ ECDSA library rejects high-`s` values, but home-rolled
`ecrecover` does not.

### 4. ecrecover zero address on invalid sig
```solidity
address signer = ecrecover(h, v, r, s);
if (signer == owner) { /* approve */ }
```
**Bug**: if `(v,r,s)` is invalid, `ecrecover` returns `address(0)`. If
`owner` is somehow `address(0)` (uninitialized!) → any malformed
signature works.
**Fix**: `require(signer != address(0))`.

### 5. Domain separator without chainid
EIP-712 domain separator should bind to the chain. If a protocol
caches `DOMAIN_SEPARATOR` in storage at deployment, hard-forks (which
change chainid) break it. OZ's EIP712 handles this; custom code often
doesn't.

```solidity
// VULNERABLE — cached at deploy
bytes32 immutable DOMAIN_SEPARATOR = keccak256(abi.encode(
    keccak256("EIP712Domain(...)"),
    keccak256(bytes("Name")),
    keccak256(bytes("1")),
    1,  // ← hardcoded chainid
    address(this)
));

// SAFE — re-derive when chainid changes
function _domainSeparator() internal view returns (bytes32) {
    return keccak256(abi.encode(..., block.chainid, ...));
}
```

### 6. Permit signature replay across forks / hard forks
ERC2612 `permit` is meta-tx for ERC20 approvals. If permit doesn't
include the EIP-712 domain separator correctly, it can be replayed on:
- Forked test chains
- L2s that copied the contract
- Hard forks (ETC, ETHW)

This is mostly resolved by OZ ERC20Permit, but custom permit impls are
often wrong.

### 7. Replay across function selectors
A signed payload `keccak256(amount, recipient)` is the same regardless
of which function it authorizes. If two functions share the same
hash structure but different effects, the signature replays:
```solidity
function withdraw(uint256 amt, address to, bytes sig) external {
    bytes32 h = keccak256(abi.encodePacked(amt, to));
    address s = ecrecover(h, ...);
    require(s == owner);
    payable(to).transfer(amt);
}

function mint(uint256 amt, address to, bytes sig) external {
    bytes32 h = keccak256(abi.encodePacked(amt, to));  // SAME HASH
    address s = ecrecover(h, ...);
    require(s == owner);
    _mint(to, amt);
}
// A withdraw signature works for mint, and vice versa
```
**Fix**: include function selector or unique typeID in the signed payload.

## Audit steps

### 1. Find every ecrecover
```bash
grep -rn 'ecrecover\|ECDSA.recover\|recover(' src/
```

### 2. For each call site, verify the payload contains
- [ ] A nonce (or other per-user unique value, like deadline + msg.sender)
- [ ] `block.chainid` (or use EIP-712 domain separator)
- [ ] A function discriminator (if multiple functions use signatures)
- [ ] `address(this)` (so signature is bound to THIS contract)

### 3. Verify signature validation
- [ ] Reject `address(0)` return from ecrecover
- [ ] Use OZ ECDSA library or equivalent that rejects high-`s` malleable signatures
- [ ] Domain separator re-derived from `block.chainid` if cached

### 4. Look for the dangerous patterns
```bash
# Custom ecrecover w/o OZ — often missing s-malleability check
grep -rn 'ecrecover' src/ | grep -v 'ECDSA.sol'

# Signature as uniqueness key
grep -rE 'mapping\(bytes' src/ | grep -i 'used\|nonce'

# Domain separator cached at deploy
grep -rn 'DOMAIN_SEPARATOR.*=.*keccak256' src/ | grep -v 'view\|pure'
```

## PoC templates (Foundry)

### Cross-chain replay
```solidity
function test_cross_chain_replay() public {
    // 1. Sign payload on chain A (chainid 1)
    bytes32 hash = target.getSignableHash(amount, deadline);
    bytes memory sig = sign(privKey, hash);

    target.execute(amount, deadline, sig);  // works on chain A

    // 2. Switch to chain B (chainid 10)
    vm.chainId(10);

    // 3. Deploy same contract bytecode to chain B
    Target targetB = new Target(...);

    // 4. Same signature should be rejected if chainid is in the hash
    vm.expectRevert("invalid sig");
    targetB.execute(amount, deadline, sig);

    // If it DOES NOT revert → cross-chain replay bug
}
```

### Malleability
```solidity
function test_malleability() public {
    bytes32 hash = ...;
    (uint8 v, bytes32 r, bytes32 s) = sign(privKey, hash);

    target.execute(amount, abi.encodePacked(r, s, v));

    // Compute the malleable counterpart
    bytes32 sPrime = bytes32(uint256(SECP256K1_N) - uint256(s));
    uint8 vPrime = v == 27 ? 28 : 27;

    // If target doesn't reject high-s, this also works
    target.execute(amount, abi.encodePacked(r, sPrime, vPrime));
}
```

### Missing nonce
```solidity
function test_replay() public {
    target.execute(amount, sig);  // first call succeeds
    target.execute(amount, sig);  // if no nonce check, succeeds again
    // Attacker can drain by replaying N times
}
```

## CVSS
- Missing nonce + signed withdraw fn: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` = 9.8
- Cross-chain replay on bridge: 10.0 (Critical)
- Malleability + sig as uniqueness key: 8.0-9.0
- Domain separator missing chainid: 8.0
- ecrecover zero-address acceptance: 9.0 (engagement-ending if owner is 0)

## Defender remediation
```solidity
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract Safe is EIP712 {
    using ECDSA for bytes32;

    mapping(address => uint256) public nonces;

    bytes32 constant TYPEHASH = keccak256(
        "Execute(address user,uint256 amount,uint256 nonce,uint256 deadline)"
    );

    constructor() EIP712("MyApp", "1") {}

    function execute(uint256 amount, uint256 deadline, bytes calldata sig) external {
        require(block.timestamp <= deadline, "expired");

        bytes32 structHash = keccak256(abi.encode(
            TYPEHASH, msg.sender, amount, nonces[msg.sender]++, deadline
        ));
        bytes32 hash = _hashTypedDataV4(structHash);
        address signer = hash.recover(sig);

        require(signer == owner, "bad sig");
        // OZ ECDSA already rejects address(0) and malleable s
    }
}
```

## Known exemplars
- Wormhole (Feb 2022): $325M — signature verification bypass (different bug but same family)
- Nomad (Aug 2022): $190M — initial-merkle-root acceptance bug, replay-adjacent
- Multichain (Jul 2023): $126M — private-key compromise + over-broad signature acceptance
- Ronin (Mar 2022): $625M — validator-set takeover via cross-chain replay-like vector
- Cream V2 / Cover (Dec 2020): infinite-mint via nonce replay
- Compound c.Token reentrancy + sig-driven liquidations (smaller)
- ParaSwap (Sep 2021): signature malleability mitigated in ERC1271 wallet integrations
