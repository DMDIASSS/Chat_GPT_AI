const LAYOUT={"q1w":[0,4096],"q1b":[4096,128],"q2w":[4224,16384],"q2b":[20608,128],"k1w":[20736,3072],"k1b":[23808,128],"k2w":[23936,16384],"k2b":[40320,128],"b0iw":[40448,49152],"b0ib":[89600,384],"b0ow":[89984,16384],"b0ob":[106368,128],"b0f1w":[106496,65536],"b0f1b":[172032,512],"b0f2w":[172544,65536],"b0f2b":[238080,128],"b0n1w":[238208,128],"b0n1b":[238336,128],"b0n2w":[238464,128],"b0n2b":[238592,128],"b0n3w":[238720,128],"b0n3b":[238848,128],"b1iw":[238976,49152],"b1ib":[288128,384],"b1ow":[288512,16384],"b1ob":[304896,128],"b1f1w":[305024,65536],"b1f1b":[370560,512],"b1f2w":[371072,65536],"b1f2b":[436608,128],"b1n1w":[436736,128],"b1n1b":[436864,128],"b1n2w":[436992,128],"b1n2b":[437120,128],"b1n3w":[437248,128],"b1n3b":[437376,128],"a1w":[437504,256],"a1b":[437760,32],"a2w":[437792,1024],"a2b":[438816,32],"a3w":[438848,1024],"a3b":[439872,32],"ecw":[439904,4096],"ecb":[444000,32]};

const SQRT_HEAD = Math.sqrt(32);
const HEADS = 4;
const D = 128;
const HD = 32;
const EPS = 1e-5;

function reluInPlace(a) {
  for (let i = 0; i < a.length; i++) if (a[i] < 0) a[i] = 0;
  return a;
}

function linearVec(x, w, b, outDim, inDim, wOff = 0, bOff = 0) {
  const out = new Float32Array(outDim);
  for (let o = 0; o < outDim; o++) {
    let sum = b ? b[bOff + o] : 0;
    let wi = wOff + o * inDim;
    let i = 0;
    // Unroll a little for V8.
    for (; i + 3 < inDim; i += 4) {
      sum += w[wi + i] * x[i] + w[wi + i + 1] * x[i + 1] + w[wi + i + 2] * x[i + 2] + w[wi + i + 3] * x[i + 3];
    }
    for (; i < inDim; i++) sum += w[wi + i] * x[i];
    out[o] = sum;
  }
  return out;
}

function linearRows(x, rows, inDim, w, b, outDim, wOff = 0, bOff = 0) {
  const out = new Float32Array(rows * outDim);
  for (let r = 0; r < rows; r++) {
    const xOff = r * inDim;
    const yOff = r * outDim;
    for (let o = 0; o < outDim; o++) {
      let sum = b ? b[bOff + o] : 0;
      let wi = wOff + o * inDim;
      let i = 0;
      for (; i + 3 < inDim; i += 4) {
        sum += w[wi + i] * x[xOff + i] + w[wi + i + 1] * x[xOff + i + 1] + w[wi + i + 2] * x[xOff + i + 2] + w[wi + i + 3] * x[xOff + i + 3];
      }
      for (; i < inDim; i++) sum += w[wi + i] * x[xOff + i];
      out[yOff + o] = sum;
    }
  }
  return out;
}

function layerNormVec(x, gamma, beta) {
  const n = x.length;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += x[i];
  mean /= n;
  let variance = 0;
  for (let i = 0; i < n; i++) {
    const d = x[i] - mean;
    variance += d * d;
  }
  variance /= n;
  const inv = 1 / Math.sqrt(variance + EPS);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = (x[i] - mean) * inv * gamma[i] + beta[i];
  return out;
}

function layerNormRows(x, rows, cols, gamma, beta) {
  const out = new Float32Array(x.length);
  for (let r = 0; r < rows; r++) {
    const off = r * cols;
    let mean = 0;
    for (let i = 0; i < cols; i++) mean += x[off + i];
    mean /= cols;
    let variance = 0;
    for (let i = 0; i < cols; i++) {
      const d = x[off + i] - mean;
      variance += d * d;
    }
    variance /= cols;
    const inv = 1 / Math.sqrt(variance + EPS);
    for (let i = 0; i < cols; i++) out[off + i] = (x[off + i] - mean) * inv * gamma[i] + beta[i];
  }
  return out;
}

function addVec(a, b) {
  const out = new Float32Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] + b[i];
  return out;
}

function makeLookupTable() {
  const actions = [];
  for (const throttle of [-1, 0, 1]) {
    for (const steer of [-1, 0, 1]) {
      for (const boost of [0, 1]) {
        for (const handbrake of [0, 1]) {
          if (boost === 1 && throttle !== 1) continue;
          actions.push([throttle || boost, steer, 0, steer, 0, 0, boost, handbrake]);
        }
      }
    }
  }
  for (const pitch of [-1, 0, 1]) {
    for (const yaw of [-1, 0, 1]) {
      for (const roll of [-1, 0, 1]) {
        for (const jump of [0, 1]) {
          for (const boost of [0, 1]) {
            if (jump === 1 && yaw !== 0) continue;
            if (pitch === 0 && roll === 0 && jump === 0) continue;
            const handbrake = jump === 1 && (pitch !== 0 || yaw !== 0 || roll !== 0) ? 1 : 0;
            actions.push([boost, yaw, pitch, yaw, roll, jump, boost, handbrake]);
          }
        }
      }
    }
  }
  return actions;
}

class NextoEngine {
  constructor(arrayBuffer) {
    if (!(arrayBuffer instanceof ArrayBuffer)) throw new Error('Nexto weights must be an ArrayBuffer.');
    if (arrayBuffer.byteLength !== 444032 * 4) throw new Error("Incompatible Nexto weights: expected 1,776,128 bytes.");
    this.all = new Float32Array(arrayBuffer);
    if (!this.all.every(Number.isFinite)) throw new Error("Model contains nonfinite weights.");
    this.t = {};
    for (const [name, [off, len]] of Object.entries(LAYOUT)) this.t[name] = this.all.subarray(off, off + len);
    this.actions = makeLookupTable();
    if (this.actions.length !== 90) throw new Error(`Nexto action table mismatch: ${this.actions.length}`);
    this.actionEmb = this.#buildActionEmbeddings();
  }

  #buildActionEmbeddings() {
    const t = this.t;
    const out = new Float32Array(90 * 32);
    for (let a = 0; a < 90; a++) {
      const x = Float32Array.from(this.actions[a]);
      const h1 = reluInPlace(linearVec(x, t.a1w, t.a1b, 32, 8));
      const h2 = reluInPlace(linearVec(h1, t.a2w, t.a2b, 32, 32));
      const h3 = reluInPlace(linearVec(h2, t.a3w, t.a3b, 32, 32));
      out.set(h3, a * 32);
    }
    return out;
  }

  #block(q, kv, rows, index, mask = null) {
    const t = this.t;
    const p = `b${index}`;
    const qn = layerNormVec(q, t[`${p}n1w`], t[`${p}n1b`]);
    const kvn = layerNormRows(kv, rows, D, t[`${p}n2w`], t[`${p}n2b`]);
    const iw = t[`${p}iw`], ib = t[`${p}ib`];
    const qwOff = 0;
    const kwOff = D * D;
    const vwOff = 2 * D * D;
    const qbOff = 0, kbOff = D, vbOff = 2 * D;
    const qProj = linearVec(qn, iw, ib, D, D, qwOff, qbOff);
    const kProj = linearRows(kvn, rows, D, iw, ib, D, kwOff, kbOff);
    const vProj = linearRows(kvn, rows, D, iw, ib, D, vwOff, vbOff);

    const attnConcat = new Float32Array(D);
    const scores = new Float64Array(rows);
    for (let h = 0; h < HEADS; h++) {
      const ho = h * HD;
      let max = -Infinity;
      for (let r = 0; r < rows; r++) {
        const ro = r * D + ho;
        let dot = 0;
        for (let j = 0; j < HD; j++) dot += qProj[ho + j] * kProj[ro + j];
        let s = dot / SQRT_HEAD;
        if (mask && mask[r]) s += mask[r];
        scores[r] = s;
        if (s > max) max = s;
      }
      let denom = 0;
      for (let r = 0; r < rows; r++) {
        const e = Math.exp(scores[r] - max);
        scores[r] = e;
        denom += e;
      }
      if (!(denom > 0)) denom = 1;
      for (let j = 0; j < HD; j++) {
        let sum = 0;
        for (let r = 0; r < rows; r++) sum += (scores[r] / denom) * vProj[r * D + ho + j];
        attnConcat[ho + j] = sum;
      }
    }
    const attnOut = linearVec(attnConcat, t[`${p}ow`], t[`${p}ob`], D, D);
    const residual = addVec(q, attnOut);
    const n3 = layerNormVec(residual, t[`${p}n3w`], t[`${p}n3b`]);
    const ff1 = reluInPlace(linearVec(n3, t[`${p}f1w`], t[`${p}f1b`], 512, D));
    const ff2 = linearVec(ff1, t[`${p}f2w`], t[`${p}f2b`], D, 512);
    return addVec(residual, ff2);
  }

  infer(qInput, kvInput, maskInput = null, returnLogits = false) {
    const q0 = qInput instanceof Float32Array ? qInput : Float32Array.from(qInput);
    const kv0 = kvInput instanceof Float32Array ? kvInput : Float32Array.from(kvInput);
    if (q0.length !== 32) throw new Error(`Nexto q must have 32 values, got ${q0.length}`);
    if (kv0.length % 24 !== 0) throw new Error(`Nexto kv length must be divisible by 24, got ${kv0.length}`);
    const rows = kv0.length / 24;
    const mask = maskInput ? (maskInput instanceof Float32Array ? maskInput : Float32Array.from(maskInput)) : null;
    if (mask && mask.length !== rows) throw new Error('Nexto mask length mismatch.');
    const t = this.t;
    let q = reluInPlace(linearVec(q0, t.q1w, t.q1b, 128, 32));
    q = reluInPlace(linearVec(q, t.q2w, t.q2b, 128, 128));
    let kv = linearRows(kv0, rows, 24, t.k1w, t.k1b, 128);
    reluInPlace(kv);
    kv = linearRows(kv, rows, 128, t.k2w, t.k2b, 128);
    reluInPlace(kv);
    q = this.#block(q, kv, rows, 0, mask);
    q = this.#block(q, kv, rows, 1, mask);
    reluInPlace(q);
    const emb = linearVec(q, t.ecw, t.ecb, 32, 128);
    const logits = new Float32Array(90);
    let best = 0, bestValue = -Infinity;
    for (let a = 0; a < 90; a++) {
      let sum = 0;
      const off = a * 32;
      for (let j = 0; j < 32; j++) sum += this.actionEmb[off + j] * emb[j];
      logits[a] = sum;
      if (sum > bestValue) { bestValue = sum; best = a; }
    }
    const action = this.actions[best];
    const result = {
      index: best,
      controls: {
        throttle: action[0], steer: action[1], pitch: action[2], yaw: action[3], roll: action[4],
        jump: action[5] > 0, boost: action[6] > 0, handbrake: action[7] > 0,
      },
    };
    if (returnLogits) result.logits = logits;
    return result;
  }
}

const BOOST_LOCATIONS = [
  [0,-4240,70],[-1792,-4184,70],[1792,-4184,70],[-3072,-4096,73],[3072,-4096,73],[-940,-3308,70],[940,-3308,70],[0,-2816,70],[-3584,-2484,70],[3584,-2484,70],[-1788,-2300,70],[1788,-2300,70],[-2048,-1036,70],[0,-1024,70],[2048,-1036,70],[-3584,0,73],[-1024,0,70],[1024,0,70],[3584,0,73],[-2048,1036,70],[0,1024,70],[2048,1036,70],[-1788,2300,70],[1788,2300,70],[-3584,2484,70],[3584,2484,70],[0,2816,70],[-940,3310,70],[940,3308,70],[-3072,4096,73],[3072,4096,73],[-1792,4184,70],[1792,4184,70],[0,4240,70]
];

// Nexto's original NextoObsBuilder layout.
const INVERT = [1,1,1,1,1,-1,-1,1,-1,-1,1,-1,-1,1,-1,-1,1,-1,-1,1,1,1,1,1];
const NORM = [1,1,1,1,1,2300,2300,2300,2300,2300,2300,1,1,1,1,1,1,5.5,5.5,5.5,1,1,1,1];
const POS=5, LIN=8, FW=11, UP=14, ANG=17;

function clamp(v,a,b){ return Math.max(a,Math.min(b,v)); }

class NextoAdapter {
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


let engine = null;
let adapter = new NextoAdapter();

self.onmessage = event => {
  const msg = event.data || {};
  try {
    if (msg.kind === 'init') {
      engine = new NextoEngine(msg.weights);
      adapter.reset();
      self.postMessage({ kind: 'ready' });
      return;
    }
    if (msg.kind === 'reset') {
      adapter.reset();
      self.postMessage({ kind: 'reset-done', generation: msg.generation });
      return;
    }
    if (msg.kind === 'infer') {
      if (!engine) throw new Error('Nexto model is not initialized.');
      const started = performance.now();
      const obs = adapter.build(msg.packet);
      const result = engine.infer(obs.q, obs.kv, obs.mask, false);
      self.postMessage({
        kind: 'result',
        requestId: msg.requestId,
        generation: msg.generation,
        controls: result.controls,
        actionIndex: result.index,
        observedBoost: msg.packet?.players?.[0]?.boost ?? null,
        latencyMs: performance.now() - started,
      });
      return;
    }
  } catch (error) {
    self.postMessage({
      kind: 'error',
      requestId: msg.requestId,
      generation: msg.generation,
      error: error instanceof Error ? error.message : String(error),
    });
  }
};
