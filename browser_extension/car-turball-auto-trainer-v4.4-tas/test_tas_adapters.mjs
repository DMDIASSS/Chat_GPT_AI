import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {transformMainSource as carPatch} from './patcher.js';
import {transformMainSource as turballPatch} from './turball-patcher.js';
import {recording,fakeEnvironment} from './test_tas.mjs';

const carSource=process.argv[2]?fs.readFileSync(process.argv[2],'utf8'):[
  'this.tick++,this.spectator||(this.controls[this.carSlot]={...this.readControls()}),this.peer.host?',
  ...Array(3).fill('c.setControls(wr,ce),c.step(1)'),
  'if(q.state.mode==="match")return ic();c.step(1),j.record(c.state,c.ballTouchMask,l);',
  'if(q.state.mode==="match"){if(!ic(!0))return!1}else c.step(1),c.pollGoal();',
  'const ke=Z?()=>{c.setUnlimitedBoost(!0),c.step(1);','xt=c.getPads();D.onError='
].join('\n');
const turballSource=[
  'async function gc(n,t={})','const r=new fo;await n.track("physics","Starting physics",()=>r.init())',
  'const b=t.botController??new wi(ro.load().botId)',
  'const ut={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:false,boost:false,handbrake:false}',
  '_=r.getPads();const ti=','return u.advance(jt)','r.step(1);const l=r.pollGoal()','export{gc as startGame}'
].join('\n');
const neutral={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:false,boost:false,handbrake:false};
class Native {reset(){};isReady=false;}
for(const site of ['car-soccer','turball']) {
  const env=fakeEnvironment(),posts=[],listeners={};
  env.sim.getPads=()=>[];
  const window={postMessage:m=>posts.push(m),addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
  const shared={window,document:{hidden:false,addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)},
    location:{origin:`https://${site==='turball'?'turball.io':'car-soccer.com'}`},performance,setTimeout,clearTimeout,
    Float32Array,ArrayBuffer,DataView,console};
  const latest=carSource.includes('R=new Qk(kd.load().botId)');
  const globals=site==='turball'?{r:env.sim,k:env.fields,N:51,h:0,u:null,w:[{team:0},{team:1}],x:null,o:{playerTeam:0},
    d:{state:{mode:'freeplay'}},Le:{boostOption:'normal'},g:{customMapActive:false},wi:Native,ut:neutral}:
    {d:false,m:null,c:env.sim,h:0,A:{playerTeam:0,botTeam:1},M:{BOOST:18},
      ...(latest?{Qk:Native,Q:neutral,P:env.fields,He:51,Ya:8,ro:430,sl:[],$:{state:{mode:'freeplay'}},wt:{boostOption:'normal'},D:null,k0:class{}}:
        {sk:Native,te:neutral,R:env.fields,De:51,Ra:8,zn:430,xt:[],q:{state:{mode:'freeplay'}},St:{boostOption:'normal'},Z:null,Gf:class{}})};
  const context=vm.createContext({...shared,...globals});
  const patched=(site==='turball'?turballPatch:carPatch)(site==='turball'?turballSource:carSource);
  const code=patched.slice(patched.indexOf(site==='turball'?'const __GCT4_CHANNEL=':'const __GCT4_KICKOFF='),site==='turball'?patched.indexOf('\nconst ti='):patched.lastIndexOf(latest?'R.onError=':'D.onError='));
  vm.runInContext(code,context);const brain=window.__GCTrainerRuntime;
  const dispatch=async command=>{
    for(const fn of listeners.message||[])await fn({source:window,origin:shared.location.origin,
      data:{source:'__grandchamp_trainer_v4__',from:'ui',...command}});
  };
  await dispatch({command:'tas-load',buffer:recording(),name:'Test.data'});
  assert.equal(brain.selectedBot,'tas');assert.equal(brain.snapshot().tas.frames,4);
  await dispatch({command:'enable',options:{boost:33,unlimited:false}});
  assert.equal(brain.active,true,brain.error);assert.equal(brain.nextoReady,false,'TAS must not load model weights');
  if(site==='turball')env.sim.step(3);
  else for(let i=0;i<3;i++){brain.stepOffline();env.sim.step();}
  const own=env.sim.writes.filter(c=>c.slot===0).slice(-3);
  assert.deepEqual(own.map(c=>c.jump),[false,true,false],`${site} skipped a jump edge`);
  assert.equal(brain.snapshot().tas.frame,2);
  for(const fn of listeners.keydown||[])fn({code:'F8',repeat:false,preventDefault(){},stopImmediatePropagation(){}});
  assert.equal(brain.active,false);assert.equal(env.sim.writes.at(-1).throttle,0);
  await dispatch({command:'enable'});assert.equal(brain.snapshot().tas.frame,0);
  for(const fn of listeners.blur||[])fn();assert.equal(brain.active,false);
  await dispatch({command:'enable'});
  if(site==='turball')context.u={};else context.d=true;
  await dispatch({command:'snapshot'});assert.equal(brain.active,false,'Entering online mode did not disarm TAS');
  console.log('PASS:',site,'patched TAS upload/start, native tick path, no model dependency, jump edges, F8, blur and mode-change stop');
}
