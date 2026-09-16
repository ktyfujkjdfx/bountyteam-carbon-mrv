const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const solc = require('solc');
const root = path.resolve(__dirname, '..');
const sourceName = 'contract-interface.sol';
const source = fs.readFileSync(path.join(root, 'contracts', sourceName), 'utf8');
const input = {language:'Solidity', sources:{[sourceName]:{content:source}},
  settings:{evmVersion:'cancun', outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}};
const out = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = (out.errors || []).filter(e => e.severity === 'error');
if(errors.length) throw new Error(errors.map(e => e.formattedMessage).join('\n'));
const artifact = out.contracts[sourceName].CarbonCreditRegistrySpec;
if(artifact.evm.bytecode.object !== '') throw new Error('Specification must remain abstract');
const digest = data => '0x'+crypto.createHash('sha256').update(data).digest('hex');
const abiBytes = JSON.stringify(artifact.abi, null, 2)+'\n';
const manifest = {compiler:solc.version(), source_file:sourceName, source_sha256:digest(source),
  abi_sha256:digest(abiBytes), evm_version:'cancun', specification_only:true,
  deployable_bytecode:false, deployed_contract_address:null};
const outputs = {'contract-abi.json':abiBytes,'abi-build.json':JSON.stringify(manifest,null,2)+'\n'};
for(const [file, bytes] of Object.entries(outputs)) {
  const target=path.join(root,'contracts',file);
  if(process.argv.includes('--check')) {
    if(fs.readFileSync(target,'utf8')!==bytes) throw new Error('Stale generated file: '+file);
  } else fs.writeFileSync(target,bytes);
}
console.log(JSON.stringify({ok:true, compiler:solc.version(), functions:artifact.abi.filter(x=>x.type==='function').length,
  events:artifact.abi.filter(x=>x.type==='event').length, specification_only:true}));
