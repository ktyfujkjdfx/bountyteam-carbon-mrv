#!/usr/bin/env node
// Verifies that the compiled implementation matches the frozen contracts-v1.0.0 ABI and that the
// Foundry build (used by tests) produces exactly the same bytecode as the solc-js deploy pipeline.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {BLOCKCHAIN, CONTRACT, compile, checkAgainstFrozen} = require('./compile.cjs');

const build = compile();
const report = checkAgainstFrozen(build);

const forgeArtifact = path.join(BLOCKCHAIN, 'out', 'CarbonCreditRegistry.sol', `${CONTRACT}.json`);
if (fs.existsSync(forgeArtifact)) {
  const forge = JSON.parse(fs.readFileSync(forgeArtifact, 'utf8'));
  if (forge.bytecode.object !== build.bytecode || forge.deployedBytecode.object !== build.deployedBytecode) {
    throw new Error('Foundry build bytecode differs from solc-js build; check foundry.toml vs tools/compile.cjs settings');
  }
  report.forge_bytecode_identical = true;
} else {
  report.forge_bytecode_identical = 'not checked (run `forge build` first)';
}

console.log(JSON.stringify(report));
