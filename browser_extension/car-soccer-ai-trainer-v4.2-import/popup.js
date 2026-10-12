const statusEl = document.getElementById('status');
const enableBtn = document.getElementById('enable');
const disableBtn = document.getElementById('disable');

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error('No active tab.');
  if (!String(tab.url || '').startsWith('https://car-soccer.com/')) throw new Error('Open https://car-soccer.com/ first.');
  return tab;
}

async function send(type) {
  const tab = await activeTab();
  return chrome.runtime.sendMessage({ type, tabId: tab.id });
}

async function refresh() {
  try {
    const res = await send('gct-status');
    if (!res.ok) throw new Error(res.error);
    const s = res.status;
    statusEl.textContent = `${s.enabled ? 'Enabled' : 'Disabled'}\n${s.state}${s.message ? `\n${s.message}` : ''}`;
  } catch (e) {
    statusEl.textContent = String(e.message || e);
  }
}

enableBtn.onclick = async () => {
  enableBtn.disabled = true;
  try {
    const res = await send('gct-enable');
    if (!res.ok) throw new Error(res.error);
    statusEl.textContent = 'Enabled. Reloading Car Soccer…';
  } catch (e) {
    statusEl.textContent = String(e.message || e);
  } finally {
    enableBtn.disabled = false;
  }
};

disableBtn.onclick = async () => {
  disableBtn.disabled = true;
  try {
    const res = await send('gct-disable');
    if (!res.ok) throw new Error(res.error);
    statusEl.textContent = 'Disabled. Reloading normal game…';
  } catch (e) {
    statusEl.textContent = String(e.message || e);
  } finally {
    disableBtn.disabled = false;
  }
};

refresh();
setInterval(refresh, 1000);

const modelSelect=document.getElementById('model');
const modelFile=document.getElementById('model-file');
const modelStatus=document.getElementById('model-status');
const {currentModel,encodeWeights,validateWeights,notifyModelChange}=await import('./model-store.js');
async function refreshModel(){
  const stored=await chrome.storage.local.get('customModel');
  let custom=modelSelect.querySelector('option[value="custom"]');
  if(stored.customModel){
    if(!custom){custom=document.createElement('option');custom.value='custom';modelSelect.append(custom);}
    custom.textContent=stored.customModel.name;
  }
  const model=await currentModel();modelSelect.value=model.id;
  modelStatus.textContent=`Selected: ${model.name}\nScripted kickoffs: ON${model.sha256?'\nSHA256: '+model.sha256:''}`;
}
modelSelect.onchange=async()=>{
  modelSelect.disabled=true;
  try {await chrome.storage.local.set({selectedModel:modelSelect.value});await notifyModelChange();await refreshModel();}
  catch(e){modelStatus.textContent=e.message;}
  finally{modelSelect.disabled=false;}
};
modelFile.onchange=async()=>{
  const file=modelFile.files?.[0];if(!file)return;
  modelSelect.disabled=modelFile.disabled=true;
  try {
    modelStatus.textContent='Importing on this PC…';
    if(file.size>256*1024*1024)throw new Error('Choose a checkpoint/export below 256 MiB.');
    let weights;
    if(file.name.toLowerCase().endsWith('.bin'))weights=await file.arrayBuffer();
    else {
      let response;
      try {response=await fetch('http://127.0.0.1:8765/convert',{
        method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file,
        signal:AbortSignal.timeout(120000),
      });}catch(e){throw new Error('Local importer unavailable. Run START_MODEL_IMPORT.bat, keep its window open, then select the file again. '+e.message);}
      if(!response.ok){const error=await response.json();throw new Error(error.error||'Conversion failed.');}
      weights=await response.arrayBuffer();
    }
    validateWeights(weights);
    const digest=await crypto.subtle.digest('SHA-256',weights);
    const sha256=Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
    await chrome.storage.local.set({customModel:{name:file.name,sha256,base64:encodeWeights(weights)},selectedModel:'custom'});
    await notifyModelChange();await refreshModel();
  }catch(e){modelStatus.textContent='Import failed: '+e.message+'\nPrevious model preserved.';}
  finally{modelSelect.disabled=modelFile.disabled=false;modelFile.value='';}
};
refreshModel().catch(e=>{modelStatus.textContent=e.message;});
