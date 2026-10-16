// Embedded only by the Car Soccer patcher. Operates on local/host native
// checkpoints; it never forges network messages or edits rendered snapshots.
export function createFunControls(adapter) {
  const flags={glue:false,boost:false,jumps:false,speed:false};
  let speedLimit=6000,lease=null,previousJump=false,message='Free Play or a room you host.',failure='';
  const length=v=>Math.hypot(...v);
  const read3=(net,at)=>[net[at],net[at+1],net[at+2]];
  const write3=(net,at,v)=>net.set(v,at);
  const bounded=(v,max)=>{const n=length(v);return n>max?v.map(x=>x*max/n):v;};
  const enabled=()=>Object.values(flags).some(Boolean);
  function context() {
    const env=adapter.environment(),sim=env.sim,state=sim?.state;
    if(env.online&&!env.host)throw Error('Host the room to change its physics. A joined client cannot apply these effects.');
    if(env.spectator)throw Error('Join Blue or Orange first.');
    if(env.customMap)throw Error('Fun controls currently use the standard soccer arena.');
    if(!sim||typeof sim.captureNetwork!=='function'||typeof sim.restoreNetwork!=='function'||typeof sim.step!=='function')
      throw Error('This game build has no supported native state controls.');
    if(!Number.isInteger(env.slot)||env.slot<0||env.slot>=state[env.fields.NUM_CARS]||![0,1].includes(env.team))
      throw Error('No playable car is available.');
    return env;
  }
  function playing(env) { return !env.online&&env.mode==='freeplay'||env.phase==='playing'; }
  function capture(env) {
    const net=env.sim.captureNetwork(),state=env.sim.state,count=state[env.fields.NUM_CARS];
    if(!(net instanceof Float32Array)||count<1||count>6||net.length!==126+count*81||!net.every(Number.isFinite))
      throw Error('Unsupported native checkpoint layout.');
    for(let slot=-1;slot<count;slot++) {
      const a=slot<0?3:21+slot*81,b=slot<0?env.fields.BALL:env.fields.CARS+slot*env.stride;
      for(let i=0;i<18;i++)if(Math.abs(net[a+i]-state[b+i])>.03)throw Error('Native pose layout changed.');
    }
    return net.slice();
  }
  function commit(env,before,after) {
    if(!after.every(n=>Number.isFinite(n)&&Math.abs(n)<=1e7))throw Error('Non-finite/out-of-range fun state rejected.');
    try{env.sim.restoreNetwork(after);}catch(error){try{env.sim.restoreNetwork(before);}catch{}throw error;}
  }
  function inputs(env) {
    let values=env.sim.controlsView;
    if(!values&&env.sim.module) {
      const mod=env.sim.module,ptr=env.sim.controlsPtr??mod._physics_getControlsPtr?.();
      if(ptr)values=new Float32Array(mod.HEAPF32.buffer,ptr,(env.slot+1)*8);
    }
    if(!values||values.length<(env.slot+1)*8)throw Error('Native player inputs are unavailable.');
    const controls=Array.from(values.subarray(env.slot*8,env.slot*8+8));
    if(!controls.every(n=>Number.isFinite(n)&&Math.abs(n)<=1.001))throw Error('Invalid native player inputs.');
    return controls;
  }
  function glue(net,env) {
    const at=21+env.slot*81,pos=read3(net,at),forward=read3(net,at+3),up=read3(net,at+9);
    const radius=Number(env.sim.ballRadius)||91.25;
    const offset=forward.map((x,i)=>x*90+up[i]*(radius+22));
    const omega=read3(net,at+15),vel=read3(net,at+12);
    const spin=[omega[1]*offset[2]-omega[2]*offset[1],omega[2]*offset[0]-omega[0]*offset[2],omega[0]*offset[1]-omega[1]*offset[0]];
    write3(net,3,pos.map((x,i)=>x+offset[i]));
    write3(net,15,bounded(vel.map((x,i)=>x+spin[i]),6000));
    write3(net,18,omega);
  }
  function before(env) {
    if(!playing(env)){previousJump=false;return null;}
    const original=capture(env),net=original.slice(),at=21+env.slot*81;
    if(net[at+51]){previousJump=false;return null;} // Demoed; wait for respawn.
    const control=inputs(env),jump=!!control[5];
    if(flags.jumps&&jump&&!previousJump) {
      // Preserve true wheel contact. Re-arm a fresh air jump/flip on each
      // actual button edge, rather than pretending the car is grounded.
      for(let i=23;i<=34;i++)net[at+i]=0;
      net[at+58]=0; // Native lastControls.jump, not the currently held input.
    }
    previousJump=jump;
    if(flags.boost)net[at+35]=100;
    if(flags.speed) {
      const forward=read3(net,at+3),vel=read3(net,at+12),accel=control[0]*500+(control[6]?1000:0);
      const adjusted=bounded(vel.map((x,i)=>x+forward[i]*accel/120),speedLimit);
      write3(net,at+12,adjusted);
    }
    if(flags.glue)glue(net,env);
    commit(env,original,net);
    return {velocity:read3(net,at+12)};
  }
  function after(env,pre) {
    if(!pre||!(flags.glue||flags.boost||flags.speed))return;
    const original=capture(env),net=original.slice(),at=21+env.slot*81;
    if(flags.speed&&!net[at+51]) {
      const vel=read3(net,at+12),n=length(vel),old=length(pre.velocity);
      // RocketSim clamps in FinishPhysicsTick, after integration. Restore
      // overspeed for the NEXT integration, preserving the collision direction.
      // A collision/brake that reduces speed below the native cap is respected.
      if(n>=2299&&old>2300)write3(net,at+12,vel.map(x=>x*Math.min(old,speedLimit)/n));
    }
    if(flags.boost&&!net[at+51])net[at+35]=100;
    if(flags.glue&&!net[at+51])glue(net,env);
    commit(env,original,net);
  }
  function currentLease(env) {
    return lease&&env.sim===lease.sim&&env.session===lease.session&&env.slot===lease.slot;
  }
  function bind(env) {
    if(lease){if(!currentLease(env))throw Error('The controlled car/session changed. Enable fun controls again.');return;}
    capture(env);inputs(env);
    const original=env.sim.step;
    const binding={sim:env.sim,session:env.session,slot:env.slot,original,wrapped:null};
    binding.wrapped=function(...args) {
      if(!enabled())return original.apply(this,args);
      const steps=args[0]??1;
      if(!Number.isInteger(steps)||steps<0||steps>120){api.stop('Unsupported physics batch.');return original.apply(this,args);}
      let result;
      for(let i=0;i<steps;i++) {
        if(!enabled()){result=original.call(this,1);continue;}
        let env,pre;
        try {
          env=context();if(!currentLease(env))throw Error('The controlled car/session changed.');
          pre=before(env);
        }catch(error){api.stop(error.message||String(error));failure=message;}
        result=original.call(this,1);
        if(enabled()&&env)try{after(env,pre);}catch(error){api.stop(error.message||String(error));failure=message;}
      }
      return result;
    };
    lease=binding;env.sim.step=binding.wrapped;
  }
  const api={
    toggle(name) {
      if(!Object.hasOwn(flags,name))throw Error('Unknown fun effect.');
      const env=context();bind(env);failure='';flags[name]=!flags[name];
      if(name==='jumps')previousJump=!!inputs(env)[5];
      message=name+' '+(flags[name]?'ON':'OFF');
      if(!enabled())api.stop('Fun controls off.');
    },
    setSpeed(value) {
      if(!Number.isFinite(value)||value<2300||value>10000)throw Error('Choose a speed limit from 2300 to 10000.');
      speedLimit=Math.round(value);message='Speed override: '+speedLimit+' units/s.';
    },
    action(name) {
      if(!['recall','launch','goal'].includes(name))throw Error('Unknown ball action.');
      const env=context();if(!playing(env))throw Error('Wait until the round starts.');
      const original=capture(env),net=original.slice();failure='';
      if(name==='recall'){glue(net,env);message='Ball brought to your hood.';}
      else {
        const sign=env.team===0?1:-1;
        if(name==='goal') {
          write3(net,3,[0,sign*5500,(Number(env.sim.ballRadius)||91.25)+30]);
          write3(net,15,[0,0,0]);message='Ball teleported inside the opponent goal.';
        }else {
          const pos=read3(net,3),dx=-pos[0],dy=sign*5400-pos[1],time=Math.max(.08,Math.hypot(dx,dy)/5400);
          write3(net,15,bounded([dx/time,dy/time,(250-pos[2]+325*time*time)/time],6000));
          message='Ball launched toward the opponent goal.';
        }
        write3(net,18,[0,0,0]);
      }
      commit(env,original,net);flags.glue=false;env.sim.resetView?.();
      if(!enabled())api.stop(message);
    },
    stop(reason='Fun controls off.') {
      for(const name of Object.keys(flags))flags[name]=false;
      const old=lease;lease=null;previousJump=false;message=reason;failure='';
      // Never overwrite a newer wrapper installed by another component.
      if(old&&old.sim.step===old.wrapped)old.sim.step=old.original;
    },
    guard() {
      if(!enabled())return;
      try{if(!currentLease(context()))throw Error('The controlled car/session changed.');}
      catch(error){api.stop(error.message||String(error));failure=message;}
    },
    snapshot() {
      let available=false,reason='',scope='unavailable',speed=0;
      try {
        const env=context();available=true;scope=env.online?'room host':'local play';
        const at=env.fields.CARS+env.slot*env.stride+12;speed=length(read3(env.sim.state,at));
      }catch(error){reason=error.message||String(error);}
      return {available,reason,scope,enabled:enabled(),...flags,speedLimit,currentSpeed:speed,message,error:failure};
    }
  };
  return api;
}
