// Optional native integration check against a user-supplied Car Soccer bundle.
// No game code, WASM, collision files or recordings are distributed by this test.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createTasPlayer} from './tas-player.mjs';
import {recording} from './test_tas.mjs';
const source=fs.readFileSync(process.argv[2],'utf8');
const begin=source.indexOf('async function Fg('),end=source.indexOf('const cn=[',begin);
assert.ok(begin>=0&&end>begin,'Unsupported supplied physics factory');
const context=vm.createContext({console,window:{},document:{currentScript:null},location:{href:'https://car-soccer.com/'},
  o:(object,name,value)=>Object.defineProperty(object,name,{value,writable:true,enumerable:true,configurable:true}),
  WebAssembly,TextDecoder,TextEncoder,URL,performance,setTimeout,clearTimeout});
vm.runInContext(source.slice(begin,end).replaceAll('import.meta.url','"https://car-soccer.com/"')+';globalThis.factory=Fg;',context);
const mod=await context.factory({noFSInit:true});
// Synthetic flat floor for pose round trips and tick checks, not a claim that
// this test recreates the full arena or validates recorded trick outcomes.
const data=new Uint8Array(80),view=new DataView(data.buffer);
view.setInt32(0,2,true);view.setInt32(4,4,true);
[0,1,2,0,2,3].forEach((n,i)=>view.setInt32(8+i*4,n,true));
[-10000,-10000,0,10000,-10000,0,10000,10000,0,-10000,10000,0].forEach((n,i)=>view.setFloat32(32+i*4,n,true));
const ptr=mod._malloc(80),lens=mod._malloc(4);mod.HEAPU8.set(data,ptr);mod.HEAP32[lens/4]=80;
assert.equal(mod._physics_init(ptr,lens,1),1);assert.equal(mod._physics_createArena(),1);assert.equal(mod._physics_addCar(0,0),0);
mod._physics_resetKickoff(0);
const sim={
  get state(){return new Float32Array(mod.HEAPF32.buffer,mod._physics_getStatePtr(),mod._physics_getStateSize());},
  resetKickoff(){mod._physics_resetKickoff(-1);},
  captureNetwork(){return new Float32Array(mod.HEAPF32.buffer,mod._physics_getNetworkPtr(),mod._physics_captureNetwork()).slice();},
  restoreNetwork(n){mod.HEAPF32.set(n,mod._physics_getNetworkPtr()/4);assert.equal(mod._physics_restoreNetwork(n.length),1);},
  setUnlimitedBoost(b){mod._physics_setUnlimitedBoost(b?1:0);},resetView(){mod._v2();},pollGoal(){mod._physics_clearGoalFlag();},
  setControls(slot,c){mod.HEAPF32.set([c.throttle,c.steer,c.pitch,c.yaw,c.roll,+c.jump,+c.boost,+c.handbrake],mod._physics_getControlsPtr()/4+slot*8);},
};
const fields={TICK:0,GOAL:1,NUM_CARS:2,NUM_PADS:3,BALL:4,CARS:22};
const player=createTasPlayer({environment:()=>({sim,fields,stride:51,slot:0,mode:'freeplay',online:false,customMap:false})});
const files=[{name:'synthetic',buffer:recording()}];
for(const path of process.argv.slice(3)){
  const data=fs.readFileSync(path);files.push({name:path.split('/').at(-1),buffer:data.buffer.slice(data.byteOffset,data.byteOffset+data.byteLength)});
}
for(const file of files){
  player.load(file.buffer,file.name);player.play({boost:100,unlimited:false});
  const initial=player.snapshot();assert.equal(sim.state[40],100);
  for(let j=0;j<3;j++)assert.ok(Math.abs(sim.state[22+j]-initial.car[j])<.03);
  for(let i=0;i<initial.frames;i++){
    const tick=sim.state[0],control=player.step(tick);assert.ok(control);
    sim.setControls(0,control);mod._physics_step(1);assert.equal(sim.state[0],tick+1);
  }
  assert.equal(player.step(sim.state[0]),null);assert.equal(player.snapshot().running,false);
  assert.ok(Array.from(sim.state).every(Number.isFinite),'Native simulation became non-finite');
  console.log('PASS: native WASM pose/velocity/rotation/boost restoration and consecutive 120 Hz ticks:',file.name);
}
