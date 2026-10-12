import { NextoEngine } from './nexto-core.mjs';
import { NextoAdapter } from './nexto-adapter.mjs';

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
