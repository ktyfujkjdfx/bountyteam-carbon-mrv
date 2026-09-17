// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {ICarbonCreditRegistry} from "shared-contracts/contract-interface.sol";
import {CarbonCreditRegistry} from "../src/CarbonCreditRegistry.sol";

abstract contract RegistryBase is Test {
    CarbonCreditRegistry internal registry;

    address internal owner = makeAddr("owner");
    address internal issuer = makeAddr("issuer");
    address internal oracle = makeAddr("oracle");
    address internal seller = makeAddr("seller");
    address internal buyer = makeAddr("buyer");
    address internal recipient = makeAddr("recipient");
    address internal stranger = makeAddr("stranger");

    uint64 internal constant START = 1_760_000_000;
    uint64 internal constant OBSERVED_AT = START - 1 days;
    uint256 internal constant AMOUNT = 100;
    uint256 internal constant PRICE = 0.001 ether;
    uint8 internal constant FIRE_REVERSAL = 1;

    bytes32 internal constant ISSUANCE_KEY = keccak256("issuance-key-1");
    bytes32 internal constant EVIDENCE = keccak256("issuance-evidence");
    bytes32 internal constant FIRE_EVIDENCE = keccak256("fire-evidence");
    bytes32 internal constant DECISION = keccak256("fire-decision");
    string internal constant PLOT = "SYNTHETIC-PLOT-001";

    /// @dev Storage slot of `_batches` in CarbonCreditRegistry (verified by `test_revokedSlotLayout`).
    uint256 internal constant BATCHES_SLOT = 4;
    uint256 internal constant STATUS_FIELD_OFFSET = 4;

    function setUp() public virtual {
        vm.warp(START);
        registry = new CarbonCreditRegistry(owner);
        vm.startPrank(owner);
        registry.setIssuer(issuer, true);
        registry.setOracle(oracle, true);
        vm.stopPrank();
        vm.deal(buyer, 100 ether);
        vm.deal(recipient, 100 ether);
        vm.deal(stranger, 100 ether);
    }

    function _issue() internal returns (uint256) {
        return _issue(ISSUANCE_KEY, seller);
    }

    function _issue(bytes32 key, address to) internal returns (uint256) {
        vm.prank(issuer);
        return registry.issue(key, PLOT, to, AMOUNT, PRICE, EVIDENCE, OBSERVED_AT);
    }

    function _buy(uint256 batchId, address who, uint256 amount) internal {
        vm.prank(who);
        registry.buy{value: amount * PRICE}(batchId, amount);
    }

    function _freeze(uint256 batchId) internal {
        vm.prank(oracle);
        registry.freeze(batchId, FIRE_EVIDENCE, DECISION, START - 1 hours, FIRE_REVERSAL);
    }

    function _setStatus(uint256 batchId, ICarbonCreditRegistry.CreditStatus status) internal {
        bytes32 base = keccak256(abi.encode(batchId, BATCHES_SLOT));
        vm.store(address(registry), bytes32(uint256(base) + STATUS_FIELD_OFFSET), bytes32(uint256(status)));
    }

    function _expectRevert(bytes4 selector) internal {
        vm.expectRevert(abi.encodeWithSelector(selector));
    }
}
