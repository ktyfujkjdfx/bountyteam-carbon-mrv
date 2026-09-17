#!/usr/bin/env node
// Deterministic local deployment of CarbonCreditRegistry to Anvil.
//
// * Uses Anvil's unlocked default accounts through eth_sendTransaction: no private key or mnemonic
//   is read, printed or written anywhere.
// * Refuses to run against anything except a local chain (chain ID 31337 by default).
// * Writes <repo>/runtime/deployment.json (validated by contracts/deployment.schema.json, public data
//   only) and blockchain/runtime/deployment.build.json (fields the schema does not allow:
//   compiler/settings/source/receipts for the Backend handoff; Team Lead decision #4).
//
// Env: RPC_URL (default http://127.0.0.1:8545), DEPLOYMENT_DIR (default <repo>/runtime),
//      DEPLOYMENT_BUILD_DIR (default <repo>/blockchain/runtime),
//      EXPECTED_CHAIN_ID (default 31337), OWNER/ISSUER/ORACLE/BUYER/RECIPIENT address overrides.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {BLOCKCHAIN, ROOT, compile, checkAgainstFrozen} = require('./compile.cjs');

const RPC_URL = process.env.RPC_URL || 'http://127.0.0.1:8545';
const DEPLOYMENT_DIR = path.resolve(process.env.DEPLOYMENT_DIR || path.join(ROOT, 'runtime'));
const DEPLOYMENT_BUILD_DIR = path.resolve(process.env.DEPLOYMENT_BUILD_DIR || path.join(BLOCKCHAIN, 'runtime'));
const EXPECTED_CHAIN_ID = BigInt(process.env.EXPECTED_CHAIN_ID || '31337');
const ROLE_NAMES = ['owner', 'issuer', 'oracle', 'buyer', 'recipient'];

let rpcId = 0;
async function rpc(method, params = []) {
  let res;
  try {
    res = await fetch(RPC_URL, {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({jsonrpc: '2.0', id: ++rpcId, method, params}),
    });
  } catch (err) {
    throw new Error(`RPC ${RPC_URL} is unreachable (start it with: anvil). ${err.cause?.code || err.message}`);
  }
  const body = await res.json();
  if (body.error) throw new Error(`${method}: ${body.error.message}`);
  return body.result;
}

const word = hex => hex.replace(/^0x/, '').toLowerCase().padStart(64, '0');
const keccakUtf8 = text => rpc('web3_sha3', ['0x' + Buffer.from(text, 'utf8').toString('hex')]);

async function waitReceipt(txHash, label) {
  for (let i = 0; i < 200; i++) {
    const receipt = await rpc('eth_getTransactionReceipt', [txHash]);
    if (receipt) {
      if (receipt.status !== '0x1') throw new Error(`${label} transaction ${txHash} failed (status ${receipt.status})`);
      return receipt;
    }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error(`${label} transaction ${txHash} not mined; is Anvil mining?`);
}

async function send(from, to, data, label) {
  const tx = {from, data};
  if (to) tx.to = to;
  const hash = await rpc('eth_sendTransaction', [tx]);
  return waitReceipt(hash, label);
}

function gitSource() {
  const git = args => execFileSync('git', args, {cwd: ROOT, encoding: 'utf8'}).trim();
  try {
    return {
      commit: git(['rev-parse', 'HEAD']),
      dirty: git(['status', '--porcelain', '--', 'blockchain', 'contracts']) !== '',
    };
  } catch {
    return {commit: null, dirty: null};
  }
}

async function main() {
  const build = compile();
  const abiReport = checkAgainstFrozen(build);

  const chainId = BigInt(await rpc('eth_chainId'));
  if (chainId !== EXPECTED_CHAIN_ID) {
    throw new Error(`Refusing to deploy: chain ID ${chainId} != expected local ${EXPECTED_CHAIN_ID}`);
  }

  const accounts = await rpc('eth_accounts');
  const roles = {};
  ROLE_NAMES.forEach((name, i) => {
    const override = process.env[name.toUpperCase()];
    roles[name] = override || accounts[i];
    if (!/^0x[0-9a-fA-F]{40}$/.test(roles[name] || '')) {
      throw new Error(`No unlocked account for role ${name}; run a local Anvil node with default accounts`);
    }
  });
  if (new Set(ROLE_NAMES.map(n => roles[n].toLowerCase())).size !== ROLE_NAMES.length) {
    throw new Error('owner, issuer, oracle, buyer and recipient must be distinct accounts');
  }

  const deployReceipt = await send(roles.owner, null, build.bytecode + word(roles.owner), 'deploy');
  const address = deployReceipt.contractAddress;
  const code = await rpc('eth_getCode', [address, 'latest']);
  if (!code || code === '0x') throw new Error(`No runtime code at ${address}`);
  if ((code.length - 2) !== (build.deployedBytecode.length - 2)) {
    throw new Error('Deployed runtime code length differs from the compiled deployedBytecode');
  }
  const codeHash = await rpc('web3_sha3', [code]);

  const grants = {};
  for (const [role, fn, event] of [
    ['issuer', 'setIssuer(address,bool)', 'IssuerPermissionChanged(address,bool)'],
    ['oracle', 'setOracle(address,bool)', 'OraclePermissionChanged(address,bool)'],
  ]) {
    const data = '0x' + build.methodIdentifiers[fn] + word(roles[role]) + word('0x1');
    const receipt = await send(roles.owner, address, data, fn);
    const topic0 = await keccakUtf8(event);
    const log = receipt.logs.find(l => l.address.toLowerCase() === address.toLowerCase() && l.topics[0] === topic0);
    if (!log || log.topics[1] !== '0x' + word(roles[role]) || log.data !== '0x' + word('0x1')) {
      throw new Error(`${event} for ${role} not found in receipt ${receipt.transactionHash}`);
    }
    grants[role] = {tx_hash: receipt.transactionHash, block_number: Number(receipt.blockNumber), event};
  }

  const genesis = await rpc('eth_getBlockByNumber', ['0x0', false]);
  const deployment = {
    deployment_id: crypto.randomUUID(),
    chain_id: chainId.toString(),
    contract_address: address,
    deployment_tx_hash: deployReceipt.transactionHash,
    contract_code_hash: codeHash,
    abi_sha256: abiReport.frozen_abi_sha256,
    roles,
  };
  const buildInfo = {
    deployment_id: deployment.deployment_id,
    network: 'local-anvil',
    rpc_url: RPC_URL,
    genesis_block_hash: genesis.hash,
    deploy_block_number: Number(deployReceipt.blockNumber),
    deploy_block_hash: deployReceipt.blockHash,
    deployed_at: new Date().toISOString(),
    source: {...gitSource(), files_sha256: build.sourceSha256},
    compiler: build.compiler,
    settings: build.settings,
    abi: {
      path: 'contracts/contract-abi.json',
      sha256: abiReport.frozen_abi_sha256,
      byte_identical_to_frozen: true,
      functions: abiReport.functions,
      events: abiReport.events,
      errors: abiReport.errors,
      constructor: abiReport.constructor,
    },
    role_grants: grants,
    private_keys_included: false,
  };

  const manifestPath = path.join(DEPLOYMENT_DIR, 'deployment.json');
  const buildPath = path.join(DEPLOYMENT_BUILD_DIR, 'deployment.build.json');
  fs.mkdirSync(DEPLOYMENT_DIR, {recursive: true});
  fs.mkdirSync(DEPLOYMENT_BUILD_DIR, {recursive: true});
  fs.writeFileSync(manifestPath, JSON.stringify(deployment, null, 2) + '\n');
  fs.writeFileSync(buildPath, JSON.stringify(buildInfo, null, 2) + '\n');
  console.log(JSON.stringify({ok: true, manifest: manifestPath, build_info: buildPath, ...deployment}, null, 2));
}

main().catch(err => {
  console.error(`deploy failed: ${err.message}`);
  process.exit(1);
});
