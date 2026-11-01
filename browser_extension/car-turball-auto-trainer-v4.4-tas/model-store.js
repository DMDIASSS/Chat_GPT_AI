// Model metadata stays small; each model's binary is stored in its own key.
// This avoids loading every 1.8 MB model just to render a dropdown.
export const MODEL_BYTES = 1776128;
export const BUILTINS = [
  { id: 'g9', name: 'G9 u0073', builtin: true },
  { id: 'nexto', name: 'Original Nexto', builtin: true },
];
const WEIGHT_KEY = id => `model-weights:${id}`;
const cleanName = (name, fallback = 'Imported model') => {
  const value = String(name || '').trim().replace(/[\r\n\t]/g, ' ').slice(0, 80);
  return value || fallback;
};

// v4.2.2 kept exactly one model in "customModel". Migrate it on first use.
export async function getModelLibrary() {
  const data = await chrome.storage.local.get(['modelCatalog', 'selectedModel', 'customModel']);
  let catalog = data.modelCatalog && typeof data.modelCatalog === 'object' ? data.modelCatalog : {};
  let selectedModel = data.selectedModel || 'g9';
  if (data.customModel?.base64) {
    const legacy = data.customModel;
    const hex = /^[a-f0-9]{64}$/i.test(legacy.sha256 || '') ? legacy.sha256.toLowerCase() : 'legacy';
    const id = 'custom-' + hex;
    catalog = { ...catalog, [id]: {
      id, name: cleanName(legacy.name), fileName: legacy.name || 'legacy.bin',
      sha256: legacy.sha256 || '', importedAt: new Date().toISOString(),
    }};
    if (selectedModel === 'custom') selectedModel = id;
    await chrome.storage.local.set({ modelCatalog: catalog, [WEIGHT_KEY(id)]: legacy.base64, selectedModel });
    await chrome.storage.local.remove('customModel');
  }
  const models = [...BUILTINS, ...Object.values(catalog)
    .filter(m => m && typeof m.id === 'string' && m.id.startsWith('custom-'))
    .sort((a, b) => String(a.name).localeCompare(String(b.name)))];
  if (!models.some(m => m.id === selectedModel)) selectedModel = 'g9';
  return { models, selectedModel, catalog };
}

export async function currentModel() {
  const library = await getModelLibrary();
  const model = library.models.find(m => m.id === library.selectedModel);
  return { ...model };
}

export function encodeWeights(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 32768)
    binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
  return btoa(binary);
}
export function validateWeights(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength !== MODEL_BYTES)
    throw new Error(`Incompatible browser weights: expected ${MODEL_BYTES.toLocaleString('en-US')} bytes.`);
  if (!new Float32Array(buffer).every(Number.isFinite)) throw new Error('Model contains nonfinite weights.');
}
export async function notifyModelChange() {
  const tabs = await chrome.tabs.query({ url: ['https://car-soccer.com/*', 'https://turball.io/*'] });
  await Promise.allSettled(tabs.filter(t => t.id).map(tab => chrome.tabs.sendMessage(tab.id, { type: 'gct-model-changed' })));
}
export async function selectModel(id) {
  const library = await getModelLibrary();
  if (!library.models.some(m => m.id === id)) throw new Error('That model is no longer installed.');
  if (library.selectedModel === id) return;
  await chrome.storage.local.set({ selectedModel: id });
  await notifyModelChange();
}
export async function addModel({ name, fileName, weights }) {
  validateWeights(weights);
  const hash = await crypto.subtle.digest('SHA-256', weights);
  const sha256 = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
  const id = 'custom-' + sha256;
  const library = await getModelLibrary();
  const catalog = { ...library.catalog };
  const existing = catalog[id];
  const model = {
    id,
    name: cleanName(name, existing?.name || fileName || 'Imported model'),
    fileName: fileName || 'model.bin', sha256,
    importedAt: existing?.importedAt || new Date().toISOString(),
  };
  catalog[id] = model;
  const updates = { modelCatalog: catalog, selectedModel: id };
  if (!existing) updates[WEIGHT_KEY(id)] = encodeWeights(weights);
  await chrome.storage.local.set(updates);
  await notifyModelChange();
  return model;
}
export async function renameModel(id, name) {
  const library = await getModelLibrary();
  if (!library.catalog[id]) throw new Error('Only imported models can be renamed.');
  const renamed = cleanName(name, '');
  if (!renamed) throw new Error('Please enter a display name.');
  await chrome.storage.local.set({ modelCatalog: {
    ...library.catalog, [id]: { ...library.catalog[id], name: renamed },
  }});
  if (library.selectedModel === id) await notifyModelChange();
}
export async function deleteModel(id) {
  const library = await getModelLibrary();
  if (!library.catalog[id]) throw new Error('Only imported models can be deleted.');
  const catalog = { ...library.catalog };
  delete catalog[id];
  const selected = library.selectedModel === id ? 'g9' : library.selectedModel;
  await chrome.storage.local.set({ modelCatalog: catalog, selectedModel: selected });
  await chrome.storage.local.remove(WEIGHT_KEY(id));
  if (selected !== library.selectedModel) await notifyModelChange();
}

export async function selectedWeights() {
  const library = await getModelLibrary();
  const model = library.models.find(m => m.id === library.selectedModel);
  if (model.builtin) return { model, weights: null };
  const entry = await chrome.storage.local.get(WEIGHT_KEY(model.id));
  const binary = entry[WEIGHT_KEY(model.id)];
  if (typeof binary !== 'string') throw new Error(`Missing weights for ${model.name}. Re-import the model.`);
  return { model, weights: Uint8Array.from(atob(binary), c => c.charCodeAt(0)).buffer };
}
