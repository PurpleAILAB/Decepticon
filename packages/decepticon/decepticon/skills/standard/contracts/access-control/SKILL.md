---
name: access-control
description: Missing modifiers, wrong msg.sender checks, default-public functions, missing onlyOwner / onlyRole / onlyDAO authorization.
metadata:
  subdomain: smart-contracts
  when_to_use: "smart contract access control onlyowner missing modifier privilege"
  mitre_attack:
    - T1190
---

# Access Control Playbook

Access control bugs are the most boring class — and the most common in
production audits. They're cheap to find with grep + LSP. They drain
millions when missed (LeetSwap, Audius, Saddle, Akropolis).

## Audit steps

### 1. Find every state-changing function
```bash
# Functions that are NOT view/pure and NOT internal/private
grep -rE 'function [a-zA-Z_]+\(.*\)(public|external)' src/ | grep -v 'view\|pure'

# Or via slither
slither . --print function-summary
```

### 2. For each external/public state-changer, ask
- Does it modify storage that affects user funds, ownership, or
  configuration?
- Is there a modifier (`onlyOwner`, `onlyRole`, `onlyDAO`, custom auth)?
- If yes, what's the modifier checking?
- If no, should there be one?

### 3. Audit each modifier
Common modifier patterns + bugs:

| Pattern | Bug |
|---|---|
| `require(msg.sender == owner)` | `owner` settable by anyone? `setOwner` unprotected? |
| `require(msg.sender == tx.origin)` | Wrong — tx.origin breaks meta-transactions, AND it's phishable |
| `_msgSender()` in OZ ERC2771Context | Forwarder trusted but anyone can forward — does the contract validate the forwarder? |
| `onlyRole(MINTER)` | Who can grant MINTER? Is the admin a multisig or single key? |
| `require(initialized == false)` | Initializer can be called twice if `initialized` writeable elsewhere |
| `require(block.timestamp > deployTime + 24 hours)` | Time-based is often a fake delay — check if `deployTime` is settable |
| `require(approvedSigners[msg.sender])` | Approval list managed by single key? |

### 4. Specific anti-patterns to grep
```bash
# Functions accidentally external (default in Solidity <0.5)
grep -rn 'function [a-zA-Z_]*[^ ]* *{' src/ | grep -v 'internal\|private\|public\|external'

# msg.sender == tx.origin (phishable)
grep -rn 'tx.origin' src/

# Reentrancy in access-control checks
grep -rn 'onlyOwner.*nonReentrant' src/   # both? often wrong order

# `delegatecall` without auth gate
grep -rn 'delegatecall' src/

# `selfdestruct` available
grep -rn 'selfdestruct\|suicide(' src/
```

### 5. Initializer bugs
```solidity
// VULNERABLE
function initialize(address _owner) external {
    owner = _owner;
    // missing: require(!initialized); initialized = true;
}

// VULNERABLE (proxy implementation)
contract Impl {
    constructor() { ... }  // NEVER RUNS in proxy context
    // initialize() should set proxy state but doesn't gate
}

// SAFE
function initialize(address _owner) external initializer {
    // OZ's initializer modifier enforces single-call
    __Ownable_init(_owner);
}
```

For UUPS/Transparent proxies: check `_authorizeUpgrade` is overridden
and gated. Default OZ override is empty (revert).

### 6. Function-selector collisions (proxies)
Transparent proxy admin function selectors collide w/ impl function
selectors → admin functions become uncallable, OR impl functions are
shadowed by admin. Check w/ slither:
```bash
slither-check-erc src/Impl.sol --erc ERC1967
```

### 7. Role grant/revoke
For `AccessControl`:
- `DEFAULT_ADMIN_ROLE` is the admin of all roles by default
- Anyone with DEFAULT_ADMIN_ROLE can grant any role to anyone
- If init code grants DEFAULT_ADMIN_ROLE to deployer w/ no transfer to multisig → key person risk

Check role hierarchy:
```bash
grep -rn '_setRoleAdmin\|_setupRole\|grantRole' src/
```

## PoC template (Foundry)
```solidity
function test_unauth_call() public {
    address attacker = address(0xBEEF);
    vm.prank(attacker);

    // Call the function that should require auth
    target.dangerousFunction(arg1, arg2);

    // Assert state change happened
    assertEq(target.criticalParam(), expectedManipulatedValue);
    // No revert = vulnerable
}

function test_role_takeover() public {
    address attacker = address(0xBEEF);
    vm.startPrank(attacker);

    // If grantRole is callable by anyone
    target.grantRole(target.MINTER_ROLE(), attacker);
    assertTrue(target.hasRole(target.MINTER_ROLE(), attacker));

    // Now exploit MINTER_ROLE
    target.mint(attacker, 1_000_000 ether);
}

function test_init_re_entry() public {
    // Call initialize twice
    target.initialize(address(this));
    vm.expectRevert("Initializable: contract is already initialized");
    target.initialize(attacker);
}

function test_upgrade_no_auth() public {
    address attacker = address(0xBEEF);
    address malicious = address(new MaliciousImpl());

    vm.prank(attacker);
    target.upgradeTo(malicious);

    // Now any call goes to malicious — drain
    assertEq(target.totalSupply(), 0);
}
```

## Severity calibration

| Bug | Severity |
|---|---|
| Unauth `withdraw` / `mint` / `transferOwnership` | Critical |
| Unauth `upgradeTo` (proxy) | Critical (escalates to any) |
| Unauth `setOracle` / `setFee` | High (DoS or value manipulation) |
| `tx.origin` auth + phishable | High |
| Initializer re-entry | High (proxy takeover) |
| Role hierarchy lets non-admin grant admin | High |
| Function defaults to external (Solidity <0.5 only) | High |
| Selector collision in proxy | High (function unreachable) |

## CVSS
- Unauth drain function: 9.8-10.0
- Unauth upgrade: 10.0
- Unauth admin / role-change: 9.0
- DoS via unauth pause: 7-8

## Defender remediation
```solidity
// Use OpenZeppelin patterns
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

contract MyContract is AccessControlUpgradeable, UUPSUpgradeable {
    bytes32 public constant MINTER = keccak256("MINTER");

    function initialize(address admin) external initializer {
        __AccessControl_init();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    function mint(address to, uint256 amt) external onlyRole(MINTER) {
        _mint(to, amt);
    }

    function _authorizeUpgrade(address) internal override onlyRole(DEFAULT_ADMIN_ROLE) {}
}
```

## Known exemplars
- Audius (Jul 2022): $6M; unauth initialize on governance proxy
- LeetSwap (Aug 2023): $625k; unauth swap fn enabled draining
- Saddle (Apr 2022): $11M; rounding + access combo
- Akropolis (Nov 2020): $2M; access + reentrancy combo
- Pickle Finance (Nov 2020): $20M; missing access on the jar
- Wormhole (Feb 2022): $325M; signature verification bug — adjacent (sig-replay/SKILL.md)
- Nomad (Aug 2022): $190M; missing message-merkle-root validation
- Multichain (Jul 2023): $126M; private-key compromise (not strictly access-control, but exploited admin)
