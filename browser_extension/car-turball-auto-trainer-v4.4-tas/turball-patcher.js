import { createScriptedKickoff } from './kickoff.mjs';
import { createBallVisibilityGuard } from './ball-visibility-guard.mjs';
import { createTasPlayer } from './tas-player.mjs';

// Target: Turball 6ecc13b81511-38608307515-1, gameplay module chunk-IORKFJL5.js.
// Only patch verified, unique control-flow anchors. No changes to the site's
// physics constants, collision geometry, meshes, rules or network protocol.
export function transformMainSource(source) {
  const required = [
    'async function gc(n,t={})',
    'const r=new fo;await n.track("physics","Starting physics",()=>r.init())',
    'const b=t.botController??new wi(ro.load().botId)',
    'const ut={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:false,boost:false,handbrake:false}',
    '_=r.getPads();const ti=',
    'return u.advance(jt)',
    'r.step(1);const l=r.pollGoal()',
    'export{gc as startGame}'
  ];
  for (const needle of required) {
    if (!source.includes(needle)) throw new Error('Unsupported Turball build (anchor missing): ' + needle.slice(0, 100));
  }
  const replaceOnce = (needle, replacement, title) => {
    const count = source.split(needle).length - 1;
    if (count !== 1) throw new Error(`${title}: expected one anchor, found ${count}`);
    source = source.replace(needle, replacement);
  };

  const kickoff = `(${createScriptedKickoff.toString()})()`;
  const runtime = String.raw`const __GCT4_BALL_VISUAL=BALL_GUARD_PLACEHOLDER(g.ball,()=>!g.customMapActive);
const __GCT4_BALL_VISUAL_FRAME=()=>{
  try{__GCT4_BALL_VISUAL.tick()}catch(e){console.warn('[Trainer] Ball visual guard',e);__GCT4_BALL_VISUAL.restore()}
  requestAnimationFrame(__GCT4_BALL_VISUAL_FRAME);
};
requestAnimationFrame(__GCT4_BALL_VISUAL_FRAME);
window.addEventListener('keydown',event=>{
  if(event.code!=='F9'||event.repeat)return;
  event.preventDefault();event.stopImmediatePropagation();
  __GCT4_BALL_VISUAL.setEnabled(!__GCT4_BALL_VISUAL.enabled);
},true);

const __GCT4_CHANNEL="__grandchamp_trainer_v4__";
const __GCT4_KICKOFF=KICKOFF_PLACEHOLDER;
const __GCT4_TAS=TAS_PLACEHOLDER({environment:()=>({sim:r,fields:k,stride:N,slot:h,
  online:!!u,mode:d.state.mode,customMap:!!g.customMapActive})});
const __GCT4_NATIVE=new wi("nexto");
const __GCT4_NEUTRAL=()=>({...ut});
const __GCT4_NAMES={nexto:"Nexto",grandchamp:"Turball native Nexto (GC)",tas:"TAS"};
const __GCT4={
  active:false,loading:false,selectedBot:"nexto",mode:"offline",lastControls:__GCT4_NEUTRAL(),
  error:"",info:"",lastApplyAt:0,lastWorldTick:null,lastCarCount:null,
  nextoReady:false,nextoPending:false,nextoInitPromise:null,nextoInitResolve:null,nextoInitReject:null,
  nextoInitTimer:null,nextoGeneration:1,nextoLastStep:-Infinity,nextoRequestId:0,
  nextoScriptActive:false,nextoLatency:null,nextoObservedBoost:null,nextoLastAction:null,
  nativePending:false,nativeLastStep:-Infinity,nativeGeneration:1,
  get botName(){return __GCT4_NAMES[this.selectedBot]||this.selectedBot},
  currentTeam(){return (u&&w[h]?.team!==undefined?w[h].team:x?.playerTeam??o.playerTeam)===1?1:0},
  resetNexto(){
    __GCT4_KICKOFF.reset();this.nextoGeneration++;this.nextoPending=false;
    this.nextoLastStep=-Infinity;this.nextoScriptActive=false;
    this.nextoLatency=null;this.nextoObservedBoost=null;this.nextoLastAction=null;
    if(this.nextoReady)__GCT4_post("nexto-reset",{generation:this.nextoGeneration});
  },
  resetBrain(){
    this.resetNexto();this.nativeGeneration++;this.nativePending=false;
    this.nativeLastStep=-Infinity;try{__GCT4_NATIVE.reset()}catch{}
    this.lastControls=__GCT4_NEUTRAL();this.lastWorldTick=null;this.lastCarCount=null;this.lastApplyAt=0;
  },
  watchWorld(state){
    const tick=state[k.TICK],cars=state[k.NUM_CARS];
    if(this.lastWorldTick!==null&&(tick<this.lastWorldTick||cars!==this.lastCarCount))this.resetBrain();
    this.lastWorldTick=tick;this.lastCarCount=cars;
  },
  async ensureNexto(){
    if(this.nextoReady)return true;
    if(this.nextoInitPromise)return this.nextoInitPromise;
    this.nextoInitPromise=new Promise((resolve,reject)=>{
      this.nextoInitResolve=resolve;this.nextoInitReject=reject;
      this.nextoInitTimer=setTimeout(()=>{
        if(this.nextoReady)return;
        this.nextoInitPromise=null;this.nextoInitResolve=null;this.nextoInitReject=null;
        reject(new Error("Nexto worker did not initialize in time."));
      },15000);
    });
    __GCT4_post("nexto-init");return this.nextoInitPromise;
  },
  async selectBot(id){
    if(id!=="nexto"&&id!=="grandchamp"&&id!=="tas")return;
    if(this.active)this.disable("Player control restored before changing AI.");
    this.selectedBot=id;this.error="";this.info="Selected "+this.botName+".";
    __GCT4_postStatus();
  },
  async enable(){
    if(this.active)return true;if(this.loading)return false;
    this.loading=true;this.error="";this.info="Loading "+this.botName+"…";__GCT4_postStatus();
    try{
      if(this.selectedBot==="tas"){
        __GCT4_TAS.play(this.tasOptions||{});
        this.resetBrain();this.mode="offline";this.active=true;
        this.info="TAS playback. F8 stops.";return true;
      }
      const slot=h,state=r.state;
      if(!Number.isInteger(slot)||slot<0||slot>=state[k.NUM_CARS])throw Error("No playable car is available.");
      if(u&&w[slot]?.departed)throw Error("The player car has left this room.");
      this.mode=u?"online":"offline";
      if(this.selectedBot==="nexto")await this.ensureNexto();
      else await __GCT4_NATIVE.loadPolicy("nexto");
      this.resetBrain();this.active=true;this.info=this.botName+" controls your car.";
      return true;
    }catch(e){this.active=false;this.error=e instanceof Error?e.message:String(e);this.info="";throw e}
    finally{this.loading=false;__GCT4_postStatus()}
  },
  disable(reason="Player control restored"){
    __GCT4_TAS.stop(reason);
    this.active=false;this.loading=false;this.resetBrain();this.info=reason;
    try{if(!u&&h<r.state[k.NUM_CARS])r.setControls(h,__GCT4_NEUTRAL())}catch{}
    __GCT4_postStatus();
  },
  carData(state,slot,team,fullBoost=false){
    const base=k.CARS+slot*N;
    const vec=off=>[state[base+off],state[base+off+1],state[base+off+2]];
    const boost=Number(state[base+v.BOOST]);
    return {team:team===1?1:0,pos:vec(v.POS),vel:vec(v.VEL),fwd:vec(v.FWD),up:vec(v.UP),angVel:vec(v.ANG_VEL),
      boost:fullBoost?1:Math.max(0,Math.min(1,(Number.isFinite(boost)?boost:0)/100)),
      demoed:state[base+v.DEMOED]===1,onGround:state[base+v.ON_GROUND]===1,
      hasFlip:state[base+v.HAS_FLIP_OR_JUMP]===1};
  },
  playerTeams(state,slot,team){
    const count=Math.max(1,Math.min(8,Math.trunc(state[k.NUM_CARS])));
    return Array.from({length:count},(_,i)=>w?.[i]?.team??(i===slot?team:1-team));
  },
  buildNextoPacket(state,slot,team,teams,pads,fullBoost){
    const count=Math.max(1,Math.min(8,Math.trunc(state[k.NUM_CARS])));
    const order=[slot];for(let i=0;i<count;i++)if(i!==slot&&teams[i]===team)order.push(i);
    for(let i=0;i<count;i++)if(i!==slot&&teams[i]!==team)order.push(i);
    const players=order.map((index,j)=>this.carData(state,index,teams[index],j===0&&fullBoost));
    const padInfo=[];
    for(let i=0;i<Math.min(34,Math.trunc(state[k.NUM_PADS]),pads.length);i++){
      const p=pads[i];padInfo.push({pos:[p.pos[0],p.pos[1],p.pos[2]],isBig:!!p.isBig,active:state[Qe+i*2]===1,timer:state[Qe+i*2+1]});
    }
    const bb=k.BALL;
    const prev=[this.lastControls.throttle||0,this.lastControls.steer||0,this.lastControls.pitch||0,
      this.lastControls.yaw||0,this.lastControls.roll||0,this.lastControls.jump?1:0,
      this.lastControls.boost?1:0,this.lastControls.handbrake?1:0];
    return {tick:state[k.TICK],players,ball:{pos:[state[bb],state[bb+1],state[bb+2]],
      vel:[state[bb+12],state[bb+13],state[bb+14]],angVel:[state[bb+15],state[bb+16],state[bb+17]]},
      pads:padInfo,previousAction:prev};
  },
  buildKickoffPacket(state,slot,team,teams){
    const count=Math.max(1,Math.min(8,Math.trunc(state[k.NUM_CARS]))),players=[];
    for(const i of [slot,...Array.from({length:count},(_,j)=>j).filter(j=>j!==slot)]){
      const at=k.CARS+i*N;players.push({team:teams[i]===1?1:0,
        pos:[state[at+v.POS],state[at+v.POS+1]],onGround:state[at+v.ON_GROUND]===1});
    }
    const bb=k.BALL;return {tick:state[k.TICK],players,
      ball:{pos:[state[bb],state[bb+1],state[bb+2]],vel:[state[bb+12],state[bb+13],state[bb+14]]}};
  },
  requestNexto(state,slot,team,teams,pads,fullBoost,tick){
    if(!this.nextoReady)return;
    const scripted=__GCT4_KICKOFF.step(this.buildKickoffPacket(state,slot,team,teams));
    if(scripted){if(!this.nextoScriptActive){this.nextoGeneration++;this.nextoPending=false}
      this.nextoScriptActive=true;this.lastControls={...scripted};return}
    if(this.nextoScriptActive){this.nextoGeneration++;this.nextoPending=false;this.nextoLastStep=-Infinity}
    this.nextoScriptActive=false;
    if(this.nextoPending||tick-this.nextoLastStep<8)return;
    const packet=this.buildNextoPacket(state,slot,team,teams,pads,fullBoost);
    const requestId=++this.nextoRequestId;this.nextoPending=true;this.nextoLastStep=tick;
    __GCT4_post("nexto-infer",{requestId,generation:this.nextoGeneration,packet});
  },
  requestNative(state,slot,team,pads,tick){
    if(this.nativePending||tick-this.nativeLastStep<8)return;
    if(state[k.NUM_CARS]!==2||pads.length!==34){this.error="Turball native Nexto requires 2 cars and 34 pads.";return}
    this.nativePending=true;this.nativeLastStep=tick;
    const generation=this.nativeGeneration;
    __GCT4_NATIVE.decide(state,pads,slot,team).then(controls=>{
      if(generation===this.nativeGeneration&&this.active&&this.selectedBot==="grandchamp")
        this.lastControls={...controls};
    }).catch(error=>{
      if(generation===this.nativeGeneration){this.error=error?.message||String(error);this.disable("Native AI failed.")}
    }).finally(()=>{if(generation===this.nativeGeneration)this.nativePending=false});
  },
  stepAi(){
    const state=r.state,slot=h;if(!this.active||slot<0||slot>=state[k.NUM_CARS])return;
    this.mode=u?"online":"offline";
    this.watchWorld(state);
    const team=this.currentTeam(),teams=this.playerTeams(state,slot,team),pads=r.getPads();
    const fullBoost=this.mode==="offline"&&d.state.mode!=="match"&&Le.boostOption==="unlimited";
    if(this.selectedBot==="nexto")this.requestNexto(state,slot,team,teams,pads,fullBoost,state[k.TICK]);
    else this.requestNative(state,slot,team,pads,state[k.TICK]);
    this.lastApplyAt=performance.now();
  },
  stepOffline(){
    if(!this.active||u)return;
    try{
      if(this.selectedBot==="tas"){
        const controls=__GCT4_TAS.step(r.state[k.TICK]);
        if(!controls){this.disable("TAS finished. Player control restored.");return}
        for(let slot=0;slot<r.state[k.NUM_CARS];slot++)r.setControls(slot,slot===h?controls:__GCT4_NEUTRAL());
        this.lastControls={...controls};this.lastApplyAt=performance.now();return;
      }
      this.stepAi();r.setControls(h,this.lastControls)
    }
    catch(e){this.error=e?.message||String(e);this.disable("AI stopped after an error.")}
  },
  onlineControls(human){
    if(!this.active||!u||w[h]?.departed)return human;
    try{this.stepAi();return this.lastControls}
    catch(e){this.error=e?.message||String(e);this.disable("AI stopped after an error.");return human}
  },
  snapshot(){
    const online=!!u,slot=h,team=this.currentTeam();
    let boost=null,worldTick=null,carCount=null;
    try{const state=r.state;worldTick=state[k.TICK];carCount=state[k.NUM_CARS];
      boost=state[k.CARS+slot*N+v.BOOST]}catch{}
    return {active:this.active,loading:this.loading,selectedBot:this.selectedBot,botName:this.botName,
      mode:online?"online":"offline",online,privacyCheck:"off",
      aiReady:this.selectedBot==="nexto"?this.nextoReady:__GCT4_NATIVE.isReady,
      nextoReady:this.nextoReady,nextoPending:this.nextoPending,nextoScriptActive:this.nextoScriptActive,
      nextoLatency:this.nextoLatency,nextoObservedBoost:this.nextoObservedBoost,nextoLastAction:this.nextoLastAction,
      playerSlot:slot,team,boost,unlimitedBoost:!online&&d.state.mode!=="match"&&Le.boostOption==="unlimited",
      worldTick,carCount,lastControls:{...this.lastControls},lastApplyAt:this.lastApplyAt,error:this.error,info:this.info,
      gameMode:d?.state?.mode??"unknown",phase:d?.state?.phase??"unknown",
      ballRadius:r.ballRadius,carHitboxProfile:r.carProfiles?.[slot]??null,tas:__GCT4_TAS.snapshot()};
  }
};
__GCT4_NATIVE.onError=msg=>{
  __GCT4.error=msg||"Turball native AI failed.";
  if(__GCT4.active&&__GCT4.selectedBot==="grandchamp")__GCT4.disable("Native AI worker stopped.");
  else __GCT4_postStatus();
};
function __GCT4_post(type,payload={}){
  window.postMessage({source:__GCT4_CHANNEL,from:"runtime",type,...payload},location.origin);
}
function __GCT4_postStatus(){__GCT4_post("status",{state:__GCT4.snapshot()})}
window.addEventListener("message",async event=>{
  if(event.source!==window||event.origin!==location.origin)return;
  const data=event.data;if(!data||data.source!==__GCT4_CHANNEL)return;
  if(data.from==="nexto-bridge"){
    if(data.type==="nexto-model-changed"){
      __GCT4.disable("Model changed. Press Give Control to play with the selected model.");
      __GCT4.nextoReady=false;__GCT4.nextoInitPromise=null;
      if(typeof data.modelName==="string")__GCT4_NAMES.nexto=data.modelName;
      __GCT4_postStatus();return;
    }
    if(data.type==="nexto-ready"){
      if(typeof data.modelName==="string")__GCT4_NAMES.nexto=data.modelName;
      __GCT4.nextoReady=true;clearTimeout(__GCT4.nextoInitTimer);
      const resolve=__GCT4.nextoInitResolve;
      __GCT4.nextoInitPromise=null;__GCT4.nextoInitResolve=null;__GCT4.nextoInitReject=null;
      resolve?.(true);__GCT4_postStatus();return;
    }
    if(data.type==="nexto-result"){
      if(data.generation!==__GCT4.nextoGeneration)return;
      __GCT4.nextoPending=false;
      if(data.controls){__GCT4.lastControls={...data.controls};
        __GCT4.nextoLatency=Number.isFinite(data.latencyMs)?data.latencyMs:null;
        __GCT4.nextoObservedBoost=Number.isFinite(data.observedBoost)?data.observedBoost:null;
        __GCT4.nextoLastAction=data.actionIndex??null}return;
    }
    if(data.type==="nexto-error"){
      if(data.generation!=null&&data.generation!==__GCT4.nextoGeneration)return;
      __GCT4.nextoPending=false;
      const message=data.error||"Nexto worker failed.";
      if(!__GCT4.nextoReady&&__GCT4.nextoInitReject){
        clearTimeout(__GCT4.nextoInitTimer);
        const reject=__GCT4.nextoInitReject;__GCT4.nextoInitPromise=null;
        __GCT4.nextoInitResolve=null;__GCT4.nextoInitReject=null;reject(new Error(message));
      }
      __GCT4.error=message;
      if(__GCT4.active&&__GCT4.selectedBot==="nexto")__GCT4.disable("Nexto worker stopped.");
      else __GCT4_postStatus();return;
    }
    return;
  }
  if(data.from!=="ui")return;
  try{
    if(data.command==="tas-load"){
      __GCT4.disable();__GCT4.selectedBot="tas";
      __GCT4_TAS.load(data.buffer,data.name);__GCT4.error="";__GCT4.info=__GCT4_TAS.snapshot().message;
    }
    else if(data.command==="tas-prepare"){
      __GCT4.disable();__GCT4_TAS.prepare(data.options);__GCT4.error="";__GCT4.info=__GCT4_TAS.snapshot().message;
    }
    else if(data.command==="enable"){
      if(__GCT4.selectedBot==="tas")__GCT4.tasOptions=data.options||{};
      await __GCT4.enable();
    }
    else if(data.command==="disable")__GCT4.disable();
    else if(data.command==="select-bot")await __GCT4.selectBot(data.botId);
    else if(data.command==="snapshot")__GCT4_TAS.guard();
    else return;
  }catch(error){__GCT4.error=error?.message||String(error);if(__GCT4.active&&__GCT4.selectedBot==="tas")__GCT4.disable("TAS stopped after a state change.")}__GCT4_postStatus();
});
window.addEventListener("keydown",event=>{
  if(event.code!=="F8"||event.repeat||!__GCT4.active)return;
  event.preventDefault();event.stopImmediatePropagation();__GCT4.disable("Emergency override (F8)");
},true);
window.addEventListener("blur",()=>{if(__GCT4.active&&__GCT4.selectedBot==="tas")__GCT4.disable("TAS stopped: window lost focus.")});
document.addEventListener("visibilitychange",()=>{if(document.hidden&&__GCT4.active&&__GCT4.selectedBot==="tas")__GCT4.disable("TAS stopped: tab hidden.")});
const __GCT4_ORIGINAL_STEP=r.step.bind(r);
r.step=function(...args){
  if(__GCT4.active&&__GCT4.selectedBot==="tas"){
    const steps=args[0]??1;
    if(!Number.isInteger(steps)||steps<0||steps>120){__GCT4.disable("Unsupported TAS physics batch.");return __GCT4_ORIGINAL_STEP(...args)}
    let value;for(let i=0;i<steps;i++){__GCT4.stepOffline();value=__GCT4_ORIGINAL_STEP(1)}return value;
  }
  if((args[0]??1)>0)__GCT4.stepOffline();
  return __GCT4_ORIGINAL_STEP(...args);
};
window.__GCTrainerRuntime=__GCT4;
__GCT4_post("ready",{state:__GCT4.snapshot()});
`.replace('KICKOFF_PLACEHOLDER',kickoff).replace('BALL_GUARD_PLACEHOLDER',`(${createBallVisibilityGuard.toString()})`)
 .replace('TAS_PLACEHOLDER',`(${createTasPlayer.toString()})`);

  replaceOnce('_=r.getPads();const ti=', '_=r.getPads();' + runtime + '\nconst ti=', 'trainer runtime');
  replaceOnce('return u.advance(jt)', 'return u.advance(__GCT4.onlineControls(jt))', 'online control provider');

  const expected = [
    'window.__GCTrainerRuntime=__GCT4',
    '__GCT4.stepOffline()',
    'u.advance(__GCT4.onlineControls(jt))',
    'const __GCT4_KICKOFF=',
    'buildNextoPacket',
    'model-changed'
  ];
  for (const marker of expected) if (!source.includes(marker)) throw Error('Post-patch check failed: '+marker);
  return source;
}
