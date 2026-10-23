// Optional host cooperation, carried over the game's existing reliable chat
// envelope. Both extensions consume these frames before ordinary chat; no
// server, external service, input-packet change or authority bypass is needed.
export function createCooperativeFunControls(factory,adapter) {
  const prefix='~gctf1~',effects=['glue','boost','jumps','speed'],actions=['recall','launch','goal'];
  const clock=adapter.now||(()=>performance.now());
  let binding=null,allowFriends=false,target=null,visitor=null,sequence=0;
  let nonce=1+Math.floor(Math.random()*1e9),remoteMask=0,remoteSpeed=6000,connected=false;
  let lastReply=0,lastSent=-Infinity,waiting=false,remoteMessage='Your friend must install this update and enable Allow friend controls.';
  const local=factory({environment:()=>{
    const env=adapter.environment();
    // Mirror acknowledged host effects in the joining player's prediction.
    // The real host still applies/replicates them; this avoids overspeed
    // prediction repeatedly falling back to the ordinary speed limit.
    if(env.online&&!env.host&&connected&&env.session===binding?.session)return {...env,host:true};
    if(target===null||!env.host||env.session!==binding?.session)return env;
    const slot=env.session.carSeats.indexOf(target);
    return {...env,slot,team:env.session.carTeams[slot],spectator:slot<0};
  }});
  const mask=()=>{const state=local.snapshot();return effects.reduce((v,key,i)=>v|(state[key]?1<<i:0),0);};
  function release(reason) { local.stop(reason);target=null;visitor=null; }
  function attach() {
    const env=adapter.environment(),session=env.online?env.session:null;
    if(session===binding?.session)return env;
    if(binding) {
      const old=binding;binding=null;
      if(old.session.command===old.wrapped)old.session.command=old.original;
      release('Room changed.');allowFriends=false;remoteMask=0;connected=false;waiting=false;
      nonce=1+Math.floor(Math.random()*1e9);sequence=0;
    }
    if(session&&typeof session.command==='function'&&typeof session.peer?.control==='function') {
      const original=session.command,record={session,original,wrapped:null};
      record.wrapped=function(message,seat) {
        if(typeof message?.text==='string'&&message.text.startsWith(prefix)) {
          let frame;try{frame=JSON.parse(message.text.slice(prefix.length));}catch{}
          if(Array.isArray(frame)&&frame.length===7&&frame.every(Number.isSafeInteger)) {
            if(session.peer.host&&message.type==='chat'&&frame[0]===1) {receiveRequest(session,seat,frame);return;}
            if(!session.peer.host&&seat===0&&message.type==='chat-line'&&frame[0]===2) {receiveReply(session,frame);return;}
          }
        }
        return original.apply(this,arguments);
      };
      binding=record;session.command=record.wrapped;
    }
    return env;
  }
  function transmit(operation,value=0) {
    const env=attach(),session=env.session;
    if(!env.online||env.host||binding?.session!==session)throw Error('This room has no supported friend connection.');
    const id=++sequence;lastSent=clock();
    if(!connected&&!waiting)lastReply=clock();waiting=true;
    const text=prefix+JSON.stringify([1,nonce,id,operation,value,remoteSpeed,session.epoch]);
    if(session.peer.control({type:'chat',text})===false) {
      local.stop();remoteMask=0;connected=false;waiting=false;throw Error('Host connection is unavailable.');
    }
  }
  function reply(session,seat,frame,status) {
    const text=prefix+JSON.stringify([2,frame[1],frame[2],status,target===seat?mask():0,
      target===seat?local.snapshot().speedLimit:frame[5],session.epoch]);
    session.peer.control({type:'chat-line',slot:0,id:1,name:'Trainer',text},seat);
  }
  function receiveRequest(session,seat,frame) {
    if(!Number.isInteger(seat)||seat<1||seat>7||!(session.members&1<<seat))return;
    if(!allowFriends){reply(session,seat,frame,1);return;}
    if(frame[6]!==session.epoch){reply(session,seat,frame,4);return;}
    const slot=session.carSeats.indexOf(seat),[,,id,operation,value,speed]=frame;
    if(slot<0||session.teams[seat]<0){reply(session,seat,frame,3);return;}
    if(id<1||id>1e7||operation<0||operation>4||value<0||value>15||speed<2300||speed>10000) {
      reply(session,seat,frame,2);return;
    }
    if(target!==null&&target!==seat){reply(session,seat,frame,5);return;}
    if(visitor&&visitor.nonce===frame[1]&&id<=visitor.id){reply(session,seat,frame,0);return;}
    if(target===seat&&visitor?.nonce!==frame[1])release('Friend reconnected.');
    if(operation===0) {
      if(visitor)Object.assign(visitor,{last:clock(),id});
      reply(session,seat,frame,0);return;
    }
    if(operation===4||operation===1&&value===0) {
      if(target===seat)release('Friend turned fun controls off.');
      reply(session,seat,frame,0);return;
    }
    if(operation===3&&!actions[value]){reply(session,seat,frame,2);return;}
    try {
      if(target===null){local.stop();target=seat;}
      visitor={nonce:frame[1],id,last:clock()};
      adapter.onRemoteStart?.();local.setSpeed(speed);
      if(operation===1) {
        const current=mask();
        effects.forEach((key,i)=>{if((current^value)&1<<i)local.toggle(key);});
      }else if(operation===3)local.action(actions[value]);
      reply(session,seat,frame,0);
      if(!local.snapshot().enabled){target=null;visitor=null;}
    }catch {release('Friend effect stopped after a state change.');reply(session,seat,frame,2);}
  }
  function receiveReply(session,frame) {
    if(frame[1]!==nonce||frame[2]!==sequence||frame[6]!==session.epoch)return;
    const status=frame[3];
    if(status<0||status>5||frame[4]<0||frame[4]>15||frame[5]<2300||frame[5]>10000)return;
    lastReply=clock();waiting=false;connected=status===0;remoteMask=connected?frame[4]:0;
    if(connected)remoteSpeed=frame[5];
    remoteMessage=['Host connected. Effects run on your car through your friend’s host.',
      'Your friend needs this update and must enable Allow friend controls.',
      'The host could not apply that effect. Wait for active play and try again.',
      'Join a team before using friend controls.',
      'Round changed. Try the control again.',
      'Another player is using friend controls. They must stop first.'][status];
    try {
      if(!remoteMask)local.stop();
      else {
        local.setSpeed(remoteSpeed);const current=mask();
        effects.forEach((key,i)=>{if((current^remoteMask)&1<<i)local.toggle(key);});
      }
    }catch {
      local.stop();remoteMask=0;connected=false;
      remoteMessage='Local prediction changed. Stop and reconnect to host.';
      try{transmit(4);}catch{}
    }
  }
  function localControl() {
    const env=attach();
    if(env.online&&!env.host&&binding?.session===env.session)return false;
    if(target!==null)release('Host took back fun controls.');
    return true;
  }
  const api={
    toggle(name) {
      const index=effects.indexOf(name);if(index<0)throw Error('Unknown fun effect.');
      if(localControl())return local.toggle(name);
      remoteMask^=1<<index;remoteMessage='Waiting for host…';transmit(1,remoteMask);
    },
    action(name) {
      const index=actions.indexOf(name);if(index<0)throw Error('Unknown ball action.');
      if(localControl())return local.action(name);
      remoteMessage='Waiting for host…';transmit(3,index);
    },
    setSpeed(value) {
      if(!Number.isFinite(value)||value<2300||value>10000)throw Error('Choose a speed limit from 2300 to 10000.');
      if(localControl())return local.setSpeed(value);
      remoteSpeed=Math.round(value);if(connected)transmit(2);
    },
    connect() {attach();remoteMessage='Connecting to friend’s host…';transmit(0);},
    setAllowFriends(value) {
      const env=attach();if(!env.online||!env.host||!binding)throw Error('Only the room host can allow friend controls.');
      allowFriends=!!value;if(!allowFriends&&target!==null)release('Host disabled friend controls.');
    },
    stop(reason='Fun controls off.') {
      let env;try{env=attach();}catch{} // Stopping also works before an arena exists.
      if(env?.online&&!env.host&&binding&&(connected||remoteMask)) {
        remoteMask=0;try{transmit(4);}catch{}
      }
      release(reason);allowFriends=false;remoteMask=0;waiting=false;remoteMessage=reason;
    },
    guard() {
      let env;try{env=attach();}catch{local.guard();return;}local.guard();
      if(target!==null&&(!allowFriends||!visitor||clock()-visitor.last>4000||
          !env.session?.carSeats.includes(target)||!(env.session.members&1<<target)))release('Friend disconnected or stopped sending controls.');
      if(env.online&&!env.host&&binding&&(connected||remoteMask||waiting)) {
        if(clock()-lastReply>4000) {
          local.stop();sequence++; // A delayed pre-timeout reply cannot resume effects.
          remoteMask=0;connected=false;waiting=false;remoteMessage='Host stopped replying. Reconnect to host.';
        }else if(connected&&clock()-lastSent>=1000)try{transmit(0);}catch(error){remoteMessage=error.message;}
      }
    },
    snapshot() {
      let env;try{env=attach();}catch{return {...local.snapshot(),joined:false,hosting:false,allowFriends:false};}
      const state=local.snapshot(),joined=env.online&&!env.host&&!!binding;
      if(joined) {
        const playable=!env.spectator&&Number.isInteger(env.slot)&&env.slot>=0;
        return {...state,available:playable,reason:playable?'':'Join a team before using friend controls.',
          scope:'friend-hosted room',enabled:!!remoteMask,...Object.fromEntries(effects.map((key,i)=>[key,!!(remoteMask&1<<i)])),
          speedLimit:remoteSpeed,message:remoteMessage,error:'',joined:true,connected,hosting:false,allowFriends:false};
      }
      return {...state,joined:false,hosting:!!(env.online&&env.host&&binding),allowFriends,
        message:target===null?state.message:`Friend controls: ${env.session.names?.[target]||'player '+target}. ${state.message}`};
    }
  };
  return api;
}
