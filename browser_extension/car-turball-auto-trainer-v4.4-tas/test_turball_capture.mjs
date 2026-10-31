import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import {assetPath,exportsStartGame,gameplayDependency} from './turball-build.mjs';
import {transformMainSource as patchTurball} from './turball-patcher.js';
const lobby='const{startGame:s}=await a.track("code","Loading game code",()=>import("./chunk-KALAXRXF.js"));';
assert.equal(gameplayDependency(lobby,'https://turball.io/assets/app/chunk-DLWGG6LS.js'),'/assets/app/chunk-KALAXRXF.js');
assert.equal(gameplayDependency('import("./chunk-OTHER.js")','https://turball.io/assets/app/chunk-LOBBY.js'),null);
assert(exportsStartGame('export { xy as startGame };'));
assert(exportsStartGame('export { startGame };'));
assert(exportsStartGame('export async function startGame(a) {}'));
assert(!exportsStartGame(lobby));
assert.equal(assetPath('https://turball.io/assets/app/chunk-A.js?ref=not-exported'),'/assets/app/chunk-A.js');
assert.throws(()=>assetPath('https://unrelated.test/assets/app/chunk-A.js'));
if(process.argv[2]){
 const source=fs.readFileSync(process.argv[2],'utf8');
 assert.equal(gameplayDependency(source,'https://turball.io/assets/app/chunk-DLWGG6LS.js'),'/assets/app/chunk-KALAXRXF.js');
 assert(!exportsStartGame(source));
 console.log('PASS actual uploaded lobby identifies the missing KALAXRXF gameplay module');
}
const entries=new Map(),calls=[],events={};let body='';
const storage={async get(keys){return Object.fromEntries((Array.isArray(keys)?keys:[keys]).filter(k=>entries.has(k)).map(k=>[k,entries.get(k)]));},
 async set(rows){for(const [k,v] of Object.entries(rows))entries.set(k,v);},async remove(keys){for(const k of Array.isArray(keys)?keys:[keys])entries.delete(k);}};
const chrome={storage:{session:storage},
 debugger:{onEvent:{addListener:fn=>events.event=fn},onDetach:{addListener:fn=>events.detach=fn},
  async attach(){},async detach(){},async sendCommand(_,method,params){calls.push({method,params});return method==='Fetch.getResponseBody'?{body,base64Encoded:false}:{};}},
 tabs:{async get(){return {id:7,url:'https://turball.io/'};},async reload(){},onRemoved:{addListener:fn=>events.remove=fn}},
 webNavigation:{onBeforeNavigate:{addListener:fn=>events.navigate=fn}},
 runtime:{getURL:name=>'chrome-extension://fixture/'+name,getManifest:()=>({version:'4.5.2'}),
  onInstalled:{addListener:fn=>events.install=fn},onMessage:{addListener:fn=>events.message=fn}}};
const code=fs.readFileSync(new URL('./background.js',import.meta.url),'utf8').replace(/^import .+;\n/gm,'');
function boot(){vm.runInNewContext(code,{chrome,URL,Uint8Array,TextEncoder,TextDecoder,crypto:webcrypto,atob,btoa,
 console:{error(){},warn(){}},assetPath,exportsStartGame,gameplayDependency,patchTurball,
 patchCarSoccer(){throw Error('Wrong site')},selectModel(){throw Error('Must not touch models')}});}
boot();
async function message(type,sender={url:chrome.runtime.getURL('popup.html')}){
 return new Promise(resolve=>events.message({type,tabId:7},sender,resolve));
}
async function response(source,name='chunk-KALAXRXF.js',status=200){
 body=source;await events.event({tabId:7},'Fetch.requestPaused',{requestId:name,responseStatusCode:status,
 request:{url:'https://turball.io/assets/app/'+name+'?private=do-not-export'}});
}
assert((await message('gct-enable')).ok);
await response(lobby,'chunk-DLWGG6LS.js');
let status=(await message('gct-status')).status;
assert.equal(status.state,'waiting-gameplay');assert(status.expectedGameplay.endsWith('KALAXRXF.js'));assert(!status.canSaveGameplay);
const unsupported='async function newGame(){};export{newGame as startGame};';
await response(unsupported);
status=(await message('gct-status')).status;
assert.equal(status.state,'unsupported');assert(status.canSaveGameplay);assert.equal(status.gameplay.bytes,new TextEncoder().encode(unsupported).length);
assert.equal(status.gameplay.sha256.length,64);assert(!JSON.stringify(status).includes('do-not-export'));
assert(!calls.some(c=>c.method==='Fetch.fulfillRequest'));
assert(calls.some(c=>c.method==='Fetch.continueResponse'));
assert.equal((await message('gct-gameplay-source')).source,unsupported);
const report=await message('gct-diagnostics');assert(report.ok);assert(!JSON.stringify(report).includes(unsupported));
assert(!(await message('gct-gameplay-source',{url:'https://turball.io/'})).ok);
boot();assert.equal((await message('gct-gameplay-source')).source,unsupported,'capture lost across worker restart');
assert.equal((await message('gct-status')).status.state,'unsupported');
await message('gct-enable');assert(!(await message('gct-gameplay-source')).ok,'new scan retained stale capture');
await response(unsupported,'chunk-KALAXRXF.js',404);assert(!(await message('gct-gameplay-source')).ok);
await response(unsupported);events.remove(7);await new Promise(r=>setTimeout(r,0));assert(!entries.has('gct-gameplay-7'));
console.log('PASS lobby detection, unsupported pass-through, original JS/hash export, popup-only access, redacted report, worker restart, new-scan/tab cleanup and HTTP errors');
