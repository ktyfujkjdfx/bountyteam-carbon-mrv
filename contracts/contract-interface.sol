// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Interface only. NO deployed ledger or token implementation is supplied.
interface ICarbonCreditRegistry {
    enum CreditStatus { ACTIVE, FROZEN, REVOKED }
    struct BatchView {
        string plotId;
        bytes32 issuanceKey;
        address seller;
        uint256 totalSupply;
        CreditStatus creditStatus;
        uint256 unitPriceWei;
        bytes32 evidenceHash;
        bytes32 decisionHash;
        uint64 issuedAt;
        uint64 frozenAt;
        uint64 lastObservedAt;
    }
    error Unauthorized();
    error UnknownBatch();
    error DuplicateIssuance();
    error InvalidAmount();
    error InvalidAddress();
    error InsufficientBalance();
    error BatchNotActive();
    error IncorrectPayment();
    error StaleObservation();
    error InvalidEvidence();
    error InvalidReason();
    error InvalidPlot();
    error NoProceeds();
    error PaymentFailed();
    error ReentrantCall();

    event IssuerPermissionChanged(address indexed account, bool allowed);
    event OraclePermissionChanged(address indexed account, bool allowed);
    event Issued(uint256 indexed batchId, bytes32 indexed issuanceKey,
                 address indexed seller, uint256 amount, bytes32 evidenceHash);
    event Purchased(uint256 indexed batchId, address indexed buyer,
                    uint256 amount, uint256 paidWei);
    event Transferred(uint256 indexed batchId, address indexed from,
                      address indexed to, uint256 amount);
    event Frozen(uint256 indexed batchId, bytes32 indexed evidenceHash,
                 bytes32 decisionHash, uint64 observedAt, uint8 reasonCode);
    event ProceedsWithdrawn(address indexed seller, uint256 amountWei);

    function setIssuer(address account, bool allowed) external;
    function setOracle(address account, bool allowed) external;
    function issue(bytes32 issuanceKey, string calldata plotId, address seller,
                   uint256 amount, uint256 unitPriceWei, bytes32 evidenceHash,
                   uint64 observedAt) external returns (uint256 batchId);
    function buy(uint256 batchId, uint256 amount) external payable;
    function transfer(uint256 batchId, address to, uint256 amount) external;
    function freeze(uint256 batchId, bytes32 evidenceHash, bytes32 decisionHash,
                    uint64 observedAt, uint8 reasonCode) external;
    function balanceOf(uint256 batchId, address account) external view returns (uint256);
    function getBatch(uint256 batchId) external view returns (BatchView memory);
    function withdrawProceeds() external;
}

/// @notice Abstract ABI/deployment-signature specification, NOT an implementation.
/// The implementation must initialize owner to initialOwner and enforce all policy.
abstract contract CarbonCreditRegistrySpec is ICarbonCreditRegistry {
    constructor(address initialOwner) {
        if (initialOwner == address(0)) revert InvalidAddress();
    }
}
