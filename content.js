(() => {
  'use strict';

  const CHANNEL = '__grandchamp_trainer_v4__';
  let latest = null;
  let panel = null;
  let inputs = null;
  let debug = null;
  let status = null;
  let button = null;
  let selector = null;
  let modelMenu = null;
  let modelMenuOpen = false;
  let modelsAvailable = [];
  let selectedModel = "g9";
  let changingModel = false;
  let error = null;
  let localError = "";
  let info = null;

  const UI_POS_KEY = 'car-soccer-ai-trainer-v4.1-position';
  let dragState = null;

  function loadPosition() {
    try {
      const value = JSON.parse(localStorage.getItem(UI_POS_KEY) || 'null');
      if (value && Number.isFinite(value.x) && Number.isFinite(value.y)) return value;
    } catch {}
    return { x: 18, y: 88 };
  }

  function savePosition() {
    if (!panel) return;
    try {
      localStorage.setItem(UI_POS_KEY, JSON.stringify({
        x: Math.round(panel.offsetLeft),
        y: Math.round(panel.offsetTop),
      }));
    } catch {}
  }

  // Nexto runs in a dedicated Web Worker owned by the extension content script.
  // This keeps ~4-10 ms neural inference work away from Car Soccer's render /
  // physics / WebRTC main thread.
  let nextoWorker = null;
  let nextoWorkerPromise = null;
  let nextoWorkerReady = false;
  let nextoBlobUrl = null;
  let loadedModelName = "Selected model";

  const send = (command, extra = {}) => {
    window.postMessage({ source: CHANNEL, from: 'ui', command, ...extra }, location.origin);
  };

  const bridge = (type, extra = {}) => {
    window.postMessage({ source: CHANNEL, from: 'nexto-bridge', type, ...extra }, location.origin);
  };

  function fmt(v) {
    return typeof v === 'number' && Number.isFinite(v)
      ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
      : 'n/a';
  }

  function percent(v) {
    return typeof v === 'number' && Number.isFinite(v)
      ? `${(v * 100).toFixed(0)}%`
      : 'n/a';
  }

  function wireWorker(worker, resolveReady, rejectReady, timer) {
    worker.onmessage = event => {
      const msg = event.data || {};
      if (msg.kind === 'ready') {
        clearTimeout(timer);
        nextoWorkerReady = true;
        // Startup succeeded. From this point onward a worker error is a real
        // runtime failure and should be forwarded to the page runtime.
        worker.onerror = runtimeEvent => {
          const message = runtimeEvent?.message || 'Nexto worker crashed.';
          nextoWorkerReady = false;
          nextoWorkerPromise = null;
          if (nextoWorker === worker) nextoWorker = null;
          try { worker.terminate(); } catch {}
          if (nextoBlobUrl) {
            URL.revokeObjectURL(nextoBlobUrl);
            nextoBlobUrl = null;
          }
          bridge('nexto-error', { error: message });
        };
        resolveReady(worker);
        return;
      }
      if (msg.kind === 'result') {
        bridge('nexto-result', {
          requestId: msg.requestId,
          generation: msg.generation,
          controls: msg.controls,
          actionIndex: msg.actionIndex,
          observedBoost: msg.observedBoost,
          latencyMs: msg.latencyMs,
        });
        return;
      }
      if (msg.kind === 'error') {
        bridge('nexto-error', {
          requestId: msg.requestId,
          generation: msg.generation,
          error: msg.error || 'Nexto worker error.',
        });
      }
    };

    // During startup, reject locally so ensureNextoWorker() can try the blob
    // fallback. Do not tell the game runtime that Nexto failed until every
    // startup strategy has actually failed.
    worker.onerror = event => {
      clearTimeout(timer);
      const message = event?.message || 'Nexto worker failed to start.';
      nextoWorkerReady = false;
      rejectReady(new Error(message));
    };
  }

  async function startWorker(strategy, workerUrl, workerSource, weights) {
    let worker;
    let localBlobUrl = null;
    if (strategy === 'direct') {
      worker = new Worker(workerUrl);
    } else {
      localBlobUrl = URL.createObjectURL(new Blob([workerSource], { type: 'text/javascript' }));
      worker = new Worker(localBlobUrl);
    }

    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`Nexto ${strategy} worker startup timed out.`)), 7000);
        wireWorker(worker, resolve, reject, timer);
        const copy = weights.slice(0);
        worker.postMessage({ kind: 'init', weights: copy }, [copy]);
      });
    } catch (error) {
      try { worker.terminate(); } catch {}
      if (localBlobUrl) URL.revokeObjectURL(localBlobUrl);
      throw error;
    }

    if (localBlobUrl) {
      if (nextoBlobUrl) URL.revokeObjectURL(nextoBlobUrl);
      nextoBlobUrl = localBlobUrl;
    }
    return worker;
  }

  async function ensureNextoWorker() {
    if (nextoWorkerReady && nextoWorker) return nextoWorker;
    if (nextoWorkerPromise) return nextoWorkerPromise;

    nextoWorkerPromise = (async () => {
      const workerUrl = chrome.runtime.getURL('nexto-worker.bundle.js');
      const stored = await chrome.storage.local.get(['selectedModel','modelCatalog']);
      const selected = stored.selectedModel || 'g9';
      let weights;
      if (selected.startsWith('custom-')) {
        const metadata = stored.modelCatalog?.[selected];
        if (!metadata) throw new Error('Imported model metadata missing. Import it again.');
        const key = 'model-weights:' + selected;
        const entry = await chrome.storage.local.get(key);
        if (!entry[key]) throw new Error('Imported model weights missing. Import the model again.');
        weights = Uint8Array.from(atob(entry[key]), c => c.charCodeAt(0)).buffer;
        loadedModelName = metadata.name;
      } else {
        if (selected !== 'nexto' && selected !== 'g9') throw new Error('Unknown selected model.');
        const filename = selected === 'g9' ? 'g9-weights.bin' : 'nexto-weights.bin';
        // The code patch ships without builtin assets. Nexto can instead be
        // restored by the user from the popup (stored inside extension storage).
        const builtin = selected === 'nexto' ? await chrome.storage.local.get('builtinNextoWeights') : {};
        if (typeof builtin.builtinNextoWeights === 'string') {
          weights = Uint8Array.from(atob(builtin.builtinNextoWeights), c => c.charCodeAt(0)).buffer;
        } else {
          let weightsResponse;
          try { weightsResponse = await fetch(chrome.runtime.getURL(filename)); }
          catch (cause) { throw new Error(`Missing ${filename}. Restore this binary in the installed extension folder and reload, or use Install Original Nexto in the popup with your genuine .pt/.bin checkpoint. (${cause.message || cause})`); }
          if (!weightsResponse.ok) throw new Error(`Missing ${filename} (HTTP ${weightsResponse.status}). Restore this .bin in the extension folder, or use Install Original Nexto in the popup.`);
          weights = await weightsResponse.arrayBuffer();
        }
        if (weights.byteLength !== 1776128) throw new Error(`Invalid ${filename}: expected 1,776,128 bytes, found ${weights.byteLength}. Reinstall the model.`);
        loadedModelName = selected === 'g9' ? 'G9 u0073' : 'Original Nexto';
      }
      const workerResponse = await fetch(workerUrl);
      if (!workerResponse.ok) throw new Error('Unable to load model worker.');
      const workerSource = await workerResponse.text();

      let directError = null;
      try {
        nextoWorker = await startWorker('direct', workerUrl, workerSource, weights);
      } catch (error) {
        directError = error;
        nextoWorkerReady = false;
        nextoWorker = null;
      }

      if (!nextoWorker) {
        try {
          nextoWorker = await startWorker('blob', workerUrl, workerSource, weights);
        } catch (blobError) {
          throw new Error(
            `Unable to start Nexto worker. Direct: ${directError?.message || directError || 'failed'}; ` +
            `Blob: ${blobError?.message || blobError}`
          );
        }
      }

      nextoWorkerReady = true;
      return nextoWorker;
    })().catch(error => {
      try { nextoWorker?.terminate(); } catch {}
      nextoWorker = null;
      nextoWorkerReady = false;
      nextoWorkerPromise = null;
      if (nextoBlobUrl) {
        URL.revokeObjectURL(nextoBlobUrl);
        nextoBlobUrl = null;
      }
      throw error;
    });

    return nextoWorkerPromise;
  }

  async function handleNextoRequest(data) {
    try {
      if (data.type === 'nexto-init') {
        await ensureNextoWorker();
        bridge('nexto-ready', { modelName: loadedModelName });
        return;
      }
      if (data.type === 'nexto-reset') {
        if (nextoWorkerReady && nextoWorker) {
          nextoWorker.postMessage({ kind: 'reset', generation: data.generation });
        }
        return;
      }
      if (data.type === 'nexto-infer') {
        const worker = await ensureNextoWorker();
        worker.postMessage({
          kind: 'infer',
          requestId: data.requestId,
          generation: data.generation,
          packet: data.packet,
        });
      }
    } catch (e) {
      bridge('nexto-error', {
        requestId: data.requestId,
        generation: data.generation,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type !== 'gct-model-changed') return;
    (async () => {
      send('disable');
      try { await nextoWorkerPromise; } catch {}
      try { nextoWorker?.terminate(); } catch {}
      nextoWorker=null;nextoWorkerPromise=null;nextoWorkerReady=false;
      if(nextoBlobUrl){URL.revokeObjectURL(nextoBlobUrl);nextoBlobUrl=null;}
      const stored=await chrome.storage.local.get(['selectedModel','modelCatalog']);
      const id=stored.selectedModel||'g9';
      const name=id.startsWith('custom-') ? stored.modelCatalog?.[id]?.name || 'Imported model'
        : id==='g9' ? 'G9 u0073' : 'Original Nexto';
      await refreshModelOptions();
      bridge('nexto-model-changed',{modelName:name});respond({ok:true});
    })().catch(e=>respond({ok:false,error:e.message}));
    return true;
  });

  function activeModelLabel() {
    if (latest?.selectedBot === 'grandchamp') return 'Grand Champion (native)';
    return modelsAvailable.find(m => m.id === selectedModel)?.name || 'G9 u0073';
  }

  function buildModelMenu() {
    if (!modelMenu || !selector) return;
    modelMenu.replaceChildren();
    for (const model of [...modelsAvailable, { id: 'grandchamp', name: 'Grand Champion (native)' }]) {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = 'gct4-model-choice';
      option.setAttribute('role', 'option');
      const active = model.id === (latest?.selectedBot === 'grandchamp' ? 'grandchamp' : selectedModel);
      option.setAttribute('aria-selected', String(active));
      option.textContent = (active ? '✓  ' : '    ') + model.name;
      option.addEventListener('click', event => {
        event.preventDefault(); event.stopPropagation();
        void switchModel(model.id);
      });
      modelMenu.appendChild(option);
    }
    selector.textContent = `${activeModelLabel()}  ▾`;
  }

  function setModelMenuOpen(open) {
    if (!modelMenu || !selector) return;
    modelMenuOpen = !!open;
    modelMenu.hidden = !modelMenuOpen;
    selector.setAttribute('aria-expanded', String(modelMenuOpen));
    if (modelMenuOpen) buildModelMenu();
  }

  async function releaseMouse() {
    if (document.pointerLockElement && document.exitPointerLock) {
      try { await document.exitPointerLock(); } catch {}
    }
  }

  async function switchModel(id) {
    if (changingModel) return;
    changingModel = true;
    setModelMenuOpen(false);
    await releaseMouse();
    try {
      localError = '';
      send('disable');
      if (id !== 'grandchamp') {
        const result = await chrome.runtime.sendMessage({ type: 'gct-select-model', modelId: id });
        if (!result?.ok) throw new Error(result?.error || 'Model switch failed.');
        // Reflect the intended model immediately, even before a status snapshot.
        selectedModel = id;
        await refreshModelOptions();
      }
      send('select-bot', { botId: id === 'grandchamp' ? 'grandchamp' : 'nexto' });
      if (info) { info.hidden = false; info.textContent = `Selected ${id === 'grandchamp' ? 'Grand Champion (native)' : activeModelLabel()}. Press Give Control to activate.`; }
    } catch (err) {
      localError = `Model switch failed: ${err.message || err}`;
      if (error) { error.hidden = false; error.textContent = localError; }
    } finally {
      changingModel = false;
      buildModelMenu();
      render();
    }
  }

  async function refreshModelOptions() {
    const stored = await chrome.storage.local.get(['selectedModel', 'modelCatalog']);
    selectedModel = stored.selectedModel || 'g9';
    const customs = Object.values(stored.modelCatalog || {})
      .filter(m => m?.id?.startsWith('custom-'))
      .sort((a, b) => String(a.name).localeCompare(String(b.name)));
    modelsAvailable = [
      { id: 'g9', name: 'G9 u0073' },
      { id: 'nexto', name: 'Original Nexto' },
      ...customs,
    ];
    if (!modelsAvailable.some(m => m.id === selectedModel)) selectedModel = 'g9';
    buildModelMenu();
    render();
  }

  function render() {
    if (!panel || !latest) return;
    const s = latest;
    const botName = s.botName || (s.selectedBot === 'nexto' ? 'Nexto' : 'Grand Champion');

    status.textContent = s.loading ? `Loading ${botName}…` : s.active ? `${botName} Control` : 'Player Control';
    button.disabled = !!s.loading;
    button.textContent = s.active ? 'Take Back Control' : `Give Control to ${botName}`;
    button.classList.toggle('active', !!s.active);
    selector.disabled = !!s.loading || changingModel;
    if (!changingModel) selector.textContent = `${activeModelLabel()}  ▾`;

    const c = s.lastControls || {};
    inputs.textContent = [
      `${botName}`,
      `Throttle:  ${fmt(c.throttle)}`,
      `Steer:     ${fmt(c.steer)}`,
      `Pitch:     ${fmt(c.pitch)}`,
      `Yaw:       ${fmt(c.yaw)}`,
      `Roll:      ${fmt(c.roll)}`,
      `Jump:      ${c.jump ? 'ON' : 'OFF'}`,
      `Boost:     ${c.boost ? 'ON' : 'OFF'}`,
      `Handbrake: ${c.handbrake ? 'ON' : 'OFF'}`,
    ].join('\n');

    debug.textContent = [
      `AI: ${botName}`,
      `mode: ${s.mode}${s.online ? ' / online' : ''}`,
      `room privacy auto-check: ${s.privacyCheck || 'off'}`,
      `AI ready: ${s.aiReady ? 'yes' : 'no'}`,
      `player slot: ${s.playerSlot}`,
      `team: ${s.team}`,
      `world tick: ${s.worldTick ?? 'n/a'}`,
      `cars: ${s.carCount ?? 'n/a'}`,
      `actual car boost: ${s.boost == null ? 'n/a' : Number(s.boost).toFixed(1)}`,
      `unlimited boost: ${s.unlimitedBoost == null ? 'n/a' : s.unlimitedBoost ? 'yes' : 'no'}`,
      `Nexto sees boost: ${s.selectedBot === 'nexto' ? percent(s.nextoObservedBoost) : 'n/a'}`,
      `Nexto inference: ${s.selectedBot === 'nexto' && Number.isFinite(s.nextoLatency) ? `${s.nextoLatency.toFixed(1)} ms` : 'n/a'}`,
      `Nexto action: ${s.selectedBot === 'nexto' ? (s.nextoLastAction ?? 'n/a') : 'n/a'}`,
      `Scripted kickoff: ${s.nextoScriptActive ? 'ACTIVE' : 'ON (waiting)'} `,
      `Nexto pending: ${s.selectedBot === 'nexto' ? (s.nextoPending ? 'yes' : 'no') : 'n/a'}`,
      `last AI apply: ${s.lastApplyAt ? `${Math.round(performance.now() - s.lastApplyAt)} ms ago` : 'n/a'}`,
      `game mode: ${s.gameMode}`,
      `phase: ${s.phase}`,
    ].join('\n');

    error.textContent = localError || s.error || '';
    error.hidden = !(localError || s.error);
    info.textContent = s.info || '';
    info.hidden = !s.info;
  }

  function build() {
    if (panel || !document.body) return;
    const style = document.createElement('style');
    style.textContent = `
#gct4-panel{position:fixed;z-index:2147483646;left:18px;top:88px;width:300px;color:#eef5ff;background:#0e1622f2;border:1px solid #40516a;border-radius:10px;box-shadow:0 12px 38px #0007;font:12px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none;overflow:hidden;backdrop-filter:blur(8px)}
#gct4-panel *{box-sizing:border-box}#gct4-panel button,#gct4-panel select{font:inherit}.gct4-head{display:flex;align-items:center;gap:8px;padding:9px 10px;background:#192538;font-weight:700;cursor:grab;touch-action:none}.gct4-head:active{cursor:grabbing}.gct4-dot{width:8px;height:8px;border-radius:50%;background:#55df8b;box-shadow:0 0 9px #55df8b88}.gct4-body{padding:10px}.gct4-status{display:flex;justify-content:space-between;gap:8px;margin-bottom:9px}.gct4-label{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px;color:#cbd5e1}.gct4-select{min-width:156px;max-width:198px;text-align:left;padding:6px 8px;border:1px solid #40516a;border-radius:6px;background:#111c2a;color:#fff;cursor:pointer}.gct4-menu{margin:-3px 0 8px;padding:5px;background:#09111d;border:1px solid #445779;border-radius:7px;max-height:210px;overflow-y:auto}.gct4-menu[hidden]{display:none}.gct4-model-choice{display:block;width:100%;margin:0;border:0;border-radius:5px;text-align:left;color:#e9f2fc;background:transparent;padding:9px;cursor:pointer;overflow-wrap:anywhere}.gct4-model-choice:hover,.gct4-model-choice:focus-visible{background:#2a4870}.gct4-model-choice[aria-selected=true]{color:#8bc5ff;font-weight:700}.gct4-main{width:100%;min-height:39px;border:1px solid #53709c;border-radius:7px;color:#fff;background:#2b67bc;cursor:pointer;font-weight:700}.gct4-main.active{background:#9b4141;border-color:#c06767}.gct4-main:disabled,.gct4-select:disabled{opacity:.55;cursor:wait}.gct4-note{margin:8px 0;color:#aebbd0}.gct4-inputs,.gct4-debug{margin-top:8px;padding:8px;background:#09111d;border:1px solid #28374c;border-radius:7px;font:11px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap}.gct4-error{margin-top:8px;color:#ff9c9c;overflow-wrap:anywhere}.gct4-info{margin-top:8px;color:#93c5fd;overflow-wrap:anywhere}
`;
    document.documentElement.appendChild(style);

    panel = document.createElement('section');
    panel.id = 'gct4-panel';
    const savedPos = loadPosition();
    panel.style.left = `${savedPos.x}px`;
    panel.style.top = `${savedPos.y}px`;

    panel.innerHTML = `
      <div class="gct4-head"><span class="gct4-dot"></span><span>Car Soccer AI Trainer v4.2.5</span></div>
      <div class="gct4-body">
        <div class="gct4-status"><span>Status</span><b>Connecting…</b></div>
        <label class="gct4-label">AI
          <button type="button" class="gct4-select" aria-controls="gct4-model-menu" aria-expanded="false">Choose model ▾</button>
        </label>
        <div id="gct4-model-menu" class="gct4-menu" role="listbox" hidden></div>
        <button class="gct4-main" type="button">Give Control to Nexto</button>
        <div class="gct4-note">Press <b>F7</b> to open models and release mouse lock; <b>Esc</b> also shows cursor. Import models in the extension popup. Emergency override: <b>F8</b>.</div>
        <details open><summary>AI Inputs</summary><div class="gct4-inputs"></div></details>
        <details><summary>Debug</summary><div class="gct4-debug"></div></details>
        <div class="gct4-info" hidden></div>
        <div class="gct4-error" hidden></div>
      </div>`;
    document.body.appendChild(panel);

    status = panel.querySelector('.gct4-status b');
    button = panel.querySelector('.gct4-main');
    selector = panel.querySelector('.gct4-select');
    modelMenu = panel.querySelector('.gct4-menu');
    inputs = panel.querySelector('.gct4-inputs');
    debug = panel.querySelector('.gct4-debug');
    error = panel.querySelector('.gct4-error');
    info = panel.querySelector('.gct4-info');

    button.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      send(latest?.active ? 'disable' : 'enable');
    });

    refreshModelOptions().catch(e => { localError=e.message; error.hidden=false;error.textContent=e.message; });
    selector.addEventListener('click', event => {
      event.preventDefault(); event.stopPropagation();
      void releaseMouse().then(() => setModelMenuOpen(!modelMenuOpen));
    });

    const head = panel.querySelector('.gct4-head');
    head.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      const rect = panel.getBoundingClientRect();
      dragState = { pointerId: e.pointerId, dx: e.clientX - rect.left, dy: e.clientY - rect.top };
      try { head.setPointerCapture(e.pointerId); } catch {}
      e.preventDefault();
      e.stopPropagation();
    });
    head.addEventListener('pointermove', e => {
      if (!dragState || dragState.pointerId !== e.pointerId) return;
      const maxX = Math.max(0, window.innerWidth - panel.offsetWidth);
      const maxY = Math.max(0, window.innerHeight - Math.min(panel.offsetHeight, window.innerHeight));
      const x = Math.max(0, Math.min(maxX, e.clientX - dragState.dx));
      const y = Math.max(0, Math.min(maxY, e.clientY - dragState.dy));
      panel.style.left = `${Math.round(x)}px`;
      panel.style.top = `${Math.round(y)}px`;
      e.preventDefault();
      e.stopPropagation();
    });
    const finishDrag = e => {
      if (!dragState || dragState.pointerId !== e.pointerId) return;
      dragState = null;
      try { head.releasePointerCapture(e.pointerId); } catch {}
      savePosition();
      e.preventDefault();
      e.stopPropagation();
    };
    head.addEventListener('pointerup', finishDrag);
    head.addEventListener('pointercancel', finishDrag);

    for (const type of ['pointerdown','pointerup','click','wheel']) {
      panel.addEventListener(type, e => e.stopPropagation());
    }

    send('snapshot');
    setInterval(() => send('snapshot'), 250);
  }

  window.addEventListener('message', event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const data = event.data;
    if (!data || data.source !== CHANNEL || data.from !== 'runtime') return;

    if (data.type === 'nexto-init' || data.type === 'nexto-reset' || data.type === 'nexto-infer') {
      handleNextoRequest(data);
      return;
    }

    if (data.state) latest = data.state;
    if (!panel) build();
    render();
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && (changes.modelCatalog || changes.selectedModel)) {
      refreshModelOptions().catch(e => {
        if (error) { error.hidden = false; error.textContent = e.message; }
      });
    }
  });

  window.addEventListener('keydown', event => {
    if (event.code === 'F7' && !event.repeat) {
      event.preventDefault(); event.stopImmediatePropagation();
      void releaseMouse().then(() => setModelMenuOpen(!modelMenuOpen));
      return;
    }
    if (event.code === 'Escape' && modelMenuOpen) {
      setModelMenuOpen(false);
      return;
    }
    if (event.code !== 'F8' || event.repeat || !latest?.active) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    send('disable');
  }, true);

  const ping = setInterval(() => {
    send('snapshot');
    if (panel) clearInterval(ping);
  }, 500);
  setTimeout(() => clearInterval(ping), 20000);

  addEventListener('pagehide', () => {
    try { nextoWorker?.terminate(); } catch {}
    if (nextoBlobUrl) URL.revokeObjectURL(nextoBlobUrl);
  }, { once: true });
})();
