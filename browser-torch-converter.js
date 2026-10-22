/**
 * Browser-only reader for PyTorch ZIP checkpoints / TorchScript archives that
 * contain the 44 float tensors used by the native Nexto actor. This is a DATA
 * parser, not a Python interpreter: pickle symbols are never executed.
 */
const decoder = new TextDecoder();
const MAX_FILE = 256 * 1024 * 1024;
const MAX_ARCHIVE = 512 * 1024 * 1024;
const u16 = (d, i) => d.getUint16(i, true);
const u32 = (d, i) => d.getUint32(i, true);
const chars = bytes => decoder.decode(bytes);
function err(message) { throw new Error(message); }

async function openZip(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (bytes.byteLength > MAX_FILE) err('Checkpoint is larger than 256 MiB.');
  const d = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const len = bytes.byteLength;
  let end = -1;
  for (let i = len - 22; i >= Math.max(0, len - 65557); i--) {
    if (u32(d, i) === 0x06054b50 && i + 22 + u16(d, i + 20) === len) { end = i; break; }
  }
  if (end < 0) err('Not a supported PyTorch ZIP archive. Select a native .pt checkpoint, not a renamed file.');
  const count = u16(d, end + 10), dirLength = u32(d, end + 12), dirOffset = u32(d, end + 16);
  if (u16(d, end + 8) !== count || u16(d, end + 4) !== 0 || u16(d, end + 6) !== 0)
    err('Multi-disk ZIP archives are unsupported.');
  if (count > 5000 || dirOffset + dirLength > end) err('Invalid or unusually large ZIP directory.');
  let pos = dirOffset, expandedSize = 0;
  const entries = new Map();
  for (let n = 0; n < count; n++) {
    if (pos + 46 > len || u32(d, pos) !== 0x02014b50) err('Invalid ZIP central directory.');
    const method = u16(d, pos + 10), compressed = u32(d, pos + 20), expanded = u32(d, pos + 24);
    const nameSize = u16(d, pos + 28), extra = u16(d, pos + 30), comment = u16(d, pos + 32);
    const offset = u32(d, pos + 42);
    if (compressed === 0xffffffff || expanded === 0xffffffff || offset === 0xffffffff)
      err('ZIP64 archives are unsupported.');
    if (pos + 46 + nameSize + extra + comment > len) err('ZIP entry name is truncated.');
    const name = chars(bytes.subarray(pos + 46, pos + 46 + nameSize));
    pos += 46 + nameSize + extra + comment;
    if (name.endsWith('/')) continue;
    expandedSize += expanded;
    if (expandedSize > MAX_ARCHIVE) err('Archive expands beyond the safety limit.');
    if (method !== 0 && method !== 8) err('Unsupported ZIP compression format.');
    if (offset + 30 > len || u32(d, offset) !== 0x04034b50) err('Missing ZIP entry header.');
    const start = offset + 30 + u16(d, offset + 26) + u16(d, offset + 28);
    if (start + compressed > len) err('ZIP entry data is truncated.');
    if (entries.has(name)) err('Archive contains duplicate filenames.');
    entries.set(name, { start, compressed, expanded, method });
  }
  async function read(name) {
    const entry = entries.get(name);
    if (!entry) err(`Checkpoint is missing ${name}.`);
    if (entry.expanded > MAX_FILE) err('ZIP entry is too large.');
    const data = bytes.subarray(entry.start, entry.start + entry.compressed);
    let output;
    if (entry.method === 0) output = data;
    else {
      if (typeof DecompressionStream !== 'function') err('This browser cannot decompress PyTorch ZIP files. Update Chrome/Brave.');
      try {
        const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
        output = new Uint8Array(await new Response(stream).arrayBuffer());
      } catch { err(`Could not decompress ZIP entry ${name}.`); }
    }
    if (output.byteLength !== entry.expanded) err(`ZIP entry ${name} has an incorrect size.`);
    return output;
  }
  return { entries, read };
}

/** Narrow, side-effect-free pickle stack reader; no GLOBAL ever resolves to JS code. */
function parsePickle(bytes) {
  if (bytes.byteLength > 32 * 1024 * 1024) err('PyTorch pickle metadata is too large.');
  const d = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const stack = [], memo = new Map();
  const MARK = Symbol('pickle mark');
  let i = 0, nextMemo = 0, steps = 0;
  function take(count) {
    if (count < 0 || i + count > bytes.length) err('Truncated PyTorch pickle data.');
    const out = bytes.subarray(i, i + count); i += count; return out;
  }
  function one() { return take(1)[0]; }
  function num4() { const n = d.getUint32(i, true); take(4); return n; }
  function num2() { const n = d.getUint16(i, true); take(2); return n; }
  function str(count) { return chars(take(count)); }
  function line() { const start = i; while (i < bytes.length && bytes[i] !== 10) i++; if (i >= bytes.length) err('Unterminated pickle line.'); const s = chars(bytes.subarray(start, i)); i++; return s; }
  function popMark() { const arr = []; while (stack.length && stack[stack.length - 1] !== MARK) arr.unshift(stack.pop()); if (!stack.length) err('Invalid pickle MARK stack.'); stack.pop(); return arr; }
  function top() { return stack[stack.length - 1]; }
  function save(key) { memo.set(key, top()); if (key >= nextMemo) nextMemo = key + 1; }
  function build(obj, state) {
    if (obj && typeof obj === 'object' && state && typeof state === 'object') {
      const data = Array.isArray(state) ? state.find(x => x && typeof x === 'object' && !Array.isArray(x)) : state;
      if (data) Object.assign(obj, data);
    }
    return obj;
  }
  function reduce(fn, args) {
    const sym = fn?.__global || '';
    if (sym === 'collections.OrderedDict' || sym === 'builtins.dict' || sym === '__builtin__.dict') return Object.create(null);
    if (/^torch\._utils\._rebuild_tensor(_v[23])?$/.test(sym)) {
      if (!args[0]?.__storage) err('Model tensor references an unsupported storage.');
      return { __tensor: true, storage: args[0], offset: args[1], shape: args[2], stride: args[3] };
    }
    if (/^torch\._utils\._rebuild_parameter/.test(sym)) return args[0];
    if (sym === 'torch.jit._pickle.restore_type_tag') return args[0];
    if (sym === 'torch._utils._rebuild_device_tensor_from_numpy') err('NumPy checkpoint tensors cannot be loaded in this format. Export a standard torch state_dict.');
    if (sym === 'torch._tensor._rebuild_from_type_v2') return args[0];
    // Custom Python classes are represented as inert data objects.
    if (/^(?:__torch__\.|torch\.nn\.|collections\.defaultdict)/.test(sym)) return { __class: sym };
    err(`Unsupported PyTorch pickle constructor: ${sym || '<unknown>'}. Upload a compatible Nexto state_dict/TorchScript checkpoint.`);
  }
  while (i < bytes.length) {
    if (++steps > 2000000 || stack.length > 500000) err('PyTorch pickle is too complex.');
    const op = one();
    switch (op) {
      case 0x80: { const proto = one(); if (proto > 5) err(`Unsupported pickle protocol ${proto}.`); break; } // PROTO
      case 0x95: take(8); break; // FRAME
      case 0x2e: if (stack.length !== 1) err('Invalid pickle stack at STOP.'); return stack[0];
      case 0x28: stack.push(MARK); break;
      case 0x7d: stack.push(Object.create(null)); break;
      case 0x5d: stack.push([]); break;
      case 0x29: stack.push([]); break;
      case 0x88: stack.push(true); break;
      case 0x89: stack.push(false); break;
      case 0x4e: stack.push(null); break;
      case 0x4b: stack.push(one()); break;
      case 0x4d: stack.push(num2()); break;
      case 0x4a: { const v = d.getInt32(i, true); take(4); stack.push(v); break; }
      case 0x8a: { const len = one(); const b = take(len); let result = 0n; for(let n = len - 1; n >= 0; n--) result = (result << 8n) + BigInt(b[n]); stack.push(Number(result)); break; }
      case 0x47: { const v = d.getFloat64(i, false); take(8); stack.push(v); break; }
      case 0x46: stack.push(Number(line())); break;
      case 0x58: stack.push(str(num4())); break;
      case 0x8c: stack.push(str(one())); break;
      case 0x8d: { const low = num4(), high = num4(); if (high !== 0) err('Oversized pickle string.'); stack.push(str(low)); break; }
      case 0x55: stack.push(str(one())); break;
      case 0x54: stack.push(str(num4())); break;
      case 0x43: stack.push(take(one())); break;
      case 0x42: stack.push(take(num4())); break;
      case 0x8e: { const n = num4(), high = num4(); if (high) err('Oversized pickle bytes.'); stack.push(take(n)); break; }
      case 0x63: stack.push({ __global: `${line()}.${line()}` }); break;
      case 0x93: { const name = stack.pop(), mod = stack.pop(); stack.push({ __global: `${mod}.${name}` }); break; }
      case 0x71: save(one()); break;
      case 0x72: save(num4()); break;
      case 0x68: { const k = one(); if (!memo.has(k)) err('Unknown pickle memo reference.'); stack.push(memo.get(k)); break; }
      case 0x6a: { const k = num4(); if (!memo.has(k)) err('Unknown pickle memo reference.'); stack.push(memo.get(k)); break; }
      case 0x94: save(nextMemo); break;
      case 0x74: stack.push(popMark()); break;
      case 0x85: stack.push([stack.pop()]); break;
      case 0x86: { const b = stack.pop(), a = stack.pop(); stack.push([a,b]); break; }
      case 0x87: { const c = stack.pop(), b = stack.pop(), a = stack.pop(); stack.push([a,b,c]); break; }
      case 0x75: { const arr = popMark(), obj = top(); if (!obj || typeof obj !== 'object') err('Bad SETITEMS target.'); for (let n=0;n<arr.length;n+=2) { if (typeof arr[n] !== 'string') err('Non-string dictionary key.'); Object.defineProperty(obj,arr[n],{value:arr[n+1],enumerable:true,writable:true,configurable:true}); } break; }
      case 0x73: { const value = stack.pop(), key = stack.pop(), obj=top(); if(typeof key!=='string') err('Non-string dictionary key.'); Object.defineProperty(obj,key,{value,enumerable:true,writable:true,configurable:true}); break; }
      case 0x65: { const arr = popMark(), obj = top(); if (!Array.isArray(obj)) err('Bad APPENDS target.'); obj.push(...arr); break; }
      case 0x61: { const v=stack.pop(); top().push(v); break; }
      case 0x52: { const args = stack.pop(), fn = stack.pop(); stack.push(reduce(fn, args)); break; }
      case 0x81: { const args=stack.pop(), fn=stack.pop(); stack.push({ __class:fn?.__global || 'object', __args: args }); break; }
      case 0x92: { const kwargs=stack.pop(), args=stack.pop(), fn=stack.pop(); stack.push({ __class:fn?.__global || 'object', __args:args, __kwargs:kwargs }); break; }
      case 0x62: { const state=stack.pop(); build(top(),state); break; }
      case 0x51: { const pid=stack.pop(); if (!Array.isArray(pid) || pid[0] !== 'storage') err('Unsupported persistent reference in PyTorch checkpoint.'); const storageName=pid[1]?.__global || ''; const type=storageName.split('.').at(-1); if (!/^(Float|Double|Half|BFloat16|Long|Int)Storage$/.test(type)) err(`Unsupported tensor storage type ${type}.`); stack.push({__storage:true, type, key:String(pid[2]), device:pid[3], size:pid[4]}); break; }
      case 0x30: stack.pop(); break; // POP
      case 0x32: stack.push(top()); break; // DUP
      default: err(`Unsupported PyTorch pickle opcode 0x${op.toString(16).padStart(2,'0')}. The selected .pt may require a different exporter.`);
    }
  }
  err('Missing pickle STOP opcode.');
}

function getTensorMap(root, layout) {
  const names = new Set(layout.map(x => x.tensor));
  const map = new Map();
  // state_dict checkpoints may wrap the actor; native TorchScript has a nested module tree.
  const candidates = [root?.actor, root?.state_dict, root?.model_state_dict, root?.model?.actor, root];
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== 'object') continue;
    const local = new Map(), visit = new WeakSet();
    function walkCandidate(obj, prefix = '', depth=0) {
      if (!obj || typeof obj !== 'object' || depth > 40 || visit.has(obj)) return;
      visit.add(obj);
      if (obj.__tensor) { if (names.has(prefix)) local.set(prefix, obj); return; }
      for (const [key,value] of Object.entries(obj)) if (!key.startsWith('__')) walkCandidate(value, prefix ? `${prefix}.${key}` : key, depth+1);
    }
    walkCandidate(candidate);
    if (local.size === names.size) return local;
    if (local.size > map.size) { map.clear(); for(const [k,v] of local)map.set(k,v); }
  }
  const missing = [...names].filter(x=>!map.has(x));
  err(`Incompatible model architecture (${map.size}/${names.size} Nexto tensors found). Missing: ${missing.slice(0,3).join(', ')}. Only the native Nexto 44-tensor actor is supported.`);
}

function halfToFloat(h) {
  const sign = (h & 0x8000) ? -1 : 1, exp = (h >> 10) & 31, mant = h & 1023;
  if (exp===0) return sign * 2 ** -14 * (mant / 1024);
  if (exp===31) return mant ? NaN : sign * Infinity;
  return sign * 2 ** (exp-15) * (1 + mant/1024);
}
function storageType(type) { return {FloatStorage:4,DoubleStorage:8,HalfStorage:2,BFloat16Storage:2,LongStorage:8,IntStorage:4}[type]; }
async function convertPyTorchArchive(zip, layout) {
  const pklName = [...zip.entries.keys()].find(x => /(^|\/)data\.pkl$/.test(x));
  if (!pklName) err('Missing data.pkl in PyTorch checkpoint.');
  const prefix = pklName.slice(0, -'data.pkl'.length);
  const byteorderName = prefix + 'byteorder';
  if (zip.entries.has(byteorderName) && chars(await zip.read(byteorderName)).trim() !== 'little')
    err('Only little-endian PyTorch archives are supported.');
  const root = parsePickle(await zip.read(pklName));
  const tensors = getTensorMap(root, layout);
  const result = new ArrayBuffer(layout.reduce((max,x)=>Math.max(max,x.offset+x.length),0)*4);
  const output = new Float32Array(result), storageCache = new Map();
  const bfloatScratch = new DataView(new ArrayBuffer(4));
  for (const item of layout) {
    const tensor = tensors.get(item.tensor);
    if (!tensor || !Array.isArray(tensor.shape) || tensor.shape.length !== item.shape.length ||
        !item.shape.every((x,i)=>x===tensor.shape[i])) err(`Incompatible shape for ${item.tensor}.`);
    const { storage, offset, stride } = tensor;
    if (!Number.isSafeInteger(offset) || offset < 0 || !Array.isArray(stride) || stride.length !== item.shape.length)
      err(`Unsupported storage view for ${item.tensor}.`);
    const typeBytes = storageType(storage.type);
    if (!typeBytes) err(`Unsupported storage type: ${storage.type}.`);
    if (typeof storage.device !== 'string' || !/^(cpu|cuda(?::\d+)?|mps)$/.test(storage.device)) err('Unsupported PyTorch checkpoint storage device.');
    const path = prefix + 'data/' + storage.key;
    let bytes = storageCache.get(path);
    if (!bytes) { bytes = await zip.read(path); storageCache.set(path,bytes); }
    const dv = new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    const dense = item.shape.every((_,i)=>stride[i] === item.shape.slice(i+1).reduce((a,b)=>a*b,1));
    if (!dense) err(`Noncontiguous tensor ${item.tensor} is not supported. Export contiguous weights.`);
    if ((offset+item.length)*typeBytes > bytes.length) err(`Truncated tensor storage for ${item.tensor}.`);
    for (let j=0;j<item.length;j++) {
      const at = (offset+j)*typeBytes;
      let val;
      switch (storage.type) {
        case 'FloatStorage': val=dv.getFloat32(at,true); break;
        case 'DoubleStorage': val=dv.getFloat64(at,true); break;
        case 'HalfStorage': val=halfToFloat(dv.getUint16(at,true)); break;
        case 'BFloat16Storage': { bfloatScratch.setUint32(0,dv.getUint16(at,true)<<16,true); val=bfloatScratch.getFloat32(0,true); break; }
        case 'LongStorage': val=Number(dv.getBigInt64(at,true)); break;
        case 'IntStorage': val=dv.getInt32(at,true); break;
      }
      if (!Number.isFinite(val)) err(`Nonfinite weight in ${item.tensor}.`);
      output[item.offset+j] = val;
    }
  }
  return result;
}

export async function convertPtBuffer(input, layout) {
  const zip = await openZip(input);
  if ([...zip.entries.keys()].some(x => /(^|\/)data\.pkl$/.test(x))) return convertPyTorchArchive(zip, layout);
  // RLBot export .zip containing one or more checkpoints: require all identical.
  const candidates = [...zip.entries.keys()].filter(x => /\.pt$/i.test(x));
  if (!candidates.length) err('ZIP does not contain a compatible .pt checkpoint.');
  if (candidates.length > 64) err('ZIP contains too many .pt checkpoints. Select one .pt file instead.');
  let first = null;
  for (const name of candidates) {
    const item=await zip.read(name);
    const weights=await convertPtBuffer(item,layout);
    if (!first) first=new Uint8Array(weights);
    else {
      const check=new Uint8Array(weights);
      if (check.length!==first.length || !first.every((v,i)=>v===check[i]))
        err('ZIP contains different models. Select one individual .pt file instead.');
    }
  }
  return first.buffer;
}
