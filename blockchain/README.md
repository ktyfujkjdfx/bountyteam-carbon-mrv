# Blockchain module — CarbonCreditRegistry (P0)

Owner: Blockchain (@efimchuk20006-pixel). Issue: #4. Consumer: Backend chain adapter.

A deployable local implementation of the frozen `contracts-v1.0.0` interface
(`contracts/contract-interface.sol`). It stores batches with real per-holder balances,
accepts exact-price test purchases, pays sellers through pull-payment, and lets only the
oracle freeze an `ACTIVE` batch. After `FROZEN`, direct `buy` and `transfer` revert in the
contract itself.

This is a minimal hackathon prototype on local Anvil. It is **not** ERC-3643, not a
production registry, and not deployed to a public network. The contract enforces
permissions and state. It does **not** decide whether a fire happened: Backend makes that
decision and is the only runtime oracle sender.

## Layout

| Path | Purpose |
|---|---|
| `src/CarbonCreditRegistry.sol` | Implementation; inherits `CarbonCreditRegistrySpec` from `contracts/contract-interface.sol` |
| `test/*.t.sol` | Foundry unit, security and invariant tests |
| `tools/compile.cjs` | solc-js 0.8.30 build (the same pipeline that produced the frozen ABI) |
| `tools/check-abi.cjs` | Byte-identical ABI check against `contracts/contract-abi.json` + forge/solc-js bytecode equality |
| `tools/deploy-local.cjs` | Deterministic Anvil deploy + seed (role grants); writes the deployment manifest |
| `scripts/e2e_local.py` | Backend-adapter-style integration smoke (web3.py, frozen ABI only; own throwaway Anvil) |
| `foundry.toml`, `soldeer.lock` | Pinned compiler/EVM settings and `forge-std` 1.10.0 |

## Prerequisites

- Foundry **1.8.3** (`forge`, `anvil`, `cast`): `brew install foundry` on macOS, or
  `curl -L https://foundry.paradigm.xyz | bash && foundryup --install v1.8.3`
  on Linux, macOS, WSL or Git Bash.
- Node.js from `.nvmrc` and the root `npm ci --ignore-scripts`. The build uses root `solc` 0.8.30.
- The project `.venv` with `requirements-contracts.txt`, plus `blockchain/requirements-chain.txt` for the smoke.

One-time setup from the repository root:

```bash
npm ci --ignore-scripts
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements-contracts.txt -r blockchain/requirements-chain.txt
cd blockchain && forge soldeer install && cd ..
```

On Windows PowerShell, use `.\.venv\Scripts\python.exe`, `npm.cmd`, and
`$env:PYTHONUTF8='1'`.

## Commands

All commands run from `blockchain/` unless noted otherwise.

| What | Command |
|---|---|
| Start local chain (terminal 1) | `anvil --port 8545 --chain-id 31337` (or `npm run chain`) |
| Compile + all tests + ABI check | `npm run verify` |
| Compile only | `forge build` |
| Tests only | `forge test` (`forge test -vvv` for traces) |
| ABI compatibility only | `npm run check:abi` |
| Deploy + seed roles (terminal 2) | `npm run deploy` |
| Integration smoke (own throwaway Anvil) | `../.venv/bin/python scripts/e2e_local.py` |
| CI (GitHub Actions) | `.github/workflows/blockchain.yml`: build, all forge tests, ABI check, Anvil deploy, schema validation, web3.py smoke |
| Shared checks (repo root) | `python -m pytest -q && npm run check:abi && git diff --check` |

`npm run deploy` always deploys a **new** contract. On a fresh Anvil the address is
`0x5FbDB2315678afecb367f032d93F642f64180aa3`, but `deployment_id` is a new UUID every time.

**What "seed" means here.** The deploy command is also the seed command. It assigns the
issuer and oracle roles (owner → `setIssuer`, `setOracle`), checks both permission events,
and relies on Anvil's pre-funded dev accounts. On purpose, it does **not** issue a demo batch.
Issuance belongs to Backend: the issuance key is
`SHA-256(JCS({plot_id, demo_authorization_id, deployment_id}))`, and the frozen demo
authorization `SYNTHETIC-AUTH-001` is `single_use`. A pre-seeded batch would consume or
contradict that authorization.

`scripts/e2e_local.py` never touches the shared deployment. It starts its own Anvil on a
free port, deploys into a temp dir, runs the flow, restarts that Anvil to prove restart
detection, and writes `blockchain/runtime/e2e-evidence.json`. Backend remains the only
runtime oracle sender on the shared deployment.

## Deployment handoff to Backend

`npm run deploy` writes two public files. Both `runtime/` directories are gitignored, and
neither file contains a private key.

1. `runtime/deployment.json` validates against `contracts/deployment.schema.json`:
   `deployment_id`, `chain_id` (`"31337"`), `contract_address`, `deployment_tx_hash`,
   `contract_code_hash` (keccak256 of the runtime code, the same value as `EXTCODEHASH`),
   `abi_sha256`, and `roles`.
2. `blockchain/runtime/deployment.build.json` (Team Lead decision #4) holds the details that do not fit the schema: source
   commit and dirty flag, source SHA-256s, compiler `0.8.30+commit.73712a01`, settings
   (`cancun`, optimizer 200 runs, no CBOR metadata), deploy block number and hash,
   genesis block hash, and role-grant tx hashes.

**ABI.** Backend uses `contracts/contract-abi.json` unchanged. The implementation's compiled
public ABI, without the constructor, is byte-identical to it
(`abi_sha256 = 0xed7cf494ad115e164ce905047eca10211946f4eb9b1a3c8c5ac4143f4901d34c`).
Nobody edits ABI JSON by hand.

**Roles on a default Anvil** (public, well-known Anvil dev accounts, unlocked by Anvil):

| Role | Anvil account | Address |
|---|---|---|
| owner (deployer; grants roles) | #0 | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` |
| issuer (also the demo seller) | #1 | `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` |
| oracle (Backend runtime sender only) | #2 | `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC` |
| buyer | #3 | `0x90F79bf6EB2c4f870365E785982E1f101E93b906` |
| recipient | #4 | `0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65` |

The deploy script requires all five addresses to be distinct, and CI checks that too. The
owner cannot grant itself issuer or oracle (Team Lead decision: roles stay separated). The
seller is not a separate schema role: `config/demo-authorizations.json` sets
`seller_actor: "issuer"`, so the demo seller address is the issuer address. Buyer and
recipient are always different from the seller, and the contract rejects a seller buying its
own batch.

You can override them with `OWNER=… ISSUER=… ORACLE=… BUYER=… RECIPIENT=…`. `RPC_URL` and
`DEPLOYMENT_DIR` (manifest) and `DEPLOYMENT_BUILD_DIR` (build info) are also configurable. The script refuses any chain ID other than 31337
(`EXPECTED_CHAIN_ID`).

**How Backend gets its configuration without committed secrets.** Backend reads
`runtime/deployment.json` and `contracts/contract-abi.json` at startup and takes `RPC_URL`
from its own environment. It signs through Anvil's unlocked oracle account, or with the
oracle dev key that `anvil` prints at startup, passed through a local, uncommitted
environment variable. Never reuse those keys with real assets.

**Startup identity check (Backend must refuse to operate on mismatch):**

1. `eth_chainId` equals `chain_id`.
2. `keccak256(eth_getCode(contract_address))` equals `contract_code_hash`. Code is empty after an Anvil restart.
3. `sha256(contracts/contract-abi.json)` equals `abi_sha256`.
4. A different `deployment_id` means a new deployment: do not reuse batches stored in the DB.

### Events (topic0) and custom errors

| Event | Indexed | Data | topic0 |
|---|---|---|---|
| `IssuerPermissionChanged` | `account` | `allowed` | `0x40f3449b…19f03` |
| `OraclePermissionChanged` | `account` | `allowed` | `0xe74325c6…9953a` |
| `Issued` | `batchId`, `issuanceKey`, `seller` | `amount`, `evidenceHash` | `0x7fea36bb…10d07` |
| `Purchased` | `batchId`, `buyer` | `amount`, `paidWei` | `0x2d422c18…a18d4` |
| `Transferred` | `batchId`, `from`, `to` | `amount` | `0x6d7c707b…98453` |
| `Frozen` | `batchId`, `evidenceHash` | `decisionHash`, `observedAt`, `reasonCode` | `0x880329e1…fab30` |
| `ProceedsWithdrawn` | `seller` | `amountWei` | `0x0f2fb75c…369ba` |

| Error | Selector | Raised when |
|---|---|---|
| `Unauthorized` | `0x82b42900` | Non-owner `setIssuer`/`setOracle`; owner grants a role to itself; non-issuer `issue`; non-oracle `freeze` |
| `UnknownBatch` | `0x119a7627` | Batch id never issued (including id 0) in any function |
| `DuplicateIssuance` | `0x53e2a57a` | `issuanceKey` already used |
| `InvalidAmount` | `0x2c5211c6` | amount is 0, or `unitPriceWei` is 0 at issue |
| `InvalidAddress` | `0xe6c4247b` | zero owner/role/seller/recipient; transfer to self; seller buys own batch |
| `InsufficientBalance` | `0xf4d678b8` | seller inventory or sender balance too small |
| `BatchNotActive` | `0xb5cf512a` | `buy`/`transfer`/`freeze` on `FROZEN` or reserved `REVOKED` (includes repeat freeze) |
| `IncorrectPayment` | `0x569e8c11` | `msg.value != amount * unitPriceWei` (overflow included) |
| `StaleObservation` | `0x158767e7` | freeze `observedAt < lastObservedAt` |
| `InvalidEvidence` | `0xc9779e3c` | zero `issuanceKey`/`evidenceHash`/`decisionHash`; `observedAt` is 0 or in the future |
| `InvalidReason` | `0xdee26e4c` | `reasonCode != 1` (`FIRE_REVERSAL`) |
| `InvalidPlot` | `0xc0c9cf4e` | empty `plotId` |
| `NoProceeds` | `0xc4d8fa87` | `withdrawProceeds` with nothing accrued |
| `PaymentFailed` | `0xf499da20` | seller rejected the ETH transfer (proceeds are kept) |
| `ReentrantCall` | `0x37ed32e8` | re-entry into `buy`/`transfer`/`withdrawProceeds` |

A transaction is `CONFIRMED` only when receipt `status == 1`, the expected event is decoded
from that receipt, **and** `getBatch`/`balanceOf` readback matches.

### Manual reproduction: ACTIVE → FROZEN → transfer revert (`cast`)

This sends `freeze` from the oracle account, so run it **only on a separate verification
Anvil**, never on the deployment Backend uses as the single oracle sender. From `blockchain/`:

```bash
anvil --port 8546 --chain-id 31337 --silent &          # verification chain, not the shared 8545
export ETH_RPC_URL=http://127.0.0.1:8546
VERIFY_DIR=$(mktemp -d)
RPC_URL=$ETH_RPC_URL DEPLOYMENT_DIR=$VERIFY_DIR DEPLOYMENT_BUILD_DIR=$VERIFY_DIR npm run deploy
REG=$(node -p "require('$VERIFY_DIR/deployment.json').contract_address")
ISSUER=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
ORACLE=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
BUYER=0x90F79bf6EB2c4f870365E785982E1f101E93b906
RECIPIENT=0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65
OBS=$(( $(cast block latest -f timestamp) - 3600 ))
BATCH_T='(string,bytes32,address,uint256,uint8,uint256,bytes32,bytes32,uint64,uint64,uint64)'

# issue 100 units at 0.001 ETH to the issuer/seller -> Issued, batchId 1 on a fresh deployment
cast send --unlocked --from $ISSUER $REG "issue(bytes32,string,address,uint256,uint256,bytes32,uint64)" \
  $(cast keccak demo-issuance-1) SYNTHETIC-PLOT-001 $ISSUER 100 1000000000000000 $(cast keccak demo-evidence) $OBS
# buy 10 with exact payment, then transfer 3 while ACTIVE
cast send --unlocked --from $BUYER $REG "buy(uint256,uint256)" 1 10 --value 10000000000000000
cast send --unlocked --from $BUYER $REG "transfer(uint256,address,uint256)" 1 $RECIPIENT 3
cast call $REG "balanceOf(uint256,address)(uint256)" 1 $BUYER          # 7
# oracle freeze (Backend does this in the real flow)
cast send --unlocked --from $ORACLE $REG "freeze(uint256,bytes32,bytes32,uint64,uint8)" \
  1 $(cast keccak fire-evidence) $(cast keccak fire-decision) $OBS 1
cast call $REG "getBatch(uint256)($BATCH_T)" 1                         # 5th field = 1 (FROZEN)
# direct transfer / repeat freeze now revert with BatchNotActive (0xb5cf512a)
cast call --from $BUYER $REG "transfer(uint256,address,uint256)" 1 $RECIPIENT 1
cast call --from $ORACLE $REG "freeze(uint256,bytes32,bytes32,uint64,uint8)" \
  1 $(cast keccak fire-evidence-2) $(cast keccak fire-decision-2) $OBS 1
cast call $REG "balanceOf(uint256,address)(uint256)" 1 $BUYER          # still 7
kill %1                                                  # stop the verification Anvil
```

The same flow runs automatically in `scripts/e2e_local.py`, with receipts, decoded events,
readback, stale-observation and unknown-batch reverts, mined reverted transactions with zero
logs, and Anvil-restart detection.

## Implemented invariants

- `owner` is set once in the constructor (zero address rejected). Only the owner manages
  issuer/oracle, and nobody can grant a role to itself. There is no owner transfer, backdoor
  or manual state edit.
- `issue` is issuer-only, `freeze` is oracle-only. A revoked role loses access at once.
- Existence is an explicit flag and batch ids start at 1, so the default enum value never
  makes an unknown batch `ACTIVE`.
- Issuance keys are unique. A failed issue does not consume its key.
- Real balances live in `batchId → holder → amount`. `issue` credits the seller, `buy` moves
  seller inventory to the buyer, `transfer` moves sender balance to the recipient.
  `totalSupply` never changes, and the sum of balances always equals `totalSupply`
  (fuzzed invariant).
- `buy` requires an exact payment and credits proceeds. There is no external call in
  `buy`/`transfer`. `withdrawProceeds` zeroes the balance before the single external call,
  is `nonReentrant`, and the contract's ETH always equals paid minus withdrawn (fuzzed
  invariant).
- `freeze` works only for an existing `ACTIVE` batch, with non-zero raw evidence/decision
  hashes (not re-hashed), `reasonCode == 1`, and `lastObservedAt <= observedAt <= now`. It
  stores status, hashes, `frozenAt` and `lastObservedAt` and emits exactly one `Frozen`.
  A repeat call reverts with no event.
- `FROZEN` and reserved `REVOKED` batches reject `buy`, `transfer` and `freeze`, and
  balances stay intact. Nothing sets `REVOKED`. There is no revoke/unfreeze.

## Limitations

- Local Anvil only; Sepolia is P2. Dev accounts are public test keys.
- The `issue` observation must not be in the future relative to the chain clock (Anvil uses
  wall-clock time).
- The owner cannot be changed, and there is no on-chain getter for roles. The deployment
  manifest and permission events are the source of truth.
- `scripts/e2e_local.py` is Blockchain-side evidence that the handed-off ABI and manifest are
  enough for a web3.py adapter. It is not Backend's real adapter, and it uses synthetic hashes
  instead of Backend's canonical JCS/SHA-256 derivations. Joint Backend adapter integration is
  the next handoff step.
- The deploy/seed step does not issue a demo batch; issuance is Backend's (see above).
