---
name: upgradeable-proxy
description: Proxy upgrade patterns and their bugs — uninitialized implementation, storage slot collisions, selector clashes, unprotected upgrade auth.
metadata:
  subdomain: smart-contracts
  when_to_use: "upgradeable proxy uups eip-1967 storage collision"
  mitre_attack:
    - T1190
    - T1574
---

# Upgradeable Proxy Playbook

Proxies separate storage (proxy) from logic (implementation). The
proxy `delegatecall`s into the implementation, executing logic in the
proxy's storage context. Three common patterns:

1. **Transparent Proxy** (OZ TransparentUpgradeableProxy)
2. **UUPS** (OZ UUPSUpgradeable, OZ 4.1+)
3. **Diamond / EIP-2535** (multi-facet, much more complex)

Each has distinct bug classes.

## Audit checklist

### 1. Uninitialized implementation
Implementations should be initialized at deployment to prevent
third-party initialization:
```solidity
// Vulnerable — anyone can call initialize() on the implementation
// directly (not via proxy) and become its owner
contract VulnImpl {
    function initialize(address owner_) external {
        owner = owner_;
    }
}

// Safe — disable initializers on impl deployment
contract SafeImpl is Initializable {
    constructor() { _disableInitializers(); }

    function initialize(address owner_) external initializer {
        owner = owner_;
    }
}
```

**Attack**: attacker calls `initialize` on the impl contract → becomes
"owner" of the impl. While this doesn't immediately drain the proxy,
it CAN matter if `_authorizeUpgrade` reads impl-side state, or if
selfdestruct is exposed and impl auth is on owner. Past incident:
**Parity multisig 2017** — $280M frozen.

```bash
# Find unprotected impl
grep -rn 'initialize\|_disableInitializers' src/
```

### 2. Storage slot collisions
Proxy and impl share storage. New impl versions must lay storage
identical to old:

```solidity
// V1
contract LogicV1 {
    address public owner;     // slot 0
    uint256 public total;     // slot 1
}

// V2 — BUG: inserted new var at top
contract LogicV2 {
    uint256 public newVar;    // slot 0 — overwrites owner!
    address public owner;     // slot 1
    uint256 public total;     // slot 2
}
```

After upgrade, `owner` is read from where `total` was; arbitrary value.

**Check**:
- New vars only appended at the end
- Inheritance order unchanged
- OZ `__gap` reserved slots used in upgradeable libs

```bash
# OZ provides a tool
slither-check-upgradeability V1.sol V2.sol --proxy-name MyProxy
```

### 3. Function selector collisions (Transparent Proxy specifically)
Transparent proxy: if caller is admin → proxy admin functions; else →
delegatecall to impl. If impl has function with selector matching a
proxy admin selector → admin sees impl, user sees impl, admin can never
call admin functions. Or worse, ABI-trickery.

**Common collisions**:
- `upgradeTo(address)`: selector `0x3659cfe6` — what if impl defines a `transferOwnership(address)` that hashes to the same selector?

Slither auto-detects:
```bash
slither --print human-summary src/ | grep -i selector
```

### 4. `_authorizeUpgrade` empty / wrong
UUPS pattern: implementation contains the upgrade authorization. Default
OZ `_authorizeUpgrade` is `internal virtual {}` — empty body that
**reverts**, but the function itself is empty. Devs override it:

```solidity
// VULNERABLE — empty body, no actual auth check
function _authorizeUpgrade(address newImplementation) internal override {}

// SAFE
function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
```

**Attack**: anyone calls `upgradeTo(maliciousImpl)` → all storage now
controlled by malicious code.

```bash
grep -rn '_authorizeUpgrade' src/
```

### 5. `delegatecall` to attacker-controlled address
If the impl contains a function that performs `delegatecall(arbitrary_address)`,
attackers can pass their own contract → execute arbitrary code in
proxy storage context, including selfdestruct.

```bash
grep -rn 'delegatecall' src/
```

### 6. Constructor logic in upgradeable contracts
Constructors run on the implementation only — proxy storage is
untouched. Storage initialization must happen in `initialize()`. If
critical state is set in the constructor, the proxy will read zero
values:

```solidity
// VULNERABLE — admin set in constructor, proxy reads 0x0
contract Impl {
    address public admin;
    constructor() { admin = msg.sender; }  // sets admin on IMPL only
}
```

### 7. Diamond / EIP-2535 specific bugs
- **Facet selector collisions** — two facets define same selector
- **Diamond storage** position not unique → cross-facet storage corruption
- **`diamondCut` access control** — must be gated, often forgotten

```bash
# Inspect facet selectors
slither . --print function-summary | grep -A1 'Facet'
```

### 8. Storage gap for inheritance
OZ upgradeable libs use `uint256[N] private __gap;` to reserve slots
for future vars. Custom contracts inheriting them MUST preserve this:

```solidity
contract MyToken is ERC20Upgradeable {
    uint256 public myVar1;
    uint256 public myVar2;
    uint256[48] private __gap;  // reserve 48 slots for future
}
```

Without `__gap`, future versions can't add fields without colliding
with parent contracts that also added fields.

## PoC template (Foundry)
```solidity
function test_unauth_upgrade() public {
    address attacker = address(0xBEEF);
    address malicious = address(new MaliciousImpl());

    vm.prank(attacker);
    proxy.upgradeTo(malicious);  // _authorizeUpgrade is empty

    // Now any call to proxy executes malicious code
    proxy.balanceOf(attacker);  // returns whatever malicious wants
}

function test_impl_init() public {
    address attacker = address(0xBEEF);
    address impl = address(proxy.implementation());

    vm.prank(attacker);
    IImpl(impl).initialize(attacker);

    // Attacker is "owner" of impl
    // Whether that matters depends on impl logic
    assertEq(IImpl(impl).owner(), attacker);
}

function test_storage_collision() public {
    // Set state in V1
    proxy.setOwner(address(this));
    assertEq(proxy.owner(), address(this));

    // Upgrade to V2 which inserted a new var at slot 0
    proxy.upgradeTo(address(new LogicV2()));

    // owner now reads from where total was — likely garbage
    assertNotEq(proxy.owner(), address(this));
}
```

## CVSS
- Empty `_authorizeUpgrade`: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = 10.0 (Critical)
- Uninitialized impl + selfdestruct path: 10.0
- Storage collision discovered post-deployment: 9.0 (already-deployed bug, can't fix in place)
- Selector collision: 8.0 (DoS or value manipulation)
- Diamond facet collision: 8.0

## Defender remediation
```solidity
// UUPS template
contract MyContract is UUPSUpgradeable, OwnableUpgradeable {
    constructor() { _disableInitializers(); }

    function initialize(address owner_) external initializer {
        __Ownable_init(owner_);
        __UUPSUpgradeable_init();
    }

    function _authorizeUpgrade(address) internal override onlyOwner {}
}

// Storage layout discipline
contract MyToken is ERC20Upgradeable, OwnableUpgradeable {
    // V1 fields
    uint256 public param1;
    address public param2;

    // Reserved gap — DECREMENT this when adding fields
    uint256[48] private __gap;
}

// Verify upgrade safety in CI
forge test --match-contract Test_Upgrade
# Plus run `slither-check-upgradeability V1 V2` in CI gate
```

## Known exemplars
- Parity multisig (Jul + Nov 2017): $30M stolen, $280M frozen — both proxy/impl bugs
- Audius (Jul 2022): $6M — unauth initializer on governance proxy
- dForce (Apr 2020): $25M — proxy upgrade w/ broken token logic (ERC777 reentrancy via upgrade)
- KILT Protocol (Mar 2022): bricked w/ storage collision after a botched upgrade
- Compound (Sep 2021): $80M; not a proxy bug but a governance-deployed bug — upgrade triggered the issue
- Beanstalk (Apr 2022): governance + flash-loan + immediate upgrade execution = drain
- Curve (Jul 2023): $61M; Vyper compiler reentrancy in a proxy-deployed contract
