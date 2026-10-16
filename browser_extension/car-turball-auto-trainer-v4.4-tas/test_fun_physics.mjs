import assert from 'node:assert/strict';
import {nativeTestArena} from './native-test-fixture.mjs';
import {createFunControls} from './fun-controls.mjs';

const env=await nativeTestArena(process.argv[2]),sim=env.sim,fun=createFunControls({environment:()=>env});
const original=sim.step;
function setup({pos=[0,0,17.02],vel=[0,0,0],ball=[1500,0,150],boost=5}={}) {
  fun.stop();sim.resetKickoff();sim.setUnlimitedBoost(false);
  const net=sim.captureNetwork();net.set([...pos,0,1,0,-1,0,0,0,0,1,...vel,0,0,0],21);net[21+35]=boost;
  net.set(ball,3);net.fill(0,15,21);net.set([3000,0,17.02],102);sim.restoreNetwork(net);
  sim.setControls(0,{});sim.setControls(1,{});sim.pollGoal();
}
setup();fun.toggle('boost');sim.setControls(0,{throttle:1,boost:true});sim.step(60);
assert.equal(sim.state[40],100);assert.ok(sim.state[22+51+18]<40,'Opponent received extra boost');
assert.equal(sim.captureNetwork()[2],0,'Global boost rule was changed');
console.log('PASS: native own-car infinite boost with room boost still limited');
setup({pos:[0,0,500],vel:[300,100,0]});fun.toggle('glue');sim.step(30);
const state=sim.state,car=state.slice(22,40),radius=sim.ballRadius;
for(let i=0;i<3;i++)assert.ok(Math.abs(state[4+i]-(car[i]+car[3+i]*90+car[9+i]*(radius+22)))<.04,'Glue did not follow native car');
fun.action('launch');assert.equal(fun.snapshot().glue,false);assert.ok(sim.state[17]>0,'Blue shot points away from opponent goal');
console.log('PASS: native ball glue and release-to-launch');
setup();fun.action('goal');sim.step(1);assert.notEqual(sim.pollGoal(),0,'Native engine did not detect teleported goal');
env.team=1;setup();fun.action('goal');sim.step(1);assert.notEqual(sim.pollGoal(),0);env.team=0;
console.log('PASS: native goal scoring after teleport, both teams');
setup({pos:[0,0,1000]});let net=sim.captureNetwork();net[21+18]=0;net[21+23]=net[21+25]=1;sim.restoreNetwork(net);
fun.toggle('jumps');const initialDodge=sim.state[22+42];
for(let repeat=0;repeat<3;repeat++) {
  sim.setControls(0,{pitch:-1,jump:false});sim.step(3);
  sim.setControls(0,{pitch:-1,jump:true});sim.step(1);
  sim.setControls(0,{pitch:-1,jump:false});sim.step(3);
}
assert.ok(sim.state[22+42]>=initialDodge+3,'Spent air flips were not restored');
console.log('PASS: native three consecutive air flips from an initially spent flip');
setup({pos:[0,-1800,500],vel:[0,5000,0]});sim.step(60);
const ordinaryDistance=sim.state[23]+1800;assert.ok(Math.hypot(...sim.state.slice(34,37))<=2301);
setup({pos:[0,-1800,500],vel:[0,5000,0]});fun.toggle('speed');sim.step(60);
const fastDistance=sim.state[23]+1800,actualSpeed=Math.hypot(...sim.state.slice(34,37));
assert.ok(actualSpeed>4500,'Only the speed display was changed');
assert.ok(fastDistance>ordinaryDistance*1.7,`Native displacement did not increase: ${ordinaryDistance} -> ${fastDistance}`);
fun.stop();assert.equal(sim.step,original);sim.step(1);assert.ok(Math.hypot(...sim.state.slice(34,37))<=2301,'Default speed cap did not return');
console.log('PASS: native speed and displacement bypass default cap, then return to normal',{ordinaryDistance,fastDistance,actualSpeed});
setup({pos:[0,-4000,17.02]});fun.toggle('boost');fun.toggle('speed');sim.setControls(0,{throttle:1,boost:true});
for(let batch=0;batch<3;batch++)sim.step(100);
assert.equal(fun.snapshot().enabled,true,fun.snapshot().message);
assert.ok(Math.hypot(...sim.state.slice(34,37))>2400,'Speed override cannot accelerate past the default cap from rest');
console.log('PASS: native speed override accelerates from rest past the standard cap',Math.hypot(...sim.state.slice(34,37)));
fun.stop();
