import assert from 'node:assert/strict';
const saved = new Map();
const tabsMessaged = [];
globalThis.chrome = {
  storage: { local: {
    async get(keys){ const k = Array.isArray(keys) ? keys : [keys]; return Object.fromEntries(k.filter(x=>saved.has(x)).map(x=>[x,saved.get(x)])); },
    async set(fields){ for(const [k,v] of Object.entries(fields))saved.set(k,v); },
    async remove(key){saved.delete(key);},
  }},
  tabs: { async query(){return [{id:41}];},async sendMessage(tabId,msg){tabsMessaged.push([tabId,msg]);} },
};
const {MODEL_BYTES}=await import('./model-store.js');
const {installBuiltinNexto,convertCompatibleModelFile}=await import('./model-import.js');
const native=new Float32Array(MODEL_BYTES/4);
native.fill(0.375);
const file={name:'nexto-model.bin', size:MODEL_BYTES, arrayBuffer:async()=>native.buffer};
const result=await installBuiltinNexto(file);
assert.equal(result.name,'Original Nexto');
assert.equal(saved.get('selectedModel'),'nexto');
assert.equal(saved.get('builtinNextoSource'),'nexto-model.bin');
assert.equal(saved.get('builtinNextoWeights').length>2_300_000,true);
const restored=Uint8Array.from(atob(saved.get('builtinNextoWeights')),x=>x.charCodeAt(0)).buffer;
assert.equal(new Float32Array(restored)[0],0.375);
assert.ok(tabsMessaged.some(([,msg])=>msg.type==='gct-model-changed'));
console.log('PASS: original Nexto restoration via .bin, storage persistence, exact weights, live tab notification.');
