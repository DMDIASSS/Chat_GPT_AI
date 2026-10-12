export const MODEL_BYTES=1776128;
export const names={nexto:'Original Nexto',g9:'G9 u0073'};
export async function currentModel(){
  const data=await chrome.storage.local.get(['selectedModel','customModel']);
  const id=data.selectedModel||'g9';
  if(id==='custom'){
    if(!data.customModel)throw new Error('Import a custom model first.');
    return {id,...data.customModel};
  }
  if(!names[id])throw new Error('Unknown selected model.');
  return {id,name:names[id]};
}
export function encodeWeights(buffer){
  const bytes=new Uint8Array(buffer);let binary='';
  for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
  return btoa(binary);
}
export function validateWeights(buffer){
  if(buffer.byteLength!==MODEL_BYTES)throw new Error('Incompatible browser weights: expected 1,776,128 bytes.');
  if(!new Float32Array(buffer).every(Number.isFinite))throw new Error('Nonfinite model weights.');
}
export async function notifyModelChange(){
  const tabs=await chrome.tabs.query({url:'https://car-soccer.com/*'});
  await Promise.allSettled(tabs.map(tab=>chrome.tabs.sendMessage(tab.id,{type:'gct-model-changed'})));
}
