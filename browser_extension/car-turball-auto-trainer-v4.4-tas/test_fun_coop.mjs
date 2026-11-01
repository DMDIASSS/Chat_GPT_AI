import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createFunControls} from './fun-controls.mjs';
import {createCooperativeFunControls} from './fun-coop.mjs';
import {fakeEnvironment} from './test_tas.mjs';
import {nativeTestArena} from './native-test-fixture.mjs';

const native=!!process.argv[2];
const hostEnv=native?await nativeTestArena(process.argv[2]):fakeEnvironment();
const guestEnv=native?await nativeTestArena(process.argv[2]):fakeEnvironment();
let validate=message=>structuredClone(message);
if(native) {
  // Exercise the actual game's text sanitization and control-message parser.
  // Frames must survive both before either peer can see our wrapper.
  const source=fs.readFileSync(process.argv[2],'utf8');
  const policy=source.slice(source.indexOf('const Zu='),source.indexOf('const Wi='));
  const parser=source.slice(source.indexOf('function Dg('),source.indexOf('const sp=',source.indexOf('function Dg(')));
  const context=vm.createContext({TextEncoder});
  vm.runInContext(policy+';const yo=14,Wi=[],Ts=[],Co=a=>KA(a,"player")||"Player",ip=a=>KA(a,"chat");'+parser+';globalThis.validate=Dg;',context);
  validate=message=>context.validate(JSON.parse(JSON.stringify(message)));
}
let now=100,dropReplies=false;const queue=[],chat=[],sent=[];
function prepare(env,host) {
  Object.assign(env,{online:true,host,slot:host?0:1,team:host?0:1,phase:'playing'});
  if(!env.sim.controlsView)env.sim.controlsView=new Float32Array(16);
  env.session={sim:env.sim,epoch:1,carSlot:env.slot,carSeats:[0,1],carTeams:[0,1],teams:[0,1],members:3,
    names:['Host','Friend'],command(message,seat){chat.push([seat,message]);},peer:{host,control(message,seat){
      sent.push([host,seat,message]);
      if(host&&dropReplies)return true;
      queue.push(()=>{const target=host?guestEnv.session:hostEnv.session;target.command(validate(message),host?0:1);});return true;
    }}};
  const net=env.sim.captureNetwork();net[21+35]=5;net[102+35]=7;env.sim.restoreNetwork(net);
}
prepare(hostEnv,true);prepare(guestEnv,false);
const oldHost=hostEnv.session,hostCommand=oldHost.command,guestCommand=guestEnv.session.command;
const originalHostStep=hostEnv.sim.step,originalGuestStep=guestEnv.sim.step;
const host=createCooperativeFunControls(createFunControls,{environment:()=>hostEnv,now:()=>now});
const guest=createCooperativeFunControls(createFunControls,{environment:()=>guestEnv,now:()=>now});
const flush=()=>{let n=0;while(queue.length){assert.ok(++n<100,'Reply loop');queue.shift()();}};
host.snapshot();guest.snapshot();
assert.equal(guest.snapshot().available,true,'Joined controls are unnecessarily blocked');
guest.toggle('boost');flush();assert.equal(guest.snapshot().enabled,false);assert.equal(hostEnv.sim.captureNetwork()[102+35],7);
assert.match(guest.snapshot().message,/Allow friend controls/);
host.setAllowFriends(true);guest.connect();flush();assert.equal(guest.snapshot().connected,true);
guest.setSpeed(8000);flush();guest.toggle('boost');guest.toggle('speed');flush();
assert.equal(guest.snapshot().boost,true);assert.equal(guest.snapshot().speed,true);assert.equal(guest.snapshot().speedLimit,8000);
hostEnv.sim.step(1);guestEnv.sim.step(1);
assert.equal(hostEnv.sim.captureNetwork()[102+35],100,'Host did not refill friend boost');
assert.ok(hostEnv.sim.captureNetwork()[21+35]<10,'Friend modified host boost');
assert.equal(guestEnv.sim.captureNetwork()[102+35],100,'Acknowledged effect was not mirrored in prediction');
guest.action('goal');flush();assert.equal(hostEnv.sim.captureNetwork()[4],-5500,'Friend goal action used host team');
guest.stop();flush();assert.equal(hostEnv.sim.step,originalHostStep);assert.equal(guestEnv.sim.step,originalGuestStep);
assert.equal(chat.length,0,'Extension frames leaked into visible chat');
hostEnv.session.command(validate({type:'chat',text:'normal game chat'}),1);assert.equal(chat.length,1,'Ordinary chat was swallowed');

// Changed state is never applied on behalf of a nonexistent member/observer.
hostEnv.session.command(validate({type:'chat',text:'~gctf1~[1,10,1,1,15,6000,1]'}),7);
assert.equal(host.snapshot().enabled,false);
hostEnv.session.teams[1]=-1;guest.toggle('glue');flush();assert.equal(guest.snapshot().enabled,false);hostEnv.session.teams[1]=1;
guest.toggle('boost');flush();assert.equal(host.snapshot().enabled,true);
host.setAllowFriends(false);now+=1001;guest.guard();flush();assert.equal(guest.snapshot().enabled,false);assert.equal(hostEnv.sim.step,originalHostStep);
host.setAllowFriends(true);guest.toggle('boost');flush();
dropReplies=true;now+=5001;host.guard();guest.guard();flush();
assert.equal(host.snapshot().enabled,false,'Host retained effects after friend heartbeat expired');
assert.equal(guest.snapshot().enabled,false,'Guest retained prediction after host timeout');dropReplies=false;
guest.connect();flush();guest.toggle('boost');flush();host.stop('F8');
assert.equal(host.snapshot().allowFriends,false);now+=1001;guest.guard();flush();assert.equal(guest.snapshot().enabled,false);
host.setAllowFriends(true);guest.toggle('boost');queue.shift()();
const delayedReply=queue.shift();assert.equal(typeof delayedReply,'function');
now+=5001;guest.guard();host.guard();delayedReply();
assert.equal(guest.snapshot().enabled,false,'Delayed acknowledgement re-enabled effects after timeout');
host.setAllowFriends(true);hostEnv.online=false;hostEnv.session=null;host.guard();
assert.equal(host.snapshot().allowFriends,false);assert.equal(guest.snapshot().enabled,false);
assert.equal(oldHost.command,hostCommand,'Host command hook was not restored after leaving');
guestEnv.online=false;const oldGuest=guestEnv.session;guestEnv.session=null;guest.guard();assert.equal(oldGuest.command,guestCommand);
assert.equal(hostEnv.sim.step,originalHostStep);assert.equal(guestEnv.sim.step,originalGuestStep);
assert.ok(sent.every(([, ,message])=>message.text.length<240),'Frames exceed native chat limits');
console.log(`PASS: ${native?'actual native physics + real protocol validation':'fake transport'} host cooperation, own-car targeting, prediction, team-aware actions, denial, chat preservation, timeout, F8 and session cleanup`);
