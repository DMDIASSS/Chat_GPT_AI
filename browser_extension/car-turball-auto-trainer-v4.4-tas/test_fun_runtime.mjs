import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {transformMainSource} from './patcher.js';
import {fakeEnvironment} from './test_tas.mjs';
const source=fs.readFileSync(process.argv[2],'utf8'),patched=transformMainSource(source);
const latest=source.includes('R=new Qk(kd.load().botId)');
const env=fakeEnvironment(),posts=[],listeners={};env.sim.controlsView=new Float32Array(16);env.sim.getPads=()=>[];
const neutral={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:false,boost:false,handbrake:false};
class Native {reset(){};isReady=false;}
const window={postMessage:m=>posts.push(m),addEventListener:(key,fn)=>(listeners[key]??=[]).push(fn)};
const document={hidden:false,addEventListener:(key,fn)=>(listeners[key]??=[]).push(fn)};
const context=vm.createContext({window,document,location:{origin:'https://car-soccer.com'},performance,setTimeout,clearTimeout,Float32Array,
  d:false,m:null,c:env.sim,h:0,A:{playerTeam:0,botTeam:1},M:{BOOST:18},
  ...(latest?{Qk:Native,Q:neutral,P:env.fields,He:51,Ya:8,ro:430,sl:[],$:{state:{mode:'freeplay'}},wt:{boostOption:'normal'},D:null,k0:class{}}:
    {sk:Native,te:neutral,R:env.fields,De:51,Ra:8,zn:430,xt:[],q:{state:{mode:'freeplay'}},St:{boostOption:'normal'},Z:null,Gf:class{}})});
vm.runInContext(patched.slice(patched.indexOf('const __GCT4_KICKOFF='),patched.lastIndexOf(latest?'R.onError=':'D.onError=')),context);
const brain=window.__GCTrainerRuntime;
const command=async value=>{for(const fn of listeners.message)await fn({source:window,origin:context.location.origin,data:{source:'__grandchamp_trainer_v4__',from:'ui',...value}});};
function key(code,extra={}) {
  let consumed=false;
  const event={code,repeat:false,target:{closest:()=>null},preventDefault(){},stopImmediatePropagation(){consumed=true;},...extra};
  for(const fn of listeners.keydown||[]){fn(event);if(consumed)break;}
}
const original=env.sim.step;
key('KeyG');assert.equal(brain.snapshot().fun.glue,true);env.sim.step();assert.equal(env.sim.captureNetwork()[3],90);
key('KeyG',{repeat:true});assert.equal(brain.snapshot().fun.glue,true);
key('KeyG',{target:{closest:()=>({tagName:'INPUT'})}});assert.equal(brain.snapshot().fun.glue,true,'Typing in chat toggled glue');
key('KeyG',{ctrlKey:true});assert.equal(brain.snapshot().fun.glue,true);
key('KeyL');assert.equal(brain.snapshot().fun.glue,false);assert.ok(env.sim.captureNetwork()[16]>0);
key('KeyB');assert.equal(brain.snapshot().fun.boost,true);key('F8');assert.equal(brain.snapshot().fun.enabled,false);assert.equal(env.sim.step,original);
await command({command:'fun-toggle',effect:'jumps'});assert.equal(brain.snapshot().fun.jumps,true);
for(const fn of listeners.blur)fn();assert.equal(brain.snapshot().fun.enabled,false);
await command({command:'fun-toggle',effect:'boost'});document.hidden=true;
for(const fn of listeners.visibilitychange)fn();assert.equal(brain.snapshot().fun.enabled,false);document.hidden=false;
const session={sim:env.sim,carSlot:0,carTeams:[0,1],peer:{host:false},match:{state:{phase:'playing'}},spectator:false,controls:[neutral,neutral]};
context.d=true;context.m=session;
await command({command:'fun-toggle',effect:'boost'});assert.equal(brain.snapshot().fun.enabled,false);assert.match(brain.error,/Host the room/);
session.peer.host=true;await command({command:'fun-toggle',effect:'boost'});assert.equal(brain.snapshot().fun.scope,'room host');
env.sim.step();assert.equal(env.sim.captureNetwork()[56],100);session.peer.host=false;
await command({command:'snapshot'});assert.equal(brain.snapshot().fun.enabled,false);assert.equal(env.sim.step,original);
context.d=false;context.m=null;
// A worker finishing after F8 or a fun activation cannot take control back.
let resolve;brain.ensureNexto=()=>new Promise(r=>resolve=r);
const loading=brain.enable();assert.equal(brain.loading,true);
await command({command:'fun-toggle',effect:'boost'});assert.equal(brain.snapshot().fun.boost,true);
resolve();await loading;assert.equal(brain.active,false,'Late AI startup stole control from fun mode');assert.equal(brain.snapshot().fun.boost,true);
await command({command:'fun-stop'});const cancelled=brain.enable();key('F8');resolve();await cancelled;
assert.equal(brain.active,false,'F8 did not cancel pending AI activation');assert.equal(env.sim.step,original);
assert.equal(patched.split('this.tick++,this.spectator||(this.controls[this.carSlot]={...this.readControls()}),this.peer.host?').length,
  source.split('this.tick++,this.spectator||(this.controls[this.carSlot]={...this.readControls()}),this.peer.host?').length);
console.log('PASS: real bundle runtime hotkeys, editable-field guards, UI commands, host authority, F8/focus stop and cancelled async AI activation');
