export const LAYOUT={"q1w":[0,4096],"q1b":[4096,128],"q2w":[4224,16384],"q2b":[20608,128],"k1w":[20736,3072],"k1b":[23808,128],"k2w":[23936,16384],"k2b":[40320,128],"b0iw":[40448,49152],"b0ib":[89600,384],"b0ow":[89984,16384],"b0ob":[106368,128],"b0f1w":[106496,65536],"b0f1b":[172032,512],"b0f2w":[172544,65536],"b0f2b":[238080,128],"b0n1w":[238208,128],"b0n1b":[238336,128],"b0n2w":[238464,128],"b0n2b":[238592,128],"b0n3w":[238720,128],"b0n3b":[238848,128],"b1iw":[238976,49152],"b1ib":[288128,384],"b1ow":[288512,16384],"b1ob":[304896,128],"b1f1w":[305024,65536],"b1f1b":[370560,512],"b1f2w":[371072,65536],"b1f2b":[436608,128],"b1n1w":[436736,128],"b1n1b":[436864,128],"b1n2w":[436992,128],"b1n2b":[437120,128],"b1n3w":[437248,128],"b1n3b":[437376,128],"a1w":[437504,256],"a1b":[437760,32],"a2w":[437792,1024],"a2b":[438816,32],"a3w":[438848,1024],"a3b":[439872,32],"ecw":[439904,4096],"ecb":[444000,32]};

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

export class NextoEngine {
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
