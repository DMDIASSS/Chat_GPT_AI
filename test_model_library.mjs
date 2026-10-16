import assert from 'node:assert/strict';
const entries = new Map();
const messages = [];
globalThis.chrome = {
  storage: {
    local: {
      async get(keys) {
        const list = Array.isArray(keys) ? keys : typeof keys === 'string' ? [keys] : Object.keys(keys || {});
        return Object.fromEntries(list.filter(k => entries.has(k)).map(k => [k, entries.get(k)]));
      },
      async set(object) { for (const [k,v] of Object.entries(object)) entries.set(k, v); },
      async remove(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) entries.delete(key); },
    },
  },
  tabs: {
    async query() { return [{id:9}]; },
    async sendMessage(id,payload) { messages.push([id,payload]); },
  },
};
const { MODEL_BYTES, getModelLibrary, addModel, renameModel, selectModel, deleteModel,
  selectedWeights, encodeWeights } = await import('./model-store.js');
function makeWeights(v) {
  const floats = new Float32Array(MODEL_BYTES/4);
  floats.fill(v);
  return floats.buffer;
}
const first = await addModel({name:'First custom',fileName:'first.bin',weights:makeWeights(.5)});
const second = await addModel({name:'Second custom',fileName:'second.bin',weights:makeWeights(.8)});
let library = await getModelLibrary();
assert.equal(library.models.length,4);
assert.equal(library.selectedModel,second.id);
assert.equal(entries.get('model-weights:'+first.id).length > 2300000,true);
assert.equal(entries.get('model-weights:'+second.id).length > 2300000,true);
await renameModel(first.id,'My favorite bot');
await selectModel(first.id);
let current = await selectedWeights();
assert.equal(current.model.name,'My favorite bot');
assert.equal(new Float32Array(current.weights)[0],.5);
await deleteModel(second.id);
library = await getModelLibrary();
assert.equal(library.models.length,3);
assert.equal(entries.has('model-weights:'+second.id),false);
await deleteModel(first.id);
assert.equal((await getModelLibrary()).selectedModel,'g9');
assert.ok(messages.length>=4);
console.log('PASS: import multiple, persist, rename, select, read exact weights, delete, fallback.');

// An existing single imported model is migrated without dropping its weights.
entries.clear();
const buffer = makeWeights(.75);
await chrome.storage.local.set({ selectedModel:'custom',customModel:{name:'Old model',sha256:'f'.repeat(64),base64:encodeWeights(buffer)} });
library = await getModelLibrary();
assert.equal(library.models.length,3);
assert.equal(library.selectedModel,'custom-'+'f'.repeat(64));
assert.equal(new Float32Array((await selectedWeights()).weights)[0],.75);
assert.equal(entries.has('customModel'),false);
console.log('PASS: migration from v4.2.2 single-custom-model storage.');
