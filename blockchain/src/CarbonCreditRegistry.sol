// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {CarbonCreditRegistrySpec} from "shared-contracts/contract-interface.sol";

/// @title CarbonCreditRegistry — local P0 implementation of the frozen `contracts-v1.0.0` interface.
/// @notice Minimal registry of carbon-credit batches with real per-holder balances, exact-price
/// test purchases, pull-payment proceeds and an oracle-only batch-level freeze.
/// It is NOT ERC-3643 and NOT a production registry. The contract enforces permissions and
/// state; it never decides whether a fire occurred (that is the Backend oracle decision).
/// @dev The public surface (functions, events, errors, tuple, enum) is inherited from the frozen
/// specification and must stay byte-identical to `contracts/contract-abi.json`. Therefore no
/// public state variables, extra functions, events or errors may be added here.
/// `REVOKED` is a reserved status: nothing in this contract ever sets it.
contract CarbonCreditRegistry is CarbonCreditRegistrySpec {
    /// @dev `reasonCode` of the only freeze reason defined by policy v1 (`FIRE_REVERSAL`).
    uint8 private constant REASON_FIRE_REVERSAL = 1;

    uint256 private constant UNLOCKED = 1;
    uint256 private constant LOCKED = 2;

    address private immutable _owner;

    mapping(address account => bool) private _issuers;
    mapping(address account => bool) private _oracles;

    /// @dev Batch ids start at 1, so id 0 is never a valid batch.
    uint256 private _nextBatchId = 1;
    /// @dev Explicit existence flag: the default enum value (ACTIVE) must never make an
    /// unknown batch look active.
    mapping(uint256 batchId => bool) private _exists;
    mapping(uint256 batchId => BatchView) private _batches;
    mapping(bytes32 issuanceKey => bool) private _usedIssuanceKeys;
    mapping(uint256 batchId => mapping(address holder => uint256)) private _balances;
    mapping(address seller => uint256) private _proceeds;

    uint256 private _lock = UNLOCKED;

    // Zero address is rejected by the CarbonCreditRegistrySpec constructor.
    // forge-lint: disable-next-line(missing-zero-check)
    constructor(address initialOwner) CarbonCreditRegistrySpec(initialOwner) {
        _owner = initialOwner;
    }

    modifier onlyOwner() {
        if (msg.sender != _owner) revert Unauthorized();
        _;
    }

    modifier nonReentrant() {
        if (_lock == LOCKED) revert ReentrantCall();
        _lock = LOCKED;
        _;
        _lock = UNLOCKED;
    }

    // ---------------------------------------------------------------- permissions

    /// @notice Grants or revokes the issuer role. Only the owner; nobody can assign a role to itself.
    function setIssuer(address account, bool allowed) external onlyOwner {
        _checkRoleAccount(account);
        _issuers[account] = allowed;
        emit IssuerPermissionChanged(account, allowed);
    }

    /// @notice Grants or revokes the oracle role. Only the owner; nobody can assign a role to itself.
    function setOracle(address account, bool allowed) external onlyOwner {
        _checkRoleAccount(account);
        _oracles[account] = allowed;
        emit OraclePermissionChanged(account, allowed);
    }

    // ---------------------------------------------------------------- issuance

    /// @notice Issues a new ACTIVE batch; the whole `amount` is credited to `seller`.
    function issue(
        bytes32 issuanceKey,
        string calldata plotId,
        address seller,
        uint256 amount,
        uint256 unitPriceWei,
        bytes32 evidenceHash,
        uint64 observedAt
    ) external returns (uint256 batchId) {
        if (!_issuers[msg.sender]) revert Unauthorized();
        if (issuanceKey == bytes32(0) || evidenceHash == bytes32(0)) revert InvalidEvidence();
        if (bytes(plotId).length == 0) revert InvalidPlot();
        if (seller == address(0)) revert InvalidAddress();
        if (amount == 0 || unitPriceWei == 0) revert InvalidAmount();
        _checkObservationTime(observedAt);
        if (_usedIssuanceKeys[issuanceKey]) revert DuplicateIssuance();

        batchId = _nextBatchId++;
        _usedIssuanceKeys[issuanceKey] = true;
        _exists[batchId] = true;

        BatchView storage batch = _batches[batchId];
        batch.plotId = plotId;
        batch.issuanceKey = issuanceKey;
        batch.seller = seller;
        batch.totalSupply = amount;
        batch.creditStatus = CreditStatus.ACTIVE;
        batch.unitPriceWei = unitPriceWei;
        batch.evidenceHash = evidenceHash;
        // forge-lint: disable-next-line(unsafe-typecast)
        batch.issuedAt = uint64(block.timestamp);
        batch.lastObservedAt = observedAt;

        _balances[batchId][seller] = amount;

        emit Issued(batchId, issuanceKey, seller, amount, evidenceHash);
    }

    // ---------------------------------------------------------------- circulation

    /// @notice Buys `amount` units from the batch seller for exactly `amount * unitPriceWei`.
    /// @dev Pull payment: proceeds are credited, never pushed, so there is no external call here.
    function buy(uint256 batchId, uint256 amount) external payable nonReentrant {
        BatchView storage batch = _activeBatch(batchId);
        if (amount == 0) revert InvalidAmount();
        address seller = batch.seller;
        if (msg.sender == seller) revert InvalidAddress();
        if (_balances[batchId][seller] < amount) revert InsufficientBalance();
        uint256 price = batch.unitPriceWei;
        if (amount > type(uint256).max / price || msg.value != amount * price) revert IncorrectPayment();

        _balances[batchId][seller] -= amount;
        _balances[batchId][msg.sender] += amount;
        _proceeds[seller] += msg.value;

        emit Purchased(batchId, msg.sender, amount, msg.value);
    }

    /// @notice Moves `amount` ACTIVE units from the caller to `to`.
    function transfer(uint256 batchId, address to, uint256 amount) external nonReentrant {
        _activeBatch(batchId);
        if (to == address(0) || to == msg.sender) revert InvalidAddress();
        if (amount == 0) revert InvalidAmount();
        uint256 fromBalance = _balances[batchId][msg.sender];
        if (fromBalance < amount) revert InsufficientBalance();

        _balances[batchId][msg.sender] = fromBalance - amount;
        _balances[batchId][to] += amount;

        emit Transferred(batchId, msg.sender, to, amount);
    }

    // ---------------------------------------------------------------- restriction

    /// @notice Freezes a whole ACTIVE batch using raw Backend evidence/decision hashes (not re-hashed).
    /// @dev A repeat call on a FROZEN batch reverts with `BatchNotActive` and emits nothing.
    function freeze(
        uint256 batchId,
        bytes32 evidenceHash,
        bytes32 decisionHash,
        uint64 observedAt,
        uint8 reasonCode
    ) external {
        if (!_oracles[msg.sender]) revert Unauthorized();
        BatchView storage batch = _activeBatch(batchId);
        if (evidenceHash == bytes32(0) || decisionHash == bytes32(0)) revert InvalidEvidence();
        if (reasonCode != REASON_FIRE_REVERSAL) revert InvalidReason();
        if (observedAt < batch.lastObservedAt) revert StaleObservation();
        _checkObservationTime(observedAt);

        batch.creditStatus = CreditStatus.FROZEN;
        batch.evidenceHash = evidenceHash;
        batch.decisionHash = decisionHash;
        // forge-lint: disable-next-line(unsafe-typecast)
        batch.frozenAt = uint64(block.timestamp);
        batch.lastObservedAt = observedAt;

        emit Frozen(batchId, evidenceHash, decisionHash, observedAt, reasonCode);
    }

    // ---------------------------------------------------------------- proceeds

    /// @notice Sends all accumulated purchase proceeds of the caller to the caller.
    function withdrawProceeds() external nonReentrant {
        uint256 amountWei = _proceeds[msg.sender];
        if (amountWei == 0) revert NoProceeds();

        _proceeds[msg.sender] = 0;
        emit ProceedsWithdrawn(msg.sender, amountWei);

        // Guarded by nonReentrant; proceeds are zeroed before the call (checks-effects-interactions).
        // forge-lint: disable-next-line(reentrancy-eth)
        (bool ok,) = payable(msg.sender).call{value: amountWei}("");
        if (!ok) revert PaymentFailed();
    }

    // ---------------------------------------------------------------- readback

    function balanceOf(uint256 batchId, address account) external view returns (uint256) {
        _existingBatch(batchId);
        return _balances[batchId][account];
    }

    function getBatch(uint256 batchId) external view returns (BatchView memory) {
        return _existingBatch(batchId);
    }

    // ---------------------------------------------------------------- internal

    function _existingBatch(uint256 batchId) private view returns (BatchView storage) {
        if (!_exists[batchId]) revert UnknownBatch();
        return _batches[batchId];
    }

    function _activeBatch(uint256 batchId) private view returns (BatchView storage batch) {
        batch = _existingBatch(batchId);
        if (batch.creditStatus != CreditStatus.ACTIVE) revert BatchNotActive();
    }

    function _checkRoleAccount(address account) private view {
        if (account == address(0)) revert InvalidAddress();
        if (account == msg.sender) revert Unauthorized();
    }

    /// @dev An observation must have a real timestamp and cannot come from the future.
    function _checkObservationTime(uint64 observedAt) private view {
        // forge-lint: disable-next-line(block-timestamp)
        if (observedAt == 0 || observedAt > block.timestamp) revert InvalidEvidence();
    }
}
