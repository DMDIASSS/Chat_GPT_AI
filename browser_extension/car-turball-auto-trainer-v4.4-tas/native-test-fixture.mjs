// Test-only loader for the caller's private Car Soccer bundle. No game engine
// or real collision asset is checked into or redistributed with the extension.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
export async function nativeTestArena(path,cars=2) {
  const source=fs.readFileSync(path,'utf8'),begin=source.indexOf('async function Fg('),end=source.indexOf('const cn=[',begin);
  assert.ok(begin>=0&&end>begin,'Unsupported supplied physics factory');
  const context=vm.createContext({console,window:{},document:{currentScript:null},location:{href:'https://car-soccer.com/'},
    o:(object,name,value)=>Object.defineProperty(object,name,{value,writable:true,enumerable:true,configurable:true}),
    WebAssembly,TextDecoder,TextEncoder,URL,performance,setTimeout,clearTimeout});
  vm.runInContext(source.slice(begin,end).replaceAll('import.meta.url','"https://car-soccer.com/"')+';globalThis.factory=Fg;',context);
  const mod=await context.factory({noFSInit:true});
  const data=new Uint8Array(80),view=new DataView(data.buffer);
  view.setInt32(0,2,true);view.setInt32(4,4,true);
  [0,1,2,0,2,3].forEach((n,i)=>view.setInt32(8+i*4,n,true));
  [-10000,-10000,0,10000,-10000,0,10000,10000,0,-10000,10000,0].forEach((n,i)=>view.setFloat32(32+i*4,n,true));
  const ptr=mod._malloc(80),lens=mod._malloc(4);mod.HEAPU8.set(data,ptr);mod.HEAP32[lens/4]=80;
  assert.equal(mod._physics_init(ptr,lens,1),1);assert.equal(mod._physics_createArena(),1);
  for(let i=0;i<cars;i++)assert.equal(mod._physics_addCar(i%2,0),i);
  mod._physics_resetKickoff(0);
  const sim={module:mod,
    get state(){return new Float32Array(mod.HEAPF32.buffer,mod._physics_getStatePtr(),mod._physics_getStateSize());},
    get controlsView(){return new Float32Array(mod.HEAPF32.buffer,mod._physics_getControlsPtr(),64);},
    get ballRadius(){return mod._physics_getBallRadius();},
    step(count=1){mod._physics_step(count);},resetKickoff(){mod._physics_resetKickoff(-1);},
    captureNetwork(){return new Float32Array(mod.HEAPF32.buffer,mod._physics_getNetworkPtr(),mod._physics_captureNetwork()).slice();},
    restoreNetwork(n){mod.HEAPF32.set(n,mod._physics_getNetworkPtr()/4);assert.equal(mod._physics_restoreNetwork(n.length),1);},
    setUnlimitedBoost(b){mod._physics_setUnlimitedBoost(b?1:0);},resetView(){mod._v2();},pollGoal(){const n=sim.state[1];mod._physics_clearGoalFlag();return n;},
    setControls(slot,c){sim.controlsView.set([c.throttle||0,c.steer||0,c.pitch||0,c.yaw||0,c.roll||0,+!!c.jump,+!!c.boost,+!!c.handbrake],slot*8);},
  };
  return {sim,fields:{TICK:0,GOAL:1,NUM_CARS:2,NUM_PADS:3,BALL:4,CARS:22},stride:51,slot:0,team:0,
    mode:'freeplay',phase:'idle',online:false,host:false,customMap:false,session:null};
}
