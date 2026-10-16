import { currentModel, getModelLibrary, selectModel, renameModel, deleteModel } from './model-store.js';
import { importModelFile, installBuiltinNexto } from './model-import.js';
const $ = id => document.getElementById(id);
const statusEl = $('status');
const modelSelect = $('model');
const modelFile = $('model-file');
const modelStatus = $('model-status');
const displayName = $('display-name');
const renameBtn = $('rename');
const removeBtn = $('remove');
const uploadBtn = $('upload');
const installNextoBtn = $('install-nexto');
const nextoFile = $('nexto-file');
const nextoStatus = $('nexto-status');
let busy = false;
async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !String(tab.url || '').startsWith('https://car-soccer.com/'))
    throw new Error('Open https://car-soccer.com/ to enable the trainer. Model management still works here.');
  return tab;
}
async function send(type) {
  const tab = await activeTab();
  return chrome.runtime.sendMessage({ type, tabId: tab.id });
}
async function refreshStatus() {
  try {
    const res = await send('gct-status');
    if (!res.ok) throw new Error(res.error);
    const s = res.status;
    statusEl.textContent = `${s.enabled ? 'Enabled' : 'Disabled'} · ${s.state}${s.message ? '\n' + s.message : ''}`;
  } catch (e) { statusEl.textContent = e.message || String(e); }
}
for (const [id, type, message] of [['enable','gct-enable','Reloading Car Soccer…'],['disable','gct-disable','Reloading normal game…']]) {
  $(id).onclick = async () => {
    $(id).disabled = true;
    try {
      const res = await send(type);
      if (!res.ok) throw new Error(res.error);
      statusEl.textContent = message;
    } catch (e) { statusEl.textContent = e.message || String(e); }
    finally { $(id).disabled = false; }
  };
}
async function refreshModels() {
  const { models, selectedModel } = await getModelLibrary();
  modelSelect.replaceChildren(...models.map(model => {
    const option = document.createElement('option');
    option.value = model.id;
    option.textContent = model.name;
    return option;
  }));
  modelSelect.value = selectedModel;
  const model = models.find(m => m.id === selectedModel);
  displayName.value = model?.name || '';
  const custom = !model?.builtin;
  renameBtn.disabled = removeBtn.disabled = !custom;
  displayName.disabled = !custom;
  modelStatus.textContent = `Selected: ${model?.name || 'Unknown'}\n${models.filter(m => !m.builtin).length} imported model(s) saved.`;
  const restored = await chrome.storage.local.get('builtinNextoSource');
  nextoStatus.textContent = restored.builtinNextoSource ? `Original Nexto weights installed from: ${restored.builtinNextoSource}` : 'Not installed through the popup. Existing nexto-weights.bin is still supported.';
}
async function runAction(action) {
  if (busy) return;
  busy = true;
  modelSelect.disabled = uploadBtn.disabled = installNextoBtn.disabled = true;
  try { await action(); await refreshModels(); }
  catch(e) { modelStatus.textContent = `Error: ${e.message || e}`; }
  finally { busy = false; modelSelect.disabled = uploadBtn.disabled = installNextoBtn.disabled = false; modelFile.value = ''; nextoFile.value = ''; }
}
modelSelect.onchange = () => runAction(async () => { await selectModel(modelSelect.value); });
renameBtn.onclick = () => runAction(async () => {
  await renameModel(modelSelect.value, displayName.value);
});
removeBtn.onclick = () => {
  const name = modelSelect.selectedOptions[0]?.textContent || 'this model';
  if (confirm(`Delete ${name} from this extension? Your original file will not be deleted.`))
    runAction(async () => { await deleteModel(modelSelect.value); });
};
uploadBtn.onclick = () => modelFile.click();
installNextoBtn.onclick = () => nextoFile.click();
nextoFile.onchange = () => runAction(async () => {
  const file = nextoFile.files?.[0]; if (!file) return;
  modelStatus.textContent = `Installing Original Nexto from ${file.name}…`;
  await installBuiltinNexto(file);
  modelStatus.textContent = 'Original Nexto weights installed. Select Original Nexto in game and press Give Control.';
});
modelFile.onchange = () => runAction(async () => {
  const file = modelFile.files?.[0]; if (!file) return;
  modelStatus.textContent = `Importing ${file.name}…`;
  const initial = displayName.disabled ? '' : displayName.value;
  // When importing use the file name by default, rather than copying the name
  // of the currently selected custom model.
  const name = initial && initial !== (await currentModel()).name ? initial : file.name.replace(/\.(pt|bin|zip)$/i,'');
  const model = await importModelFile(file, name);
  modelStatus.textContent = `Imported ${model.name}`;
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && !busy && (changes.modelCatalog || changes.selectedModel))
    refreshModels().catch(e => { modelStatus.textContent = e.message; });
});
refreshStatus();
setInterval(refreshStatus, 1200);
refreshModels().catch(e => { modelStatus.textContent = e.message; });
