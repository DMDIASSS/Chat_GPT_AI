import { createScriptedKickoff } from './kickoff.mjs';
import { createBallVisibilityGuard } from './ball-visibility-guard.mjs';
import { createTasPlayer } from './tas-player.mjs';
import { createFunControls } from './fun-controls.mjs';
import { createCooperativeFunControls } from './fun-coop.mjs';
export function transformMainSource(source) {
  // Vite renames minified identifiers on each deployment. Translate only
  // injected snippets, and verify signature groups before patching anything.
  // Never blindly replace identifier tokens in the game's own source.
  const build20261015 = source.includes('R=new Qk(kd.load().botId)') &&
    source.includes('sl=c.getPads();R.onError=');
  const build20261014 = source.includes('D=new ak(Zh.load().botId)') &&
    source.includes('xt=c.getPads();D.onError=');
  const maps = {
    latest: {
      Pc:'lh', ce:'ee', ic:'Sc', sk:'Qk', Gf:'k0', te:'Q', Ra:'Ya', zn:'ro',
      R:'P', D:'R', De:'He', wr:'Mr', xt:'sl', q:'$', St:'wt', Z:'D', j:'v',
      ke:'ve', Oe:'Ve', Gt:'Ht'
    },
    previous: {Pc:'Ic', ce:'oe', ic:'sc', sk:'ak', Gf:'Df', te:'ee', Ra:'Pa', zn:'Vn'}
  };
  const names = build20261015 ? maps.latest : build20261014 ? maps.previous : {};
  const fragment = text => text.replace(
    /\b(Pc|ce|ic|sk|Gf|te|Ra|zn|De|wr|xt|St|ke|Oe|Gt|R|D|q|Z|j)\b/g,
    name => Object.hasOwn(names, name) ? names[name] : name
  );
  const signatures = build20261015 ? [
    'class Qk{', 'class k0{',
    'He=51,Xc=8,Ya=8,ro=P.CARS+Ya*He',
    'Q={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:!1,boost:!1,handbrake:!1}'
  ] : build20261014 ? [
    'class ak{', 'class Df{',
    'De=51,Cc=8,Pa=8,Vn=R.CARS+Pa*De',
    'ee={throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:!1,boost:!1,handbrake:!1}'
  ] : [];
  for (const signature of signatures) {
    if (!source.includes(signature)) throw new Error('Unsupported game build: ' + signature);
  }
  const replaceExact = (needle, replacement, label, expected = 1) => {
    needle = fragment(needle);
    replacement = fragment(replacement);
    const count = source.split(needle).length - 1;
    if (count !== expected) {
      throw new Error(`${label}: expected ${expected} match(es), found ${count}`);
    }
    source = source.split(needle).join(replacement);
  };

  // Older builds have this exact input expression, newer ones sometimes
  // change its shape. It is an OPTIONAL optimization, not essential: every
  // verified offline physics hook below calls stepOffline() immediately before
  // c.step(1), overriding any earlier human input in the same simulation tick.
  // Do NOT fail the whole extension just because the optional hook is absent.
  // Leave unsupported/unrecognized input code byte-for-byte unchanged.
  const humanInput = fragment('d||c.setControls(h,Gt),Oe&&Pc("consume",Gt.boost)');
  if (source.split(humanInput).length === 2) {
    replaceExact(
      'd||c.setControls(h,Gt),Oe&&Pc("consume",Gt.boost)',
      'd||__GCT4.controlsOffline||c.setControls(h,Gt),Oe&&Pc("consume",Gt.boost)',
      'optional offline human input hook'
    );
  }

  // IMPORTANT: do NOT patch the multiplayer tick/input expression at all.
  // v4.1 leaves Car Soccer's online simulation loop byte-for-byte original.
  // When takeover is enabled later, we temporarily wrap only that session's
  // readControls provider and restore it on disable. This means creating /
  // joining a room runs the exact original multiplayer hot path.
  const onlineInputNeedle =
    'this.tick++,this.spectator||(this.controls[this.carSlot]={...this.readControls()}),this.peer.host?';
  if ((source.split(onlineInputNeedle).length - 1) !== 1) {
    throw new Error('online input signature: expected 1 match');
  }

  replaceExact(
    'c.setControls(wr,ce),c.step(1)',
    'c.setControls(wr,ce),__GCT4.stepOffline(),c.step(1)',
    'offline match physics hooks',
    3
  );

  replaceExact(
    'if(q.state.mode==="match")return ic();c.step(1),j.record(c.state,c.ballTouchMask,l);',
    'if(q.state.mode==="match")return ic();__GCT4.stepOffline(),c.step(1),j.record(c.state,c.ballTouchMask,l);',
    'freeplay physics hook'
  );

  replaceExact(
    'if(q.state.mode==="match"){if(!ic(!0))return!1}else c.step(1),c.pollGoal();',
    'if(q.state.mode==="match"){if(!ic(!0))return!1}else __GCT4.stepOffline(),c.step(1),c.pollGoal();',
    'freeplay celebration physics hook'
  );

  replaceExact(
    'const ke=Z?()=>{c.setUnlimitedBoost(!0),c.step(1);',
    'const ke=Z?()=>{c.setUnlimitedBoost(!0),__GCT4.stepOffline(),c.step(1);',
    'custom map physics hook'
  );

  const runtimeAnchor = 'xt=c.getPads();D.onError=';
  const runtime = String.raw`xt=c.getPads();
const __GCT4_BALL_VISUAL=BALL_GUARD_PLACEHOLDER(se.ball,()=>!se.customMapActive);
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

const __GCT4_KICKOFF=(${createScriptedKickoff.toString()})();
const __GCT4_TAS=(${createTasPlayer.toString()})({environment:()=>({sim:c,fields:R,stride:De,slot:h,
  online:!!d,mode:q.state.mode,customMap:!!Z})});
const __GCT4_FUN=(${createCooperativeFunControls.toString()})(${createFunControls.toString()},{environment:()=>{
  const online=!!(d&&m),session=online?m:null;
  return {sim:online?session.sim:c,fields:R,stride:De,slot:online?session.carSlot:h,
    team:online?session.carTeams[session.carSlot]:A.playerTeam,online,host:!!session?.peer?.host,
    spectator:!!session?.spectator,mode:online?"match":q.state.mode,
    phase:online?session.match?.state?.phase:q.state.phase,customMap:!online&&!!Z,session};
},onRemoteStart:()=>{if(__GCT4.active||__GCT4.loading)__GCT4.disable("Player control restored for friend controls.")}});
const __GCT4_NATIVE=new sk("grand-champion");
const __GCT4_ONLINE_KEY=32767;
const __GCT4_CHANNEL="__grandchamp_trainer_v4__";
const __GCT4_NAMES={nexto:"Nexto",grandchamp:"Grand Champion",tas:"TAS"};
const __GCT4_NEUTRAL=()=>({...te});
const __GCT4={
  active:!1,
  loading:!1,
  activationGeneration:0,
  selectedBot:"nexto",
  mode:"offline",
  boundOnline:null,
  onlineProviderSession:null,
  onlineOriginalReadControls:null,
  onlineWrappedReadControls:null,
  onlineAI:null,
  onlineLastStep:-1/0,
  lastControls:{...te},
  lastApplyAt:0,
  lastWorldTick:null,
  lastCarCount:null,
  error:"",
  info:"",

  nextoScriptActive:!1,
  nextoReady:!1,
  nextoPending:!1,
  nextoRequestId:0,
  nextoGeneration:1,
  nextoLastStep:-1/0,
  nextoLatency:null,
  nextoObservedBoost:null,
  nextoLastAction:null,
  nextoInitPromise:null,
  nextoInitResolve:null,
  nextoInitReject:null,
  nextoInitTimer:null,

  get botName(){return __GCT4_NAMES[this.selectedBot]||this.selectedBot},
  get controlsOffline(){return this.active&&this.mode==="offline"&&!d},

  async ensureNexto(){
    if(this.nextoReady)return!0;
    if(this.nextoInitPromise)return this.nextoInitPromise;
    this.nextoInitPromise=new Promise((resolve,reject)=>{
      this.nextoInitResolve=resolve;
      this.nextoInitReject=reject;
      this.nextoInitTimer=setTimeout(()=>{
        if(this.nextoReady)return;
        this.nextoInitPromise=null;
        this.nextoInitResolve=null;
        this.nextoInitReject=null;
        reject(new Error("Nexto worker did not initialize in time."))
      },15000)
    });
    __GCT4_post("nexto-init");
    return this.nextoInitPromise
  },

  resetNexto(){
    __GCT4_KICKOFF.reset();
    this.nextoScriptActive=!1;
    this.nextoGeneration++;
    this.nextoPending=!1;
    this.nextoLastStep=-1/0;
    this.nextoObservedBoost=null;
    this.nextoLastAction=null;
    if(this.nextoReady)__GCT4_post("nexto-reset",{generation:this.nextoGeneration})
  },

  resetBrain(){
    try{__GCT4_NATIVE.reset()}catch{}
    try{this.onlineAI?.reset()}catch{}
    this.onlineLastStep=-1/0;
    this.resetNexto();
    this.lastControls={...te};
    this.lastApplyAt=0;
    this.lastWorldTick=null;
    this.lastCarCount=null
  },

  restoreOnlineProvider(){
    const session=this.onlineProviderSession;
    const original=this.onlineOriginalReadControls;
    const wrapped=this.onlineWrappedReadControls;
    try{
      if(session&&original&&session.readControls===wrapped)session.readControls=original
    }catch{}
    this.onlineProviderSession=null;
    this.onlineOriginalReadControls=null;
    this.onlineWrappedReadControls=null
  },

  installOnlineProvider(session){
    if(!session||typeof session.readControls!=="function")throw new Error("Online input provider is unavailable.");
    this.restoreOnlineProvider();
    const original=session.readControls;
    const runtime=this;
    const wrapped=function(...args){
      let human={...te};
      try{
        const value=original.apply(this,args);
        if(value&&typeof value==="object")human={...value}
      }catch{}
      if(!runtime.shouldControlOnline(session))return human;
      return runtime.computeOnlineControls(session,human)
    };
    this.onlineProviderSession=session;
    this.onlineOriginalReadControls=original;
    this.onlineWrappedReadControls=wrapped;
    session.readControls=wrapped
  },

  async selectBot(botId){
    if(botId!=="nexto"&&botId!=="grandchamp"&&botId!=="tas")return;
    if(this.active)this.disable("Player control restored before changing AI.");
    this.selectedBot=botId;
    this.error="";
    this.info="Selected "+this.botName+".";
    __GCT4_postStatus()
  },

  async enable(){
    __GCT4_FUN.stop("Fun controls off while AI/TAS runs.");
    if(this.active)return!0;
    if(this.loading)return!1;
    const activation=++this.activationGeneration;
    this.loading=!0;
    this.error="";
    this.info="Loading "+this.botName+"…";
    __GCT4_postStatus();
    try{
      if(this.selectedBot==="tas"){
        __GCT4_TAS.play(this.tasOptions||{});
        this.resetBrain();this.mode="offline";this.active=!0;
        this.info="TAS playback. F8 stops.";return!0
      }
      if(d&&m){
        if(m.spectator)throw new Error("Cannot take over while spectating.");
        const team=m.carTeams[m.carSlot];
        if(team!==0&&team!==1)throw new Error("Join Blue or Orange first.");
        this.mode="online";
        this.boundOnline=m
      }else{
        this.mode="offline";
        this.boundOnline=null
      }

      if(this.selectedBot==="nexto"){
        try{this.onlineAI?.dispose()}catch{}
        this.onlineAI=null;
        await this.ensureNexto()
      }else if(this.mode==="online"){
        try{this.onlineAI?.dispose()}catch{}
        this.onlineAI=new Gf;
        await this.onlineAI.add(__GCT4_ONLINE_KEY,"grand-champion");
        this.onlineAI.reset();
        this.onlineLastStep=-1/0
      }else{
        try{this.onlineAI?.dispose()}catch{}
        this.onlineAI=null;
        __GCT4_NATIVE.select("grand-champion");
        await __GCT4_NATIVE.loadPolicy("grand-champion")
      }

      if(activation!==this.activationGeneration)return!1;
      // Stability checks only; no room-public/private metadata is inspected.
      if(this.mode==="online"){
        if(!d||!m||m!==this.boundOnline)throw new Error("Online session changed while AI was loading.");
        const team=m.carTeams[m.carSlot];
        if(m.spectator||team!==0&&team!==1)throw new Error("Your playable online car is no longer available.")
      }else if(d){
        throw new Error("Game mode changed while AI was loading.")
      }

      this.resetBrain();
      if(this.mode==="online")this.installOnlineProvider(this.boundOnline);
      this.active=!0;
      this.info=this.botName+" controls your car.";
      __GCT4_postStatus();
      return!0
    }catch(e){
      if(activation!==this.activationGeneration)return!1;
      this.active=!1;
      this.restoreOnlineProvider();
      this.boundOnline=null;
      try{this.onlineAI?.dispose()}catch{}
      this.onlineAI=null;
      this.error=e instanceof Error?e.message:String(e);
      this.info="";
      throw e
    }finally{
      if(activation===this.activationGeneration)this.loading=!1;
      __GCT4_postStatus()
    }
  },

  disable(reason="Player control restored"){
    this.activationGeneration++;
    __GCT4_TAS.stop(reason);
    this.active=!1;
    this.loading=!1;
    this.restoreOnlineProvider();
    this.boundOnline=null;
    this.resetBrain();
    try{this.onlineAI?.dispose()}catch{}
    this.onlineAI=null;
    this.info=reason;
    try{
      if(d&&m&&!m.spectator){
        m.controls[m.carSlot]={...te};
        m.sim.setControls(m.carSlot,te)
      }else{
        c.setControls(h,te)
      }
    }catch{}
    __GCT4_postStatus()
  },

  watchWorld(state){
    const tick=state[R.TICK];
    const cars=state[R.NUM_CARS];
    if(this.lastWorldTick!==null&&(tick<this.lastWorldTick||cars!==this.lastCarCount)){
      try{__GCT4_NATIVE.reset()}catch{}
      try{this.onlineAI?.reset()}catch{}
      this.onlineLastStep=-1/0;
      this.resetNexto();
      this.lastControls={...te}
    }
    this.lastWorldTick=tick;
    this.lastCarCount=cars
  },

  carData(state,slot,team,forceFullBoost=!1){
    const base=R.CARS+slot*De;
    const vec=(off)=>[state[base+off],state[base+off+1],state[base+off+2]];
    const rawBoost=Number(state[base+M.BOOST]);
    return{
      team:team===1?1:0,
      pos:vec(M.POS),
      vel:vec(M.VEL),
      fwd:vec(M.FWD),
      up:vec(M.UP),
      angVel:vec(M.ANG_VEL),
      // Nexto was trained with boost_amount normalized to [0,1]. In unlimited
      // modes we explicitly show SELF as full every inference rather than a
      // stale/decreasing virtual-bot boost value.
      boost:forceFullBoost?1:Math.max(0,Math.min(1,(Number.isFinite(rawBoost)?rawBoost:0)/100)),
      demoed:state[base+M.DEMOED]===1,
      onGround:state[base+M.ON_GROUND]===1,
      hasFlip:state[base+M.HAS_FLIP_OR_JUMP]===1
    }
  },

  buildNextoPacket(state,slot,team,teams,pads,unlimitedSelf){
    const numCars=Math.max(1,Math.min(Ra,Math.trunc(state[R.NUM_CARS])));
    const order=[slot];
    for(let i=0;i<numCars;i++)if(i!==slot&&(teams[i]===team))order.push(i);
    for(let i=0;i<numCars;i++)if(i!==slot&&(teams[i]!==team))order.push(i);
    const players=order.map((carSlot,index)=>this.carData(state,carSlot,teams[carSlot],index===0&&unlimitedSelf));
    const padsInfo=[];
    const count=Math.min(34,Math.trunc(state[R.NUM_PADS]),pads?.length??0);
    for(let i=0;i<count;i++){
      const p=pads[i];
      padsInfo.push({
        pos:[p.pos[0],p.pos[1],p.pos[2]],
        isBig:!!p.isBig,
        active:state[zn+i*2]===1,
        timer:state[zn+i*2+1]
      })
    }
    const b=R.BALL;
    const previous=[
      this.lastControls.throttle||0,this.lastControls.steer||0,this.lastControls.pitch||0,
      this.lastControls.yaw||0,this.lastControls.roll||0,this.lastControls.jump?1:0,
      this.lastControls.boost?1:0,this.lastControls.handbrake?1:0
    ];
    return{
      tick:state[R.TICK],
      players,
      ball:{
        pos:[state[b],state[b+1],state[b+2]],
        vel:[state[b+12],state[b+13],state[b+14]],
        angVel:[state[b+15],state[b+16],state[b+17]]
      },
      pads:padsInfo,
      previousAction:previous
    }
  },

  buildKickoffPacket(state,slot,team,teams){
    const players=[];
    const count=Math.max(1,Math.min(Ra,Math.trunc(state[R.NUM_CARS])));
    const order=[slot];for(let i=0;i<count;i++)if(i!==slot)order.push(i);
    for(const i of order){
      const base=R.CARS+i*De;
      players.push({team:teams[i]===1?1:0,
        pos:[state[base+M.POS],state[base+M.POS+1]],
        onGround:state[base+M.ON_GROUND]===1})
    }
    const b=R.BALL;
    return {tick:state[R.TICK],players,ball:{
      pos:[state[b],state[b+1],state[b+2]],
      vel:[state[b+12],state[b+13],state[b+14]]}}
  },

  requestNexto(state,slot,team,teams,pads,unlimitedSelf,tick){
    if(!this.nextoReady)return;
    try{
      const scripted=__GCT4_KICKOFF.step(this.buildKickoffPacket(state,slot,team,teams));
      if(scripted){
        if(!this.nextoScriptActive){this.nextoGeneration++;this.nextoPending=!1;}
        this.nextoScriptActive=!0;this.lastControls={...scripted};return
      }
      if(this.nextoScriptActive){this.nextoGeneration++;this.nextoPending=!1;this.nextoLastStep=-1/0;}
      this.nextoScriptActive=!1;
      if(this.nextoPending||tick-this.nextoLastStep<8)return;
      const packet=this.buildNextoPacket(state,slot,team,teams,pads,unlimitedSelf);
      const requestId=++this.nextoRequestId;
      this.nextoPending=!0;
      this.nextoLastStep=tick;
      __GCT4_post("nexto-infer",{requestId,generation:this.nextoGeneration,packet})
    }catch(e){
      this.error=e instanceof Error?e.message:String(e);
      this.nextoPending=!1
    }
  },

  stepOffline(){
    if(!this.controlsOffline)return;
    try{
      if(this.selectedBot==="tas"){
        const controls=__GCT4_TAS.step(c.state[R.TICK]);
        if(!controls){this.disable("TAS finished. Player control restored.");return}
        for(let slot=0;slot<c.state[R.NUM_CARS];slot++)c.setControls(slot,slot===h?controls:__GCT4_NEUTRAL());
        this.lastControls={...controls};this.lastApplyAt=performance.now();return
      }
      const state=c.state;
      this.watchWorld(state);
      let controls;
      if(this.selectedBot==="nexto"){
        const numCars=Math.max(1,Math.min(Ra,Math.trunc(state[R.NUM_CARS])));
        const teams=Array.from({length:numCars},(_,i)=>i===h?A.playerTeam:A.botTeam);
        const unlimited=(q.state.mode!=="match"&&St.boostOption==="unlimited")||!!Z;
        this.requestNexto(state,h,A.playerTeam,teams,xt,unlimited,state[R.TICK]);
        controls=this.lastControls
      }else{
        controls=__GCT4_NATIVE.step(state,xt,h,A.playerTeam);
        this.lastControls={...controls}
      }
      this.lastApplyAt=performance.now();
      c.setControls(h,controls)
    }catch(e){
      this.error=e instanceof Error?e.message:String(e);
      this.disable(this.botName+" stopped after an AI error.")
    }
  },

  shouldControlOnline(session){
    if(!this.active||this.mode!=="online"||!d||!m)return!1;
    if(session!==m||session!==this.boundOnline||session.spectator)return!1;
    const team=session.carTeams[session.carSlot];
    return team===0||team===1
  },

  computeOnlineControls(session,human){
    // Called by the temporary readControls wrapper. The original provider has
    // already run exactly once for this tick, so never call readControls here.
    if(!this.shouldControlOnline(session))return human;
    try{
      const state=session.sim.state;
      const slot=session.carSlot;
      const team=session.carTeams[slot];
      this.watchWorld(state);

      if(this.selectedBot==="nexto"){
        const pads=session.sim.getPads();
        const unlimited=session.stage==="warmup";
        this.requestNexto(state,slot,team,session.carTeams,pads,unlimited,session.tick);
        this.lastApplyAt=performance.now();
        return this.lastControls
      }

      if(!this.onlineAI)throw new Error("Grand Champion online worker is not ready.");
      if(session.tick-this.onlineLastStep>=8){
        const seats=session.carSeats.slice();
        seats[slot]=__GCT4_ONLINE_KEY;
        this.onlineAI.step(session.sim,seats,session.carTeams,session.tick);
        this.onlineLastStep=session.tick
      }
      if(this.onlineAI.error)throw new Error(this.onlineAI.error);
      const controls={...this.onlineAI.get(__GCT4_ONLINE_KEY)};
      this.lastControls=controls;
      this.lastApplyAt=performance.now();
      return controls
    }catch(e){
      this.error=e instanceof Error?e.message:String(e);
      this.disable(this.botName+" stopped after an AI error.");
      return human
    }
  },

  snapshot(){
    const online=!!(d&&m);
    let playerSlot=h,team=A.playerTeam,boost=null,unlimited=null,worldTick=null,carCount=null;
    try{
      if(online){
        playerSlot=m.carSlot;
        team=m.carTeams[m.carSlot];
        const state=m.sim.state;
        worldTick=state[R.TICK];
        carCount=state[R.NUM_CARS];
        const base=R.CARS+playerSlot*De;
        boost=state[base+M.BOOST];
        unlimited=m.stage==="warmup"
      }else{
        const state=c.state;
        worldTick=state[R.TICK];
        carCount=state[R.NUM_CARS];
        const base=R.CARS+h*De;
        boost=state[base+M.BOOST];
        unlimited=(q.state.mode!=="match"&&St.boostOption==="unlimited")||!!Z
      }
    }catch{}
    const nativeReady=this.mode==="online"?!!this.onlineAI&&!this.onlineAI.error&&this.onlineAI.seats.has(__GCT4_ONLINE_KEY):__GCT4_NATIVE.isReady;
    return{
      active:this.active,
      loading:this.loading,
      selectedBot:this.selectedBot,
      botName:this.botName,
      mode:this.mode,
      online,
      privacyCheck:"off",
      aiReady:this.selectedBot==="nexto"?this.nextoReady:nativeReady,
      nextoReady:this.nextoReady,
      nextoPending:this.nextoPending,
      nextoScriptActive:this.nextoScriptActive,
      nextoLatency:this.nextoLatency,
      nextoObservedBoost:this.nextoObservedBoost,
      nextoLastAction:this.nextoLastAction,
      playerSlot,
      team,
      boost,
      unlimitedBoost:unlimited,
      worldTick,
      carCount,
      lastControls:{...this.lastControls},
      lastApplyAt:this.lastApplyAt,
      error:this.error,
      info:this.info,
      gameMode:q?.state?.mode??"unknown",
      phase:online?(m?.match?.state?.phase??m?.stage??"unknown"):(q?.state?.phase??"unknown")
      ,tas:__GCT4_TAS.snapshot()
      ,fun:__GCT4_FUN.snapshot()
    }
  }
};

__GCT4_NATIVE.onError=message=>{
  __GCT4.error=message||"Grand Champion worker failed.";
  if(__GCT4.active&&__GCT4.mode==="offline"&&__GCT4.selectedBot==="grandchamp")__GCT4.disable("Grand Champion worker stopped.");
  else __GCT4_postStatus()
};

function __GCT4_post(type,payload={}){
  window.postMessage({source:__GCT4_CHANNEL,from:"runtime",type,...payload},location.origin)
}
function __GCT4_postStatus(){__GCT4_post("status",{state:__GCT4.snapshot()})}

window.addEventListener("message",async event=>{
  if(event.source!==window||event.origin!==location.origin)return;
  const data=event.data;
  if(!data||data.source!==__GCT4_CHANNEL)return;

  if(data.from==="nexto-bridge"){
    if(data.type==="nexto-model-changed"){
      __GCT4.disable("Model changed. Press Give Control to play with the selected model.");
      __GCT4.nextoReady=!1;__GCT4.nextoInitPromise=null;
      if(typeof data.modelName==="string")__GCT4_NAMES.nexto=data.modelName;
      __GCT4_postStatus();return
    }
    if(data.type==="nexto-ready"){
      if(typeof data.modelName==="string")__GCT4_NAMES.nexto=data.modelName;
      __GCT4.nextoReady=!0;
      clearTimeout(__GCT4.nextoInitTimer);
      const resolve=__GCT4.nextoInitResolve;
      __GCT4.nextoInitPromise=null;
      __GCT4.nextoInitResolve=null;
      __GCT4.nextoInitReject=null;
      resolve?.(!0);
      __GCT4_postStatus();
      return
    }
    if(data.type==="nexto-result"){
      if(data.generation!==__GCT4.nextoGeneration)return;
      __GCT4.nextoPending=!1;
      if(data.controls){
        __GCT4.lastControls={...data.controls};
        __GCT4.nextoLatency=Number.isFinite(data.latencyMs)?data.latencyMs:null;
        __GCT4.nextoObservedBoost=Number.isFinite(data.observedBoost)?data.observedBoost:null;
        __GCT4.nextoLastAction=data.actionIndex??null
      }
      return
    }
    if(data.type==="nexto-error"){
      if(data.generation!=null&&data.generation!==__GCT4.nextoGeneration)return;
      __GCT4.nextoPending=!1;
      const message=data.error||"Nexto worker failed.";
      if(!__GCT4.nextoReady&&__GCT4.nextoInitReject){
        clearTimeout(__GCT4.nextoInitTimer);
        const reject=__GCT4.nextoInitReject;
        __GCT4.nextoInitPromise=null;
        __GCT4.nextoInitResolve=null;
        __GCT4.nextoInitReject=null;
        reject(new Error(message))
      }
      __GCT4.error=message;
      if(__GCT4.active&&__GCT4.selectedBot==="nexto")__GCT4.disable("Nexto worker stopped.");
      else __GCT4_postStatus();
      return
    }
    return
  }

  if(data.from!=="ui")return;
  try{
    if(data.command==="fun-toggle"){
      if(__GCT4.active||__GCT4.loading)__GCT4.disable("Player control restored for fun controls.");
      __GCT4_FUN.toggle(data.effect);__GCT4.error="";__GCT4.info=__GCT4_FUN.snapshot().message
    }
    else if(data.command==="fun-action"){
      if(__GCT4.active||__GCT4.loading)__GCT4.disable("Player control restored for fun controls.");
      __GCT4_FUN.action(data.action);__GCT4.error="";__GCT4.info=__GCT4_FUN.snapshot().message
    }
    else if(data.command==="fun-speed")__GCT4_FUN.setSpeed(Number(data.speed));
    else if(data.command==="fun-friends"){__GCT4_FUN.setAllowFriends(!!data.allowed);__GCT4.error=""}
    else if(data.command==="fun-connect"){__GCT4_FUN.connect();__GCT4.error=""}
    else if(data.command==="fun-stop")__GCT4_FUN.stop();
    else if(data.command==="tas-load"){
      __GCT4_FUN.stop();
      __GCT4.disable();__GCT4.selectedBot="tas";
      __GCT4_TAS.load(data.buffer,data.name);__GCT4.error="";__GCT4.info=__GCT4_TAS.snapshot().message
    }
    else if(data.command==="tas-prepare"){
      __GCT4_FUN.stop();
      __GCT4.disable();__GCT4_TAS.prepare(data.options);__GCT4.error="";__GCT4.info=__GCT4_TAS.snapshot().message
    }
    else if(data.command==="enable"){
      if(__GCT4.selectedBot==="tas")__GCT4.tasOptions=data.options||{};
      await __GCT4.enable()
    }
    else if(data.command==="disable"){__GCT4_FUN.stop();__GCT4.disable()}
    else if(data.command==="select-bot")await __GCT4.selectBot(data.botId);
    else if(data.command==="snapshot"){__GCT4_TAS.guard();__GCT4_FUN.guard()}
    else return
  }catch(error){__GCT4.error=error?.message||String(error);if(__GCT4.active&&__GCT4.selectedBot==="tas")__GCT4.disable("TAS stopped after a state change.")}
  __GCT4_postStatus()
});

window.addEventListener("keydown",event=>{
  if(event.code!=="F8"||event.repeat||!(__GCT4.active||__GCT4.loading||__GCT4_FUN.snapshot().enabled||__GCT4_FUN.snapshot().allowFriends))return;
  event.preventDefault();
  event.stopImmediatePropagation();
  __GCT4_FUN.stop("Emergency override (F8)");__GCT4.disable("Emergency override (F8)")
},!0);
window.addEventListener("blur",()=>{__GCT4_FUN.stop("Fun controls off: window lost focus.");if(__GCT4.active&&__GCT4.selectedBot==="tas")__GCT4.disable("TAS stopped: window lost focus.")});
document.addEventListener("visibilitychange",()=>{if(document.hidden){__GCT4_FUN.stop("Fun controls off: tab hidden.");if(__GCT4.active&&__GCT4.selectedBot==="tas")__GCT4.disable("TAS stopped: tab hidden.")}});
const __GCT4_FUN_KEYS={KeyG:["toggle","glue"],KeyB:["toggle","boost"],KeyJ:["toggle","jumps"],KeyV:["toggle","speed"],KeyL:["action","launch"],KeyP:["action","goal"],KeyH:["action","recall"]};
window.addEventListener("keydown",event=>{
  if(event.repeat||event.ctrlKey||event.altKey||event.metaKey||document.hidden)return;
  const target=event.target;
  if(target&&(target.isContentEditable||target.closest?.("input,textarea,select,[contenteditable='true'],#gct4-panel")))return;
  const choice=__GCT4_FUN_KEYS[event.code];if(!choice)return;
  event.preventDefault();event.stopImmediatePropagation();
  try{
    if(__GCT4.active||__GCT4.loading)__GCT4.disable("Player control restored for fun controls.");
    if(choice[0]==="toggle")__GCT4_FUN.toggle(choice[1]);else __GCT4_FUN.action(choice[1]);
    __GCT4.error="";__GCT4.info=__GCT4_FUN.snapshot().message
  }catch(error){__GCT4.error=error?.message||String(error)}
  __GCT4_postStatus()
},true);

window.__GCTrainerRuntime=__GCT4;
__GCT4_post("ready",{state:__GCT4.snapshot()});
D.onError=`.replace('BALL_GUARD_PLACEHOLDER',`(${createBallVisibilityGuard.toString()})`);

  replaceExact(runtimeAnchor, runtime, 'runtime injection anchor');

  const required = [
    'const __GCT4_NATIVE=new sk("grand-champion")',
    'const __GCT4_KICKOFF=',
    '__GCT4.stepOffline(),c.step(1)',
    'installOnlineProvider(session)',
    'computeOnlineControls(session,human)',
    'selectedBot:"nexto"',
    'this.requestNexto(state,h,A.playerTeam,teams,xt,unlimited,state[R.TICK])',
    'this.requestNexto(state,slot,team,session.carTeams,pads,unlimited,session.tick)',
    'boost:forceFullBoost?1:',
    'privacyCheck:"off"',
    'window.__GCTrainerRuntime=__GCT4'
  ];
  for (const marker of required) {
    if (!source.includes(fragment(marker))) throw new Error(`post-transform marker missing: ${marker}`);
  }

  // The whole point of v4.1: the multiplayer tick expression must remain
  // exactly the site's original code after transformation.
  if ((source.split(onlineInputNeedle).length - 1) !== 1) {
    throw new Error('online input hot path was unexpectedly modified');
  }

  if (source.includes('__GCT4.privateRoom') || source.includes('Online takeover is allowed only in a private room.')) {
    throw new Error('legacy privacy gate unexpectedly remained in patched source');
  }

  return source;
}
