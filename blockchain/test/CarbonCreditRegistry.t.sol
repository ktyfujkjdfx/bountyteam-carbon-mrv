// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Vm} from "forge-std/Vm.sol";
import {ICarbonCreditRegistry as I} from "shared-contracts/contract-interface.sol";
import {CarbonCreditRegistry} from "../src/CarbonCreditRegistry.sol";
import {RegistryBase} from "./RegistryBase.t.sol";

contract ReentrantSeller {
    CarbonCreditRegistry internal immutable registry;
    bytes public reentryError;
    uint256 public receiveCount;

    constructor(CarbonCreditRegistry registry_) {
        registry = registry_;
    }

    function withdraw() external {
        registry.withdrawProceeds();
    }

    receive() external payable {
        receiveCount++;
        try registry.withdrawProceeds() {} catch (bytes memory err) {
            reentryError = err;
        }
    }
}

contract RejectingSeller {
    function withdraw(CarbonCreditRegistry registry) external {
        registry.withdrawProceeds();
    }
}

contract DeploymentAndPermissionsTest is RegistryBase {
    function test_constructorRejectsZeroOwner() public {
        _expectRevert(I.InvalidAddress.selector);
        new CarbonCreditRegistry(address(0));
    }

    function test_ownerGrantsAndRevokesRolesWithExactEvents() public {
        address account = makeAddr("second-issuer");
        vm.startPrank(owner);
        vm.expectEmit(true, false, false, true, address(registry));
        emit I.IssuerPermissionChanged(account, true);
        registry.setIssuer(account, true);
        vm.expectEmit(true, false, false, true, address(registry));
        emit I.OraclePermissionChanged(account, true);
        registry.setOracle(account, true);
        vm.expectEmit(true, false, false, true, address(registry));
        emit I.IssuerPermissionChanged(account, false);
        registry.setIssuer(account, false);
        vm.stopPrank();

        vm.prank(account);
        _expectRevert(I.Unauthorized.selector);
        registry.issue(ISSUANCE_KEY, PLOT, seller, AMOUNT, PRICE, EVIDENCE, OBSERVED_AT);
    }

    function test_nonOwnerCannotManagePermissions() public {
        address[4] memory callers = [issuer, oracle, stranger, seller];
        for (uint256 i; i < callers.length; i++) {
            vm.startPrank(callers[i]);
            _expectRevert(I.Unauthorized.selector);
            registry.setIssuer(callers[i], true);
            _expectRevert(I.Unauthorized.selector);
            registry.setOracle(callers[i], true);
            _expectRevert(I.Unauthorized.selector);
            registry.setIssuer(stranger, true);
            _expectRevert(I.Unauthorized.selector);
            registry.setOracle(stranger, true);
            vm.stopPrank();
        }
    }

    function test_ownerCannotSelfAssignOrUseZeroAddress() public {
        vm.startPrank(owner);
        _expectRevert(I.Unauthorized.selector);
        registry.setIssuer(owner, true);
        _expectRevert(I.Unauthorized.selector);
        registry.setOracle(owner, true);
        _expectRevert(I.InvalidAddress.selector);
        registry.setIssuer(address(0), true);
        _expectRevert(I.InvalidAddress.selector);
        registry.setOracle(address(0), true);
        vm.stopPrank();
    }

    function test_revokedOracleCannotFreeze() public {
        uint256 id = _issue();
        vm.prank(owner);
        registry.setOracle(oracle, false);
        vm.prank(oracle);
        _expectRevert(I.Unauthorized.selector);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT, FIRE_REVERSAL);
    }

    function test_revokedSlotLayout() public {
        uint256 id = _issue();
        _setStatus(id, I.CreditStatus.FROZEN);
        assertEq(uint8(registry.getBatch(id).creditStatus), uint8(I.CreditStatus.FROZEN));
        assertEq(registry.getBatch(id).totalSupply, AMOUNT, "status slot must not overlap supply");
        assertEq(registry.getBatch(id).unitPriceWei, PRICE, "status slot must not overlap price");
    }
}

contract IssueTest is RegistryBase {
    function test_issueStoresBatchBalanceAndEmits() public {
        vm.expectEmit(true, true, true, true, address(registry));
        emit I.Issued(1, ISSUANCE_KEY, seller, AMOUNT, EVIDENCE);
        uint256 id = _issue();

        assertEq(id, 1);
        I.BatchView memory b = registry.getBatch(id);
        assertEq(b.plotId, PLOT);
        assertEq(b.issuanceKey, ISSUANCE_KEY);
        assertEq(b.seller, seller);
        assertEq(b.totalSupply, AMOUNT);
        assertEq(uint8(b.creditStatus), uint8(I.CreditStatus.ACTIVE));
        assertEq(b.unitPriceWei, PRICE);
        assertEq(b.evidenceHash, EVIDENCE);
        assertEq(b.decisionHash, bytes32(0));
        assertEq(b.issuedAt, START);
        assertEq(b.frozenAt, 0);
        assertEq(b.lastObservedAt, OBSERVED_AT);
        assertEq(registry.balanceOf(id, seller), AMOUNT);
        assertEq(registry.balanceOf(id, buyer), 0);
    }

    function test_batchIdsAreSequentialAndIndependent() public {
        uint256 a = _issue(keccak256("a"), seller);
        uint256 b = _issue(keccak256("b"), buyer);
        assertEq(a, 1);
        assertEq(b, 2);
        assertEq(registry.balanceOf(a, seller), AMOUNT);
        assertEq(registry.balanceOf(a, buyer), 0);
        assertEq(registry.balanceOf(b, buyer), AMOUNT);
    }

    function test_onlyIssuerCanIssue() public {
        address[4] memory callers = [owner, oracle, stranger, seller];
        for (uint256 i; i < callers.length; i++) {
            vm.prank(callers[i]);
            _expectRevert(I.Unauthorized.selector);
            registry.issue(ISSUANCE_KEY, PLOT, seller, AMOUNT, PRICE, EVIDENCE, OBSERVED_AT);
        }
    }

    function test_duplicateIssuanceKeyReverts() public {
        _issue();
        vm.prank(issuer);
        _expectRevert(I.DuplicateIssuance.selector);
        registry.issue(ISSUANCE_KEY, "OTHER-PLOT", buyer, 5, 1, keccak256("other"), OBSERVED_AT);
    }

    function test_invalidIssueInputsRevert() public {
        vm.startPrank(issuer);
        _expectRevert(I.InvalidEvidence.selector);
        registry.issue(bytes32(0), PLOT, seller, AMOUNT, PRICE, EVIDENCE, OBSERVED_AT);
        _expectRevert(I.InvalidEvidence.selector);
        registry.issue(ISSUANCE_KEY, PLOT, seller, AMOUNT, PRICE, bytes32(0), OBSERVED_AT);
        _expectRevert(I.InvalidPlot.selector);
        registry.issue(ISSUANCE_KEY, "", seller, AMOUNT, PRICE, EVIDENCE, OBSERVED_AT);
        _expectRevert(I.InvalidAddress.selector);
        registry.issue(ISSUANCE_KEY, PLOT, address(0), AMOUNT, PRICE, EVIDENCE, OBSERVED_AT);
        _expectRevert(I.InvalidAmount.selector);
        registry.issue(ISSUANCE_KEY, PLOT, seller, 0, PRICE, EVIDENCE, OBSERVED_AT);
        _expectRevert(I.InvalidAmount.selector);
        registry.issue(ISSUANCE_KEY, PLOT, seller, AMOUNT, 0, EVIDENCE, OBSERVED_AT);
        _expectRevert(I.InvalidEvidence.selector);
        registry.issue(ISSUANCE_KEY, PLOT, seller, AMOUNT, PRICE, EVIDENCE, 0);
        _expectRevert(I.InvalidEvidence.selector);
        registry.issue(ISSUANCE_KEY, PLOT, seller, AMOUNT, PRICE, EVIDENCE, START + 1);
        vm.stopPrank();
        // A failed attempt must not consume the issuance key.
        assertEq(_issue(), 1);
    }

    function test_unknownBatchRejectedEverywhere() public {
        _issue();
        uint256[3] memory ids = [uint256(0), 2, type(uint256).max];
        for (uint256 i; i < ids.length; i++) {
            _expectRevert(I.UnknownBatch.selector);
            registry.getBatch(ids[i]);
            _expectRevert(I.UnknownBatch.selector);
            registry.balanceOf(ids[i], seller);
            vm.prank(buyer);
            _expectRevert(I.UnknownBatch.selector);
            registry.buy{value: PRICE}(ids[i], 1);
            vm.prank(seller);
            _expectRevert(I.UnknownBatch.selector);
            registry.transfer(ids[i], buyer, 1);
            vm.prank(oracle);
            _expectRevert(I.UnknownBatch.selector);
            registry.freeze(ids[i], FIRE_EVIDENCE, DECISION, OBSERVED_AT, FIRE_REVERSAL);
        }
    }
}

contract BuyTransferWithdrawTest is RegistryBase {
    uint256 internal id;

    function setUp() public override {
        super.setUp();
        id = _issue();
    }

    function test_buyWithExactPaymentMovesRealBalances() public {
        vm.expectEmit(true, true, false, true, address(registry));
        emit I.Purchased(id, buyer, 10, 10 * PRICE);
        _buy(id, buyer, 10);

        assertEq(registry.balanceOf(id, seller), AMOUNT - 10);
        assertEq(registry.balanceOf(id, buyer), 10);
        assertEq(registry.getBatch(id).totalSupply, AMOUNT);
        assertEq(address(registry).balance, 10 * PRICE);
        assertEq(buyer.balance, 100 ether - 10 * PRICE);
    }

    function test_buyRejectsWrongPayment() public {
        vm.startPrank(buyer);
        _expectRevert(I.IncorrectPayment.selector);
        registry.buy{value: 10 * PRICE - 1}(id, 10);
        _expectRevert(I.IncorrectPayment.selector);
        registry.buy{value: 10 * PRICE + 1}(id, 10);
        _expectRevert(I.IncorrectPayment.selector);
        registry.buy{value: 0}(id, 10);
        vm.stopPrank();
        assertEq(registry.balanceOf(id, buyer), 0);
    }

    function test_buyRejectsInvalidAmountSellerAndInsufficientInventory() public {
        vm.prank(buyer);
        _expectRevert(I.InvalidAmount.selector);
        registry.buy(id, 0);

        vm.deal(seller, 1 ether);
        vm.prank(seller);
        _expectRevert(I.InvalidAddress.selector);
        registry.buy{value: PRICE}(id, 1);

        vm.prank(buyer);
        _expectRevert(I.InsufficientBalance.selector);
        registry.buy{value: (AMOUNT + 1) * PRICE}(id, AMOUNT + 1);
    }

    function test_buyOverflowIsIncorrectPaymentNotPanic() public {
        uint256 bigId = _issue(keccak256("big"), seller);
        vm.prank(issuer);
        uint256 hugeSupplyId =
            registry.issue(keccak256("huge"), PLOT, seller, type(uint256).max, 2, EVIDENCE, OBSERVED_AT);
        assertGt(hugeSupplyId, bigId);
        vm.prank(buyer);
        _expectRevert(I.IncorrectPayment.selector);
        registry.buy{value: 1}(hugeSupplyId, type(uint256).max);
    }

    function test_sellerInventoryCanBeBoughtOutExactly() public {
        vm.deal(buyer, AMOUNT * PRICE);
        _buy(id, buyer, AMOUNT);
        assertEq(registry.balanceOf(id, seller), 0);
        vm.prank(recipient);
        _expectRevert(I.InsufficientBalance.selector);
        registry.buy{value: PRICE}(id, 1);
    }

    function test_transferActiveMovesBalances() public {
        _buy(id, buyer, 10);
        vm.expectEmit(true, true, true, true, address(registry));
        emit I.Transferred(id, buyer, recipient, 4);
        vm.prank(buyer);
        registry.transfer(id, recipient, 4);

        vm.prank(seller);
        registry.transfer(id, recipient, 6);

        assertEq(registry.balanceOf(id, buyer), 6);
        assertEq(registry.balanceOf(id, recipient), 10);
        assertEq(registry.balanceOf(id, seller), AMOUNT - 16);
        assertEq(registry.getBatch(id).totalSupply, AMOUNT);
    }

    function test_transferRejectsInvalidInputs() public {
        vm.startPrank(seller);
        _expectRevert(I.InvalidAddress.selector);
        registry.transfer(id, address(0), 1);
        _expectRevert(I.InvalidAddress.selector);
        registry.transfer(id, seller, 1);
        _expectRevert(I.InvalidAmount.selector);
        registry.transfer(id, buyer, 0);
        _expectRevert(I.InsufficientBalance.selector);
        registry.transfer(id, buyer, AMOUNT + 1);
        vm.stopPrank();

        vm.prank(stranger);
        _expectRevert(I.InsufficientBalance.selector);
        registry.transfer(id, buyer, 1);
    }

    function test_withdrawProceedsOnceWithEvent() public {
        _buy(id, buyer, 3);
        _buy(id, recipient, 2);
        uint256 before = seller.balance;

        vm.expectEmit(true, false, false, true, address(registry));
        emit I.ProceedsWithdrawn(seller, 5 * PRICE);
        vm.prank(seller);
        registry.withdrawProceeds();

        assertEq(seller.balance - before, 5 * PRICE);
        assertEq(address(registry).balance, 0);

        vm.prank(seller);
        _expectRevert(I.NoProceeds.selector);
        registry.withdrawProceeds();
    }

    function test_withdrawWithoutProceedsReverts() public {
        vm.prank(buyer);
        _expectRevert(I.NoProceeds.selector);
        registry.withdrawProceeds();
    }

    function test_withdrawIsReentrancySafe() public {
        ReentrantSeller attacker = new ReentrantSeller(registry);
        uint256 attackId = _issue(keccak256("attack"), address(attacker));
        _buy(attackId, buyer, 7);
        _buy(id, recipient, 1); // other seller's funds stay in the contract

        attacker.withdraw();

        assertEq(address(attacker).balance, 7 * PRICE);
        assertEq(attacker.receiveCount(), 1);
        assertEq(attacker.reentryError(), abi.encodeWithSelector(I.ReentrantCall.selector));
        assertEq(address(registry).balance, PRICE);
        vm.expectRevert(abi.encodeWithSelector(I.NoProceeds.selector));
        attacker.withdraw();
    }

    function test_withdrawToRejectingReceiverRevertsAndKeepsProceeds() public {
        RejectingSeller rejecting = new RejectingSeller();
        uint256 rejectId = _issue(keccak256("reject"), address(rejecting));
        _buy(rejectId, buyer, 2);

        _expectRevert(I.PaymentFailed.selector);
        rejecting.withdraw(registry);
        assertEq(address(registry).balance, 2 * PRICE);
    }
}

contract FreezeTest is RegistryBase {
    uint256 internal id;

    function setUp() public override {
        super.setUp();
        id = _issue();
        _buy(id, buyer, 10);
    }

    function test_freezeStoresHashesTimeStatusAndEmits() public {
        vm.warp(START + 2 hours);
        uint64 observedAt = START + 1 hours;
        vm.expectEmit(true, true, false, true, address(registry));
        emit I.Frozen(id, FIRE_EVIDENCE, DECISION, observedAt, FIRE_REVERSAL);
        vm.prank(oracle);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, observedAt, FIRE_REVERSAL);

        I.BatchView memory b = registry.getBatch(id);
        assertEq(uint8(b.creditStatus), uint8(I.CreditStatus.FROZEN));
        assertEq(b.evidenceHash, FIRE_EVIDENCE);
        assertEq(b.decisionHash, DECISION);
        assertEq(b.frozenAt, START + 2 hours);
        assertEq(b.lastObservedAt, observedAt);
        assertEq(b.issuedAt, START);
        assertEq(b.issuanceKey, ISSUANCE_KEY);
        assertEq(b.totalSupply, AMOUNT);
    }

    function test_freezeEmitsExactlyOneLogWithIndexedTopics() public {
        vm.recordLogs();
        _freeze(id);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        assertEq(logs.length, 1);
        assertEq(logs[0].topics.length, 3, "batchId and evidenceHash are indexed");
        assertEq(logs[0].topics[0], keccak256("Frozen(uint256,bytes32,bytes32,uint64,uint8)"));
        assertEq(logs[0].topics[1], bytes32(id));
        assertEq(logs[0].topics[2], FIRE_EVIDENCE);
        assertEq(logs[0].data, abi.encode(DECISION, uint64(START - 1 hours), uint8(FIRE_REVERSAL)));
    }

    function test_onlyOracleCanFreeze() public {
        address[4] memory callers = [owner, issuer, seller, stranger];
        for (uint256 i; i < callers.length; i++) {
            vm.prank(callers[i]);
            _expectRevert(I.Unauthorized.selector);
            registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT, FIRE_REVERSAL);
        }
        assertEq(uint8(registry.getBatch(id).creditStatus), uint8(I.CreditStatus.ACTIVE));
    }

    function test_freezeValidatesHashesReasonAndTime() public {
        vm.startPrank(oracle);
        _expectRevert(I.InvalidEvidence.selector);
        registry.freeze(id, bytes32(0), DECISION, OBSERVED_AT, FIRE_REVERSAL);
        _expectRevert(I.InvalidEvidence.selector);
        registry.freeze(id, FIRE_EVIDENCE, bytes32(0), OBSERVED_AT, FIRE_REVERSAL);
        _expectRevert(I.InvalidReason.selector);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT, 0);
        _expectRevert(I.InvalidReason.selector);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT, 2);
        _expectRevert(I.InvalidEvidence.selector);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, START + 1, FIRE_REVERSAL);
        vm.stopPrank();
        assertEq(uint8(registry.getBatch(id).creditStatus), uint8(I.CreditStatus.ACTIVE));
    }

    function test_staleObservationReverts() public {
        vm.prank(oracle);
        _expectRevert(I.StaleObservation.selector);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT - 1, FIRE_REVERSAL);
    }

    function test_observationEqualToBaselineIsAccepted() public {
        vm.prank(oracle);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT, FIRE_REVERSAL);
        assertEq(uint8(registry.getBatch(id).creditStatus), uint8(I.CreditStatus.FROZEN));
    }

    function test_repeatFreezeRevertsWithoutNewEvent() public {
        _freeze(id);
        I.BatchView memory first = registry.getBatch(id);

        vm.warp(START + 1 days);
        vm.recordLogs();
        vm.prank(oracle);
        _expectRevert(I.BatchNotActive.selector);
        registry.freeze(id, keccak256("newer-evidence"), keccak256("newer-decision"), START + 1 hours, FIRE_REVERSAL);
        assertEq(vm.getRecordedLogs().length, 0);

        I.BatchView memory again = registry.getBatch(id);
        assertEq(again.evidenceHash, first.evidenceHash);
        assertEq(again.decisionHash, first.decisionHash);
        assertEq(again.frozenAt, first.frozenAt);
        assertEq(again.lastObservedAt, first.lastObservedAt);
    }

    function test_frozenBatchBlocksBuyAndTransferForSellerAndBuyer() public {
        _freeze(id);

        vm.prank(recipient);
        _expectRevert(I.BatchNotActive.selector);
        registry.buy{value: PRICE}(id, 1);

        vm.prank(seller);
        _expectRevert(I.BatchNotActive.selector);
        registry.transfer(id, recipient, 1);

        vm.prank(buyer);
        _expectRevert(I.BatchNotActive.selector);
        registry.transfer(id, recipient, 1);

        assertEq(registry.balanceOf(id, seller), AMOUNT - 10);
        assertEq(registry.balanceOf(id, buyer), 10);
        assertEq(registry.balanceOf(id, recipient), 0);
    }

    function test_freezeIsBatchLevelOnly() public {
        uint256 other = _issue(keccak256("other"), seller);
        _freeze(id);
        vm.prank(seller);
        registry.transfer(other, recipient, 1);
        assertEq(registry.balanceOf(other, recipient), 1);
    }

    function test_proceedsEarnedBeforeFreezeRemainWithdrawable() public {
        _freeze(id);
        vm.prank(seller);
        registry.withdrawProceeds();
        assertEq(seller.balance, 10 * PRICE);
    }

    function test_reservedRevokedStatusBlocksCirculationAndFreeze() public {
        _setStatus(id, I.CreditStatus.REVOKED);
        assertEq(uint8(registry.getBatch(id).creditStatus), uint8(I.CreditStatus.REVOKED));

        vm.prank(recipient);
        _expectRevert(I.BatchNotActive.selector);
        registry.buy{value: PRICE}(id, 1);
        vm.prank(buyer);
        _expectRevert(I.BatchNotActive.selector);
        registry.transfer(id, recipient, 1);
        vm.prank(oracle);
        _expectRevert(I.BatchNotActive.selector);
        registry.freeze(id, FIRE_EVIDENCE, DECISION, OBSERVED_AT, FIRE_REVERSAL);
        assertEq(registry.balanceOf(id, buyer), 10);
    }
}
