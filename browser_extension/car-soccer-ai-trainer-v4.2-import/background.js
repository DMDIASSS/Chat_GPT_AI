import { transformMainSource } from './patcher.js';

const PROTOCOL_VERSION = '1.3';
const enabledTabs = new Set();
const statusByTab = new Map();

function setStatus(tabId, patch) {
  statusByTab.set(tabId, {
    enabled: enabledTabs.has(tabId),
    state: 'idle',
    message: '',
    ...statusByTab.get(tabId),
    ...patch,
  });
}

async function command(tabId, method, params = {}) {
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

async function detachPatcher(tabId, message = 'Patch installed. Debugger detached.', state = 'patched') {
  if (!enabledTabs.has(tabId)) return;
  try { await command(tabId, 'Fetch.disable'); } catch {}
  try { await chrome.debugger.detach({ tabId }); } catch {}
  enabledTabs.delete(tabId);
  setStatus(tabId, { enabled: state === 'patched', state, message });
}

async function enableForTab(tabId) {
  if (!enabledTabs.has(tabId)) {
    setStatus(tabId, { state: 'attaching', message: 'Attaching one-shot network patcher…' });
    try {
      await chrome.debugger.attach({ tabId }, PROTOCOL_VERSION);
    } catch (error) {
      const text = String(error?.message || error);
      if (/already attached/i.test(text)) {
        throw new Error('A debugger is already attached to this tab. Close DevTools/other debugger extensions and try again.');
      }
      throw error;
    }
    enabledTabs.add(tabId);
  }

  await command(tabId, 'Fetch.enable', {
    patterns: [{
      urlPattern: 'https://car-soccer.com/assets/main-*.js*',
      requestStage: 'Response',
    }],
  });

  setStatus(tabId, { enabled: true, state: 'armed', message: 'Armed for one reload…' });
  await chrome.tabs.reload(tabId, { bypassCache: true });
}

async function disableForTab(tabId, reload = true) {
  if (enabledTabs.has(tabId)) {
    try { await command(tabId, 'Fetch.disable'); } catch {}
    try { await chrome.debugger.detach({ tabId }); } catch {}
    enabledTabs.delete(tabId);
  }
  setStatus(tabId, { enabled: false, state: 'disabled', message: 'Trainer disabled.' });
  if (reload) {
    try { await chrome.tabs.reload(tabId, { bypassCache: true }); } catch {}
  }
}

function decodeBody(body, base64Encoded) {
  if (!base64Encoded) return body;
  const binary = atob(body);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

function encodeBody(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

function safeHeaders(headers = []) {
  const drop = new Set(['content-length', 'content-encoding', 'etag', 'content-md5']);
  const out = headers.filter(h => !drop.has(String(h.name).toLowerCase()));
  if (!out.some(h => String(h.name).toLowerCase() === 'content-type')) {
    out.push({ name: 'Content-Type', value: 'text/javascript; charset=utf-8' });
  }
  out.push({ name: 'Cache-Control', value: 'no-store' });
  return out;
}

chrome.debugger.onEvent.addListener(async (source, method, params) => {
  const tabId = source.tabId;
  if (!tabId || !enabledTabs.has(tabId) || method !== 'Fetch.requestPaused') return;

  const requestId = params.requestId;
  const url = params.request?.url || '';

  if (!/^https:\/\/car-soccer\.com\/assets\/main-[^/?]+\.js(?:\?.*)?$/.test(url)) {
    try { await command(tabId, 'Fetch.continueResponse', { requestId }); } catch {}
    return;
  }

  try {
    setStatus(tabId, { state: 'patching', message: 'Patching Car Soccer main module…' });
    const response = await command(tabId, 'Fetch.getResponseBody', { requestId });
    const original = decodeBody(response.body, response.base64Encoded);
    const patched = transformMainSource(original);

    await command(tabId, 'Fetch.fulfillRequest', {
      requestId,
      responseCode: params.responseStatusCode || 200,
      responsePhrase: params.responseStatusText || 'OK',
      responseHeaders: safeHeaders(params.responseHeaders),
      body: encodeBody(patched),
    });

    // Important: the debugger is only needed to replace main.js once.
    // Keeping Fetch/debugger attached during WebRTC/private-room play adds a
    // moving part we do not need, so detach immediately after successful patch.
    await detachPatcher(tabId, `Patched ${url.split('/').pop()} and detached.`);
  } catch (error) {
    const message = String(error?.message || error);
    setStatus(tabId, { state: 'error', message });
    console.error('[Car Soccer AI Trainer] patch failed:', error);
    try {
      await command(tabId, 'Fetch.continueResponse', { requestId });
    } catch {
      try { await command(tabId, 'Fetch.failRequest', { requestId, errorReason: 'Failed' }); } catch {}
    }
    await detachPatcher(tabId, `Patch failed: ${message}`, 'error');
  }
});

chrome.debugger.onDetach.addListener((source, reason) => {
  const tabId = source.tabId;
  if (!tabId) return;
  if (!enabledTabs.has(tabId)) return; // expected one-shot detach
  enabledTabs.delete(tabId);
  setStatus(tabId, { enabled: false, state: 'detached', message: `Debugger detached: ${reason}` });
});

chrome.tabs.onRemoved.addListener(tabId => {
  enabledTabs.delete(tabId);
  statusByTab.delete(tabId);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    const tabId = message.tabId ?? sender.tab?.id;
    if (!tabId) throw new Error('No tab selected.');

    if (message.type === 'gct-enable') {
      await enableForTab(tabId);
      sendResponse({ ok: true, status: statusByTab.get(tabId) });
      return;
    }
    if (message.type === 'gct-disable') {
      await disableForTab(tabId, true);
      sendResponse({ ok: true, status: statusByTab.get(tabId) });
      return;
    }
    if (message.type === 'gct-status') {
      sendResponse({
        ok: true,
        status: statusByTab.get(tabId) || {
          enabled: false,
          state: 'disabled',
          message: '',
        },
      });
      return;
    }
    throw new Error('Unknown message.');
  })().catch(error => sendResponse({ ok: false, error: String(error?.message || error) }));
  return true;
});
