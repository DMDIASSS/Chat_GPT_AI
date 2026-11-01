// Self-contained factory: injected into the game's runtime for tick-level control.
export function createScriptedKickoff() {
  const stages = [
    [44,[1,0,0,0,0,0,1,0]], [16,[1,-1,0,0,0,0,1,0]],
    [8,[1,0,0,0,0,1,1,0]], [4,[1,0,0,0,0,0,1,0]],
    [4,[1,0,-.7,.8,0,1,1,0]], [52,[1,0,1,0,0,0,1,0]],
    [40,[1,0,.5,0,1,0,0,0]],
  ];
  let start=null, latched=false, lastTick=null;
  return {
    reset(){ start=null;latched=false;lastTick=null; },
    step(packet){
      const tick=packet.tick, ball=packet.ball, players=packet.players||[];
      if(!Number.isFinite(tick)||!ball||!players.length)return null;
      if(lastTick!==null && tick<lastTick)this.reset();
      lastTick=tick;
      const p=ball.pos||[], v=ball.vel||[];
      // Car Soccer does not expose RLBot's authoritative kickoff-pause flag.
      const center=Math.hypot(p[0],p[1])<2 && p[2]>60 && p[2]<120 && Math.hypot(...v)<20;
      if(!center){ start=null;latched=false;return null; }
      const self=players[0];
      if(!latched){
        if(!self.onGround || Math.hypot(self.pos[0],self.pos[1])<2000)return null;
        latched=true;
        const distance=p=>Math.hypot(p.pos[0],p.pos[1]);
        const own=distance(self);
        // Closest teammate takes kickoff; ties use the team-relative left side.
        const teammate=players.slice(1).some(p=>p.team===self.team &&
          (distance(p)<own-10 || (Math.abs(distance(p)-own)<=10 &&
            (self.team===0 ? p.pos[0]<self.pos[0] : p.pos[0]>self.pos[0]))));
        if(teammate)return null;
        start=tick;
      }
      if(start===null)return null;
      let elapsed=tick-start;
      if(elapsed<0 || elapsed>=168)return null;
      for(const [duration,action] of stages){
        if(elapsed<duration)return {
          throttle:action[0],steer:action[1],pitch:action[2],yaw:action[3],roll:action[4],
          jump:!!action[5],boost:!!action[6],handbrake:!!action[7],
        };
        elapsed-=duration;
      }
      return null;
    }
  };
}
