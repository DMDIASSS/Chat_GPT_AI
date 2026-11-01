// This factory is embedded in each game's own scope by the patchers. Keep it
// self-contained: files are decoded as binary data, never evaluated as code.
export function createTasPlayer(adapter) {
  const neutral = () => ({throttle:0,steer:0,pitch:0,yaw:0,roll:0,jump:false,boost:false,handbrake:false});
  let clip=null, running=false, frame=0, lastTick=null, message='Upload a TAS .data file.', prepared=false;
  let savedOptions={boost:100,unlimited:false};
  const finite=(x,limit)=>Number.isFinite(x)&&Math.abs(x)<=limit;
  const vector=(view,at,integer=false)=>Array.from({length:3},(_,i)=>integer?view.getInt32(at+i*4,true):view.getFloat32(at+i*4,true));
  function rotation(angles) {
    const [pitch,yaw,roll]=angles.map(n=>n*Math.PI/32768);
    const cp=Math.cos(pitch),sp=Math.sin(pitch),cy=Math.cos(yaw),sy=Math.sin(yaw),cr=Math.cos(roll),sr=Math.sin(roll);
    return [cp*cy,cp*sy,sp,cy*sp*sr-cr*sy,sy*sp*sr+cr*cy,-cp*sr,
      -cr*cy*sp-sr*sy,-cr*sy*sp+sr*cy,cp*cr];
  }
  function decode(buffer,name) {
    if(Object.prototype.toString.call(buffer)!=='[object ArrayBuffer]'||buffer.byteLength<168||buffer.byteLength>16*1024*1024)
      throw Error('Expected a nonempty binary TAS .data file (up to 16 MB).');
    const view=new DataView(buffer),version=view.getUint32(0,true),frames=view.getUint32(4,true);
    if(version!==1||frames<1||frames>450000||buffer.byteLength!==8+frames*32+128)
      throw Error('Unsupported TAS format: expected version 1, 32-byte input frames and a 128-byte state trailer.');
    let extraFlags=false;
    for(let i=0;i<frames;i++) {
      const at=8+i*32,flags=view.getUint32(at,true);
      if(flags>127)throw Error('Unsupported button flags at frame '+i+'.');
      extraFlags ||= !!(flags&96);
      for(let j=0;j<7;j++)if(!finite(view.getFloat32(at+4+j*4,true),1.001))throw Error('Invalid input at frame '+i+'.');
    }
    const trailer=8+frames*32;
    const body=at=>{
      const pos=vector(view,at),angles=vector(view,at+12,true),vel=vector(view,at+24),angVel=vector(view,at+36);
      if(!pos.every(v=>finite(v,100000))||!angles.every(v=>Number.isSafeInteger(v)&&Math.abs(v)<1e7)
        ||!vel.every(v=>finite(v,10000))||!angVel.every(v=>finite(v,100)))throw Error('Invalid TAS starting pose.');
      return {pos,rotation:rotation(angles),vel,angVel};
    };
    // This legacy layout stores UE3 Rotators as signed integers, plus padding
    // bytes beside body flags. Reading the whole trailer as floats yields NaNs.
    return {name:String(name||'TAS').slice(0,160),view,frames,car:body(trailer+12),ball:body(trailer+64),extraFlags};
  }
  const poseArray=body=>[...body.pos,...body.rotation,...body.vel,...body.angVel];
  function validateEnvironment() {
    const env=adapter.environment();
    if(env.online)throw Error('TAS positioning needs local Free Play. Leave the online room first.');
    if(env.mode!=='freeplay'||env.customMap)throw Error('Open standard-arena Free Play before restoring or playing TAS.');
    const sim=env.sim,state=sim?.state;
    if(!sim||typeof sim.captureNetwork!=='function'||typeof sim.restoreNetwork!=='function'||typeof sim.resetKickoff!=='function')
      throw Error('This game build does not expose the supported local state restore API.');
    if(!Number.isInteger(env.slot)||env.slot<0||env.slot>=state[env.fields.NUM_CARS])throw Error('No playable car is available.');
    return env;
  }
  function checkpoint(env) {
    const net=env.sim.captureNetwork(),state=env.sim.state,n=state[env.fields.NUM_CARS];
    if(!(net instanceof Float32Array)||net.length!==126+n*81||n<1||n>6||!net.every(Number.isFinite))
      throw Error('Unsupported physics checkpoint layout; no TAS state was written.');
    // Confirm the native wire layout against actual observable poses before
    // editing it. Never write into the read-only rendered state buffer.
    for(let slot=-1;slot<n;slot++) {
      const a=slot<0?3:21+slot*81,b=slot<0?env.fields.BALL:env.fields.CARS+slot*env.stride;
      for(let j=0;j<18;j++)if(Math.abs(net[a+j]-state[b+j])>.03)
        throw Error('Physics checkpoint pose layout differs from this adapter.');
    }
    return net.slice();
  }
  function options(value={}) {
    const boost=Number(value.boost??100);
    if(!Number.isFinite(boost)||boost<0||boost>100||typeof(value.unlimited??false)!=='boolean')throw Error('Invalid TAS boost setting.');
    return {boost,unlimited:value.unlimited??false};
  }
  function prepare(value) {
    if(!clip)throw Error('Upload a TAS .data file first.');
    running=false;prepared=false;frame=0;lastTick=null;
    const settings=options(value),env=validateEnvironment(),before=checkpoint(env);
    try {
      env.sim.resetKickoff();
      const net=checkpoint(env),at=21+env.slot*81;
      net.set(poseArray(clip.ball),3);net.set(poseArray(clip.car),at);
      // Ground starts are supported; missing jump/boost metadata is not guessed
      // from pointer/padding bytes in the legacy trailer.
      const grounded=clip.car.pos[2]<65&&clip.car.rotation[8]>.65;
      net[at+18]=grounded?1:0;
      net[at+19]=net[at+20]=net[at+21]=net[at+22]=grounded?1:0;
      net[at+35]=settings.boost;
      net[2]=settings.unlimited?1:0;
      env.sim.restoreNetwork(net);
      env.sim.setUnlimitedBoost(settings.unlimited);
      for(let i=0;i<env.sim.state[env.fields.NUM_CARS];i++)env.sim.setControls(i,neutral());
      env.sim.pollGoal?.();env.sim.resetView?.();adapter.discontinuity?.();
      // Check that this writes native bodies, rather than a transient snapshot.
      const after=checkpoint(env);
      for(const [base,body] of [[3,clip.ball],[at,clip.car]]) {
        const expected=poseArray(body);
        for(let j=0;j<18;j++)if(Math.abs(after[base+j]-expected[j])>.05)throw Error('The game did not accept the TAS starting state.');
      }
      savedOptions=settings;prepared=true;
      message='Starting car and ball poses/velocities restored. Play always restores again.';
    } catch(error) {
      try{env.sim.restoreNetwork(before);env.sim.resetView?.()}catch{}
      throw error;
    }
  }
  const api={
    load(buffer,name) {
      api.stop();clip=null;prepared=false;frame=0;
      clip=decode(buffer,name);
      message='Loaded '+clip.name+' ('+(clip.frames/120).toFixed(2)+' s at 120 Hz).';
      return api.snapshot();
    },
    prepare,
    play(value) { prepare(value);running=true;lastTick=null;message='Playing recorded inputs.'; },
    stop(reason='TAS stopped.') { running=false;lastTick=null;message=reason; },
    guard() { if(running)validateEnvironment(); },
    step(tick) {
      if(!running)return null;
      validateEnvironment();
      if(!Number.isInteger(tick)||tick<0)throw Error('Invalid simulation tick.');
      if(lastTick!==null) {
        if(tick===lastTick)return api.controls(frame);
        if(tick!==lastTick+1)throw Error('Simulation reset or skipped ticks. TAS stopped; Play restarts from the saved pose.');
        frame++;
      }
      lastTick=tick;
      if(frame>=clip.frames){api.stop('TAS finished. Player control restored.');return null;}
      adapter.environment().sim.setUnlimitedBoost(savedOptions.unlimited);
      return api.controls(frame);
    },
    controls(index) {
      if(!clip||!Number.isInteger(index)||index<0||index>=clip.frames)throw Error('TAS frame outside recording.');
      const at=8+index*32,flags=clip.view.getUint32(at,true),f=i=>Math.max(-1,Math.min(1,clip.view.getFloat32(at+4+i*4,true)));
      // BakkesMod ControllerInput: throttle/steer/pitch/yaw/roll,
      // DodgeForward/DodgeStrafe; Handbrake=1, Jump=2, boost=4|8.
      // Jumped=16 is history. Upper two flags have no mapped car action.
      return {throttle:f(0),steer:f(1),pitch:f(2),yaw:f(3),roll:f(4),
        jump:!!(flags&2),boost:!!(flags&12),handbrake:!!(flags&1)};
    },
    snapshot() { return {loaded:!!clip,running,prepared,name:clip?.name||'',frames:clip?.frames||0,
      frame,seconds:clip?clip.frames/120:0,car:clip?.car.pos||null,ball:clip?.ball.pos||null,
      extraFlags:clip?.extraFlags||false,message}; },
  };
  return api;
}
