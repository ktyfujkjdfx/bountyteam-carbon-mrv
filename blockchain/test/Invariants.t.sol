// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {ICarbonCreditRegistry as I} from "shared-contracts/contract-interface.sol";
import {CarbonCreditRegistry} from "../src/CarbonCreditRegistry.sol";

/// @dev Drives random buy/transfer/withdraw/freeze sequences over a fixed set of actors.
contract RegistryHandler is Test {
    CarbonCreditRegistry public immutable registry;
    address public immutable seller;
    address public immutable oracle;
    uint256 public immutable batchId;
    uint256 public immutable price;
    address[4] public actors;

    uint256 public paidTotal;
    uint256 public withdrawnTotal;
    bool public frozen;
    uint256 public circulationAfterFreeze;

    constructor(CarbonCreditRegistry registry_, address seller_, address oracle_, uint256 batchId_, uint256 price_) {
        registry = registry_;
        seller = seller_;
        oracle = oracle_;
        batchId = batchId_;
        price = price_;
        actors = [seller_, makeAddr("h-buyer"), makeAddr("h-recipient"), makeAddr("h-other")];
    }

    function buy(uint256 actorSeed, uint256 amount) external {
        address actor = actors[1 + (actorSeed % 3)];
        amount = bound(amount, 1, 20);
        uint256 value = amount * price;
        vm.deal(actor, value);
        vm.prank(actor);
        try registry.buy{value: value}(batchId, amount) {
            paidTotal += value;
            if (frozen) circulationAfterFreeze++;
        } catch {}
    }

    function transfer(uint256 fromSeed, uint256 toSeed, uint256 amount) external {
        address from = actors[fromSeed % 4];
        address to = actors[toSeed % 4];
        amount = bound(amount, 1, 50);
        vm.prank(from);
        try registry.transfer(batchId, to, amount) {
            if (frozen) circulationAfterFreeze++;
        } catch {}
    }

    function withdraw() external {
        uint256 before = seller.balance;
        vm.prank(seller);
        try registry.withdrawProceeds() {
            withdrawnTotal += seller.balance - before;
        } catch {}
    }

    /// @dev Freezes rarely (~1 in 16 calls) so that most sequences exercise ACTIVE circulation first.
    function freeze(uint64 delay, uint256 chance) external {
        if (chance % 16 != 0) return;
        vm.warp(vm.getBlockTimestamp() + bound(delay, 0, 1 days));
        vm.prank(oracle);
        try registry.freeze(batchId, keccak256("inv-evidence"), keccak256("inv-decision"), uint64(vm.getBlockTimestamp()), 1) {
            frozen = true;
        } catch {}
    }

    function actorCount() external pure returns (uint256) {
        return 4;
    }
}

contract RegistryInvariantTest is Test {
    uint256 internal constant SUPPLY = 250;
    uint256 internal constant PRICE = 1 gwei;

    CarbonCreditRegistry internal registry;
    RegistryHandler internal handler;
    uint256 internal id;

    function setUp() public {
        vm.warp(1_760_000_000);
        address owner = makeAddr("owner");
        address issuer = makeAddr("issuer");
        address oracle = makeAddr("oracle");
        address seller = makeAddr("seller");
        registry = new CarbonCreditRegistry(owner);
        vm.startPrank(owner);
        registry.setIssuer(issuer, true);
        registry.setOracle(oracle, true);
        vm.stopPrank();
        vm.prank(issuer);
        id = registry.issue(keccak256("inv"), "INV-PLOT", seller, SUPPLY, PRICE, keccak256("e"), 1_759_000_000);

        handler = new RegistryHandler(registry, seller, oracle, id, PRICE);
        targetContract(address(handler));
    }

    function invariant_balancesSumToConstantSupply() public view {
        uint256 sum;
        for (uint256 i; i < handler.actorCount(); i++) {
            sum += registry.balanceOf(id, handler.actors(i));
        }
        assertEq(sum, SUPPLY);
        assertEq(registry.getBatch(id).totalSupply, SUPPLY);
    }

    function invariant_etherIsFullyAccounted() public view {
        assertEq(address(registry).balance, handler.paidTotal() - handler.withdrawnTotal());
    }

    function invariant_noCirculationAfterFreeze() public view {
        assertEq(handler.circulationAfterFreeze(), 0);
        if (handler.frozen()) {
            assertEq(uint8(registry.getBatch(id).creditStatus), uint8(I.CreditStatus.FROZEN));
        }
    }
}
