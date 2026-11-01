import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createTasPlayer} from './tas-player.mjs';

export function recording(frames=4) {
  const buffer=new ArrayBuffer(8+32*frames+128),v=new DataView(buffer),tail=8+32*frames;
  v.setUint32(0,1,true);v.setUint32(4,frames,true);
  for(let i=0;i<frames;i++) {
    v.setUint32(8+i*32,[0,14,12,1][i%4],true);
    [1,-.5,-1,.25,.75,0,0].forEach((f,j)=>v.setFloat32(12+i*32+j*4,f,true));
  }
  const body=(at,pos,vel)=>{
    pos.forEach((f,j)=>v.setFloat32(at+j*4,f,true));
    v.setInt32(at+16,16384,true);
    vel.forEach((f,j)=>v.setFloat32(at+24+j*4,f,true));
    [0,0,.3].forEach((f,j)=>v.setFloat32(at+36+j*4,f,true));
    v.setUint8(at+48,1);
    // Deliberately non-float padding beside the body's bool.
    v.setUint8(at+49,255);v.setUint8(at+50,255);v.setUint8(at+51,255);
  };
  body(tail+12,[500,-3000,17],[120,500,0]);body(tail+64,[600,-2800,93.15],[0,100,0]);
  return buffer;
}

export function fakeEnvironment() {
  const fields={TICK:0,GOAL:1,NUM_CARS:2,NUM_PADS:3,BALL:4,CARS:22};
  const state=new Float32Array(500);state[fields.NUM_CARS]=2;state[fields.NUM_PADS]=34;
  let net,failRestore=false;const writes=[];
  const sync=()=>{state.set(net.subarray(3,21),4);for(let i=0;i<2;i++)state.set(net.subarray(21+i*81,39+i*81),22+i*51);state[0]=net[0];};
  const sim={state,writes,
    resetKickoff(){net=new Float32Array(126+2*81);net[2]=1;for(const at of [3,21,102]){net[at+3]=1;net[at+7]=1;net[at+11]=1;}sync();},
    captureNetwork(){return net.slice();},
    restoreNetwork(value){if(failRestore){failRestore=false;throw Error('simulated rejection');}net=value.slice();sync();},
    setControls(slot,control){writes.push({slot,...control});},setUnlimitedBoost(value){this.unlimited=value;},resetView(){},pollGoal(){return 0;},
    step(count=1){state[0]+=count;net[0]=state[0];},
    failNextRestore(){failRestore=true;},
  };
  sim.resetKickoff();
  return {sim,fields,stride:51,slot:0,mode:'freeplay',online:false,customMap:false};
}

if(process.argv[1]===new URL(import.meta.url).pathname) {
  const env=fakeEnvironment(),player=createTasPlayer({environment:()=>env});
  assert.equal(player.load(recording(),'<unsafe>.data').frames,4);
  assert.equal(player.snapshot().name,'<unsafe>.data');
  player.prepare({boost:33,unlimited:false});
  assert.deepEqual(Array.from(env.sim.state.slice(22,25)),[500,-3000,17]);
  assert.ok(Math.abs(env.sim.state[6]-93.15)<.001);
  assert.equal(env.sim.captureNetwork()[21+35],33);
  assert.equal(player.snapshot().frame,0);
  player.play({boost:100,unlimited:true});
  assert.equal(player.step(0).throttle,1);
  assert.equal(player.step(0).jump,false,'Duplicate hook consumed another frame');
  env.sim.step();assert.equal(player.step(1).jump,true);
  env.sim.step();assert.equal(player.step(2).jump,false,'Jump release was skipped');
  env.sim.step();assert.equal(player.step(3).handbrake,true);
  env.sim.step();assert.equal(player.step(4),null);assert.equal(player.snapshot().running,false);
  assert.equal(player.snapshot().frame,4);
  player.play();player.step(0);assert.throws(()=>player.step(3),/skipped ticks/);
  player.stop();assert.equal(player.step(10),null);
  for(const key of ['online','customMap']){
    env[key]=true;assert.throws(()=>player.play(),/Free Play/);env[key]=false;
  }
  env.mode='match';assert.throws(()=>player.prepare(),/Free Play/);env.mode='freeplay';
  const before=env.sim.captureNetwork();env.sim.failNextRestore();
  assert.throws(()=>player.prepare(),/simulated rejection/);assert.deepEqual(env.sim.captureNetwork(),before,'Failed setup did not roll back');
  const changed=recording();new DataView(changed).setFloat32(12,NaN,true);
  assert.throws(()=>player.load(changed,'bad'),/Invalid input/);assert.equal(player.snapshot().loaded,false,'Bad upload retained playable previous clip');
  for(const edit of [v=>v.setUint32(0,2,true),v=>v.setUint32(4,999,true),v=>v.setUint32(8,256,true)]){
    const b=recording();edit(new DataView(b));assert.throws(()=>player.load(b));
  }
  assert.throws(()=>player.load(recording().slice(0,-1)),/format/);
  // Upper flags are metadata; history bit 16 cannot turn into a held jump.
  const b=recording(),v=new DataView(b);v.setUint32(8,112,true);player.load(b);
  assert.equal(player.controls(0).jump,false);assert.equal(player.controls(0).boost,false);
  assert.equal(player.snapshot().extraFlags,true);
  const seen=[];
  for(const path of process.argv.slice(2)){
    const data=fs.readFileSync(path);player.load(data.buffer.slice(data.byteOffset,data.byteOffset+data.byteLength),path.split('/').at(-1));
    player.prepare();for(let i=0;i<player.snapshot().frames;i++)player.controls(i);
    seen.push({name:player.snapshot().name,frames:player.snapshot().frames,car:player.snapshot().car,ball:player.snapshot().ball});
  }
  console.log('PASS: TAS validation, input mapping, tick playback, restart, rollback, offline guards, supplied files',seen);
}
