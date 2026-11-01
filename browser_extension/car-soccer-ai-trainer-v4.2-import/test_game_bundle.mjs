// Supply the downloaded main-DaNpiwbA.js; third-party bundles are not committed.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {transformMainSource} from './patcher.js';
const original=fs.readFileSync(process.argv[2],'utf8');
const patched=transformMainSource(original);
const runtime=patched.slice(patched.indexOf('const __GCT4_KICKOFF='),patched.lastIndexOf('D.onError='));
assert.ok(runtime.length>10000);
const neutral={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:false,boost:false,handbrake:false};
const state=new Float32Array(500);state[2]=1;state[6]=92;state[23]=-4608;state[24]=17;state[41]=1;state[40]=33;
const posts=[],applied=[];
const context=vm.createContext({
 window:{postMessage:m=>posts.push(m),addEventListener:()=>{}},location:{origin:'https://car-soccer.com'},
 ak:class{reset(){}},Df:class{},ee:neutral,d:false,m:null,h:0,A:{playerTeam:0,botTeam:1},
 R:{TICK:0,NUM_CARS:2,NUM_PADS:3,BALL:4,CARS:22},De:51,Pa:8,Vn:430,
 M:{POS:0,FWD:3,UP:9,VEL:12,ANG_VEL:15,BOOST:18,ON_GROUND:19,DEMOED:21,HAS_FLIP_OR_JUMP:22},
 c:{state,setControls:(slot,controls)=>applied.push({slot,...controls})},xt:[],
 q:{state:{mode:'match'}},St:{boostOption:'normal'},Z:null,performance,clearTimeout,setTimeout
});
vm.runInContext(runtime,context);
const brain=context.window.__GCTrainerRuntime;
assert.equal(brain.snapshot().boost,33);
brain.active=true;brain.nextoReady=true;brain.stepOffline();
assert.equal(brain.error,'');assert.equal(applied.at(-1).boost,true);assert.equal(applied.at(-1).slot,0);
state[0]=44;brain.stepOffline();assert.equal(applied.at(-1).steer,-1);
state[4]=100;state[0]=45;brain.stepOffline();
const packet=posts.find(p=>p.type==='nexto-infer').packet;
assert.equal(packet.players[0].boost,.33);assert.equal(packet.previousAction[1],-1);
brain.disable();assert.equal(applied.at(-1).throttle,0);
let reads=0;const originalRead=()=>{reads++;return {throttle:.2}};
const session={readControls:originalRead,carSlot:0,carTeams:[0],spectator:false};
context.d=true;context.m=session;brain.boundOnline=session;brain.mode='online';brain.active=true;
brain.computeOnlineControls=()=>({throttle:1});brain.installOnlineProvider(session);
assert.equal(session.readControls().throttle,1);assert.equal(reads,1);
brain.restoreOnlineProvider();assert.equal(session.readControls,originalRead);
const hot='this.tick++,this.spectator||(this.controls[this.carSlot]={...this.readControls()}),this.peer.host?';
assert.equal(patched.split(hot).length,original.split(hot).length);
assert.equal(patched.split('__GCT4.stepOffline(),c.step(1)').length-1,6);
console.log('PASS: uploaded bundle hooks, runtime startup, state observation, scripted kickoff, neural handoff, neutral restore, online provider restore.');
