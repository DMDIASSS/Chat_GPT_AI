export const BOOST_LOCATIONS = [
  [0,-4240,70],[-1792,-4184,70],[1792,-4184,70],[-3072,-4096,73],[3072,-4096,73],[-940,-3308,70],[940,-3308,70],[0,-2816,70],[-3584,-2484,70],[3584,-2484,70],[-1788,-2300,70],[1788,-2300,70],[-2048,-1036,70],[0,-1024,70],[2048,-1036,70],[-3584,0,73],[-1024,0,70],[1024,0,70],[3584,0,73],[-2048,1036,70],[0,1024,70],[2048,1036,70],[-1788,2300,70],[1788,2300,70],[-3584,2484,70],[3584,2484,70],[0,2816,70],[-940,3310,70],[940,3308,70],[-3072,4096,73],[3072,4096,73],[-1792,4184,70],[1792,4184,70],[0,4240,70]
];

// Nexto's original NextoObsBuilder layout.
const INVERT = [1,1,1,1,1,-1,-1,1,-1,-1,1,-1,-1,1,-1,-1,1,-1,-1,1,1,1,1,1];
const NORM = [1,1,1,1,1,2300,2300,2300,2300,2300,2300,1,1,1,1,1,1,5.5,5.5,5.5,1,1,1,1];
const POS=5, LIN=8, FW=11, UP=14, ANG=17;

function clamp(v,a,b){ return Math.max(a,Math.min(b,v)); }

export class NextoAdapter {
  constructor(){ this.reset(); }
  reset(){ this.padMap=null; }

  #ensurePadMap(pads){
    if(this.padMap && this.padMap.length===34) return;
    const used=new Set();
    const map=new Int16Array(34); map.fill(-1);
    for(let s=0;s<34;s++){
      const [x,y,z]=BOOST_LOCATIONS[s];
      let best=-1,bestD=Infinity;
      for(let i=0;i<pads.length;i++){
        if(used.has(i)) continue;
        const pos=pads[i]?.pos||[0,0,0];
        const dx=(pos[0]??0)-x,dy=(pos[1]??0)-y,dz=(pos[2]??0)-z;
        const d=dx*dx+dy*dy+dz*dz;
        if(d<bestD){bestD=d;best=i;}
      }
      if(best>=0){map[s]=best;used.add(best);}
    }
    this.padMap=map;
  }

  build(packet){
    const players=packet.players||[];
    if(players.length<1) throw new Error('Nexto requires a controlled player.');

    const pads=packet.pads||[];
    this.#ensurePadMap(pads);

    const nPlayers=players.length;
    const nEntities=nPlayers+1+34; // players + ball + all standard RL boost pads
    const kv=new Float32Array(nEntities*24);
    const q=new Float32Array(32);
    const mask=new Float32Array(nEntities); // all rows are real, so no rows are masked
    const row=r=>r*24;

    // Ball entity.
    let o=row(nPlayers);
    kv[o+3]=1;
    const ball=packet.ball||{};
    kv.set(ball.pos||[0,0,0],o+POS);
    kv.set(ball.vel||[0,0,0],o+LIN);
    kv.set(ball.angVel||[0,0,0],o+ANG);

    // Boost entities. Original Nexto's GameState.boost_pads is the pad ACTIVE
    // vector (0/1), despite the old source comment saying "FIXME boost timer".
    // Feed Car Soccer's real active state, not an invented cooldown estimate.
    for(let s=0;s<34;s++){
      o=row(nPlayers+1+s);
      kv[o+4]=1;
      kv.set(BOOST_LOCATIONS[s],o+POS);
      kv[o+20]=BOOST_LOCATIONS[s][2]>72?1:0.12; // full pad vs small pad amount
      const sourceIndex=this.padMap?.[s]??-1;
      const sourcePad=sourceIndex>=0?pads[sourceIndex]:null;
      kv[o+21]=sourcePad?.active?1:0;
    }

    // Players. Caller orders SELF first, then teammates, then opponents.
    for(let i=0;i<nPlayers;i++){
      const p=players[i];
      o=row(i);
      const team=p.team===1?1:0;
      kv[o+1]=1-team;
      kv[o+2]=team;
      if(i===0)kv[o+0]=1;
      kv.set(p.pos||[0,0,0],o+POS);
      kv.set(p.vel||[0,0,0],o+LIN);
      kv.set(p.fwd||[1,0,0],o+FW);
      kv.set(p.up||[0,0,1],o+UP);
      kv.set(p.angVel||[0,0,0],o+ANG);
      kv[o+20]=clamp(Number(p.boost)||0,0,1);
      kv[o+21]=p.demoed?1:0;
      kv[o+22]=p.onGround?1:0;
      kv[o+23]=p.hasFlip?1:0;
    }

    // Original Nexto orange-team inversion: flip x/y-like components and swap
    // teammate/opponent selectors. Pad rows stay in the same ordering.
    const orange=players[0].team===1;
    if(orange){
      for(let r=0;r<nEntities;r++){
        o=row(r);
        for(let j=0;j<24;j++)kv[o+j]*=INVERT[j];
        const mate=kv[o+1];kv[o+1]=kv[o+2];kv[o+2]=mate;
      }
    }

    for(let r=0;r<nEntities;r++){
      o=row(r);
      for(let j=0;j<24;j++)kv[o+j]/=NORM[j];
    }

    // Query starts as the self row, with previous action appended in q[24:32].
    q.set(kv.subarray(0,24),0);
    const prev=packet.previousAction||[0,0,0,0,0,0,0,0];
    for(let i=0;i<8;i++)q[24+i]=Number(prev[i])||0;

    // Exact NextoObsBuilder.convert_to_relative transform.
    const qx=q[POS],qy=q[POS+1],qz=q[POS+2];
    const theta=Math.atan2(q[FW],q[FW+1]);
    const ct=Math.cos(theta),st=Math.sin(theta);
    for(let r=0;r<nEntities;r++){
      o=row(r);
      kv[o+POS]-=qx;kv[o+POS+1]-=qy;kv[o+POS+2]-=qz;
      for(const base of [POS,LIN,FW,UP,ANG]){
        const x=kv[o+base],y=kv[o+base+1];
        kv[o+base]=ct*x-st*y;
        kv[o+base+1]=st*x+ct*y;
      }
    }

    return {q,kv,mask};
  }
}
