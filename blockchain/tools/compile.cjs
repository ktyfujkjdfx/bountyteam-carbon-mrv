// Compiles CarbonCreditRegistry with the repository's pinned solc-js (the same compiler pipeline
// that produced the frozen contracts/contract-abi.json) and checks it against the frozen ABI.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const solc = require('solc');

const BLOCKCHAIN = path.resolve(__dirname, '..');
const ROOT = path.resolve(BLOCKCHAIN, '..');
const SOURCE = 'src/CarbonCreditRegistry.sol';
const CONTRACT = 'CarbonCreditRegistry';
const FROZEN_ABI_PATH = path.join(ROOT, 'contracts', 'contract-abi.json');
const FROZEN_BUILD_PATH = path.join(ROOT, 'contracts', 'abi-build.json');

// Must match blockchain/foundry.toml so forge tests and the deployed bytecode are identical.
const SETTINGS = {
  evmVersion: 'cancun',
  optimizer: {enabled: true, runs: 200},
  metadata: {bytecodeHash: 'none', appendCBOR: false},
  remappings: ['shared-contracts/=contracts/'],
  outputSelection: {'*': {'*': ['abi', 'evm.bytecode.object', 'evm.deployedBytecode.object', 'evm.methodIdentifiers']}},
};

const sha256 = data => '0x' + crypto.createHash('sha256').update(data).digest('hex');
const readText = file => fs.readFileSync(file, 'utf8');

function compile() {
  const sources = {
    [SOURCE]: {content: readText(path.join(BLOCKCHAIN, SOURCE))},
    'contracts/contract-interface.sol': {content: readText(path.join(ROOT, 'contracts', 'contract-interface.sol'))},
  };
  const input = {language: 'Solidity', sources, settings: SETTINGS};
  const out = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (out.errors || []).filter(e => e.severity === 'error');
  if (errors.length) throw new Error(errors.map(e => e.formattedMessage).join('\n'));
  const artifact = out.contracts[SOURCE][CONTRACT];
  return {
    compiler: solc.version(),
    settings: {evmVersion: SETTINGS.evmVersion, optimizer: SETTINGS.optimizer, metadata: SETTINGS.metadata},
    abi: artifact.abi,
    bytecode: '0x' + artifact.evm.bytecode.object,
    deployedBytecode: '0x' + artifact.evm.deployedBytecode.object,
    methodIdentifiers: artifact.evm.methodIdentifiers,
    sourceSha256: {
      [`blockchain/${SOURCE}`]: sha256(sources[SOURCE].content),
      'contracts/contract-interface.sol': sha256(sources['contracts/contract-interface.sol'].content),
    },
  };
}

const EXPECTED_CONSTRUCTOR = {
  inputs: [{internalType: 'address', name: 'initialOwner', type: 'address'}],
  stateMutability: 'nonpayable',
  type: 'constructor',
};

/// Throws unless the implementation's public surface is byte-identical to the frozen ABI.
function checkAgainstFrozen(build) {
  const frozenBytes = readText(FROZEN_ABI_PATH);
  const frozenBuild = JSON.parse(readText(FROZEN_BUILD_PATH));
  const constructors = build.abi.filter(x => x.type === 'constructor');
  const surface = build.abi.filter(x => x.type !== 'constructor');
  const surfaceBytes = JSON.stringify(surface, null, 2) + '\n';
  const problems = [];

  if (build.compiler !== frozenBuild.compiler) problems.push(`compiler ${build.compiler} != frozen ${frozenBuild.compiler}`);
  if (sha256(frozenBytes) !== frozenBuild.abi_sha256) problems.push('contracts/contract-abi.json does not match abi-build.json');
  if (JSON.stringify(constructors) !== JSON.stringify([EXPECTED_CONSTRUCTOR])) {
    problems.push('constructor must be exactly constructor(address initialOwner)');
  }
  if (surfaceBytes !== frozenBytes) {
    const key = x => `${x.type}:${x.name}`;
    const frozenKeys = new Set(JSON.parse(frozenBytes).map(key));
    const implKeys = new Set(surface.map(key));
    const missing = [...frozenKeys].filter(k => !implKeys.has(k));
    const extra = [...implKeys].filter(k => !frozenKeys.has(k));
    problems.push(`public ABI differs from frozen ABI (missing: [${missing}], extra: [${extra}], or changed types/indexed/names)`);
  }
  if (problems.length) throw new Error('ABI compatibility FAILED:\n- ' + problems.join('\n- '));

  const count = type => surface.filter(x => x.type === type).length;
  return {
    ok: true,
    compiler: build.compiler,
    frozen_abi_sha256: frozenBuild.abi_sha256,
    implementation_surface_sha256: sha256(surfaceBytes),
    functions: count('function'),
    events: count('event'),
    errors: count('error'),
    constructor: 'constructor(address initialOwner)',
  };
}

module.exports = {BLOCKCHAIN, ROOT, CONTRACT, SETTINGS, compile, checkAgainstFrozen, sha256};
