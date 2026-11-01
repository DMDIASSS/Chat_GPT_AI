import { addModel, validateWeights, encodeWeights, notifyModelChange } from './model-store.js';
import { convertPtBuffer } from './browser-torch-converter.js';

const MAX_IMPORT_BYTES = 256 * 1024 * 1024;
let layoutPromise;
async function getLayout() {
  if (!layoutPromise) {
    layoutPromise = fetch(chrome.runtime.getURL('model-layout.json'))
      .then(response => {
        if (!response.ok) throw new Error('The extension is missing model-layout.json. Reinstall the complete extension ZIP.');
        return response.json();
      }).catch(error => { layoutPromise = null; throw error; });
  }
  return layoutPromise;
}

// All files are handled inside the extension popup, completely offline.
// Compatible native Nexto PyTorch ZIP/TorchScript checkpoints are unpacked
// by browser JS; no Python, localhost request, account, network or BAT file.
export async function convertCompatibleModelFile(file) {
  if (!file || !/\.(?:bin|pt|zip)$/i.test(file.name))
    throw new Error('Choose a native Nexto .bin, .pt or .zip checkpoint.');
  if (file.size > MAX_IMPORT_BYTES)
    throw new Error('Choose a model file under 256 MiB.');
  const input = await file.arrayBuffer();
  let weights;
  if (/\.bin$/i.test(file.name)) {
    weights = input;
  } else {
    try {
      weights = await convertPtBuffer(input, await getLayout());
    } catch (error) {
      throw new Error(`Cannot import ${file.name}: ${error.message || error}`);
    }
  }
  validateWeights(weights);
  return weights;
}

export async function importModelFile(file, displayName) {
  const weights = await convertCompatibleModelFile(file);
  return addModel({ name: displayName, fileName: file.name, weights });
}

// Same direct upload path for the built-in Nexto entry. The checkpoint is
// saved in chrome.storage.local, not fetched from a missing extension asset.
export async function installBuiltinNexto(file) {
  const weights = await convertCompatibleModelFile(file);
  await chrome.storage.local.set({
    builtinNextoWeights: encodeWeights(weights),
    builtinNextoSource: file.name,
    selectedModel: 'nexto',
  });
  await notifyModelChange();
  return { name: 'Original Nexto', fileName: file.name };
}
