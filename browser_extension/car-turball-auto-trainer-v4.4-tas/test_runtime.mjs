import assert from 'node:assert/strict';
import vm from 'node:vm';
import {transformMainSource} from './patcher.js';
import {createScriptedKickoff} from './kickoff.mjs';
const online='this.tick++,this.spectator||(this.controls[this.carSlot]={...this.readControls()}),this.peer.host?';
const source=[online,'d||c.setControls(h,Gt),Oe&&Pc("consume",Gt.boost)',...Array(3).fill('c.setControls(wr,ce),c.step(1)'), 'if(q.state.mode==="match")return ic();c.step(1),j.record(c.state,c.ballTouchMask,l);', 'if(q.state.mode==="match"){if(!ic(!0))return!1}else c.step(1),c.pollGoal();','const ke=Z?()=>{c.setUnlimitedBoost(!0),c.step(1);','xt=c.getPads();D.onError='].join('\n');
const out=transformMainSource(source);assert.equal(out.split(online).length,2);
const code=out.slice(out.indexOf('const __GCT4_KICKOFF='),out.lastIndexOf('D.onError='));
const posts=[];const listeners=[];
const window={addEventListener:(kind,fn)=>{if(kind==='message')listeners.push(fn);},postMessage:m=>posts.push(m)};
const context=vm.createContext({window,document:{addEventListener(){}},location:{origin:'https://car-soccer.com'},sk:class{reset(){}},te:{},d:false,q:{state:{mode:"freeplay"}},h:0,A:{playerTeam:0},clearTimeout,setTimeout,console});vm.runInContext(code,context);
const brain=window.__GCTrainerRuntime;brain.nextoReady=true;
const packet={tick:100,ball:{pos:[0,0,92],vel:[0,0,0]},players:[{pos:[0,-4608,17],team:0,onGround:true}]};brain.buildNextoPacket=()=>packet;brain.buildKickoffPacket=()=>packet;
brain.requestNexto(null,0,0,[],[],false,100);assert.ok(brain.nextoScriptActive&&brain.lastControls.boost);
const gen=brain.nextoGeneration;
listeners[0]({source:window,origin:context.location.origin,data:{source:'__grandchamp_trainer_v4__',from:'nexto-bridge',type:'nexto-result',generation:gen-1,controls:{throttle:-1}}});
assert.equal(brain.lastControls.throttle,1);
packet.tick=144;brain.requestNexto(null,0,0,[],[],false,144);assert.equal(brain.lastControls.steer,-1);
packet.ball.pos[0]=30;packet.tick=145;brain.requestNexto(null,0,0,[],[],false,145);assert.ok(!brain.nextoScriptActive&&posts.some(p=>p.type==='nexto-infer'));
const k=createScriptedKickoff();packet.ball.pos=[0,0,750];assert.equal(k.step(packet),null);
packet.ball.pos=[0,0,92];packet.players.push({pos:[0,-2560,17],team:0,onGround:true});assert.equal(k.step(packet),null);
console.log('PASS: runtime kickoff control, stale result rejection, neural handoff, aerial rejection, teammate priority, preserved multiplayer hot path.');
// Regression: game builds can change their optional human-input expression.
// Offline AI must still override controls immediately before each physics step.
const changedInput = source.replace('d||c.setControls(h,Gt),Oe&&Pc("consume",Gt.boost)',
  'd||c.setControls(h,Gt),Oe?.consumeBoost?.(Gt.boost)');
const patchedWithoutInputHook = transformMainSource(changedInput);
assert.ok(patchedWithoutInputHook.includes('d||c.setControls(h,Gt),Oe?.consumeBoost?.(Gt.boost)'));
assert.equal(patchedWithoutInputHook.split('__GCT4.stepOffline(),c.step(1)').length - 1, 6);
console.log('PASS: optional human-input signature mismatch no longer disables the patch.');
