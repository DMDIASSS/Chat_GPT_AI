import { selectModel } from './model-store.js';
import { transformMainSource as patchCarSoccer } from './patcher.js';
import { transformMainSource as patchTurball } from './turball-patcher.js';

// Each site has its own minified source layout and needs its own patcher.
const SITES = Object.freeze({
  'car-soccer.com': {
    id: 'car-soccer',
    label: 'Car Soccer',
    pattern: 'https://car-soccer.com/assets/main-*.js*',
    request: /^https:\/\/car-soccer\.com\/assets\/main-[^/?]+\.js(?:\?.*)?$/,
    patch: patchCarSoccer,
  },
  'turball.io': {
    id: 'turball',
    label: 'Turball',
    // Gameplay chunks receive a new content-hash filename after game releases.
    // The game loader in Turball build 332c59c495f7-38732477493-1
    // imports chunk-TVJT3ATP.js. Match all JS chunks and identify the
    // gameplay module by its exported startGame entry point, rather than
    // assuming a filename from the previous game build.
    pattern: 'https://turball.io/assets/app/chunk-*.js*',
    request: /^https:\/\/turball\.io\/assets\/app\/chunk-[A-Za-z0-9_-]+\.js(?:\?.*)?$/,
    patch: patchTurball,
  },
});

const PROTOCOL_VERSION = '1.3';
const armedTabs = new Map(); // tabId -> site config; only while CDP Fetch is attached
const arming = new Map();    // tabId -> Promise; prevent duplicate debugger attaches
const statusByTab = new Map();

function siteForUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' ? SITES[u.hostname] || null : null;
  } catch { return null; }
}

function disabledKey(tabId) { return `gct-disabled-tab-${tabId}`; }
async function isPaused(tabId) {
  const key = disabledKey(tabId);
  return Boolean((await chrome.storage.session.get(key))[key]);
}

function setStatus(tabId, fields) {
  const value = {
    enabled: false, site: null, state: 'idle', message: '',
    ...(statusByTab.get(tabId) || {}), ...fields,
  };
  statusByTab.set(tabId, value);
  // Session storage survives MV3 service-worker restarts. Do not misreport
  // a successfully installed patch as disabled if Chrome sleeps this worker.
  chrome.storage.session.set({ [`gct-status-${tabId}`]: value }).catch(() => {});
}

function command(tabId, method, params = {}) {
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

async function detach(tabId, { state = 'patched', message = 'Patch installed. Debugger detached.', enabled = true } = {}) {
  const config = armedTabs.get(tabId);
  if (!config) return;
  armedTabs.delete(tabId); // Mark expected detach before the detach event fires.
  try { await command(tabId, 'Fetch.disable'); } catch {}
  try { await chrome.debugger.detach({ tabId }); } catch {}
  setStatus(tabId, { site: config.id, enabled, state, message });
}

async function arm(tabId, site, { reload = false } = {}) {
  const prior = arming.get(tabId);
  if (prior) {
    await prior;
    if (armedTabs.get(tabId)?.id === site.id) {
      if (reload) await chrome.tabs.reload(tabId, { bypassCache: true });
      return;
    }
  }

  const task = (async () => {
    if (armedTabs.get(tabId)?.id === site.id) return;
    if (armedTabs.has(tabId)) {
      await detach(tabId, { state: 'switched', enabled: false, message: 'Switched websites.' });
    }
    setStatus(tabId, { site: site.id, state: 'attaching', enabled: false,
      message: `Detecting ${site.label}. Preparing the matching script…` });
    try {
      await chrome.debugger.attach({ tabId }, PROTOCOL_VERSION);
      armedTabs.set(tabId, site);
      await command(tabId, 'Fetch.enable', {
        patterns: [{ urlPattern: site.pattern, requestStage: 'Response' }],
      });
      setStatus(tabId, { site: site.id, enabled: true, state: 'armed',
        message: site.id === 'turball'
          ? 'Scanning Turball JavaScript. Start Free Play or a match to load the gameplay module.'
          : `Waiting for ${site.label} gameplay JavaScript…` });
    } catch (error) {
      const msg = String(error?.message || error);
      if (armedTabs.has(tabId)) {
        await detach(tabId, { state: 'error', enabled: false, message: msg });
      } else {
        setStatus(tabId, { site: site.id, state: 'error', enabled: false,
          message: /already attached/i.test(msg)
            ? 'Another debugger/DevTools is attached. Close it and use Enable + reload.' : msg });
      }
      throw error;
    }
  })();
  arming.set(tabId, task);
  try { await task; } finally { if (arming.get(tabId) === task) arming.delete(tabId); }
  if (reload) await chrome.tabs.reload(tabId, { bypassCache: true });
}

async function enableForTab(tabId) {
  const tab = await chrome.tabs.get(tabId);
  const site = siteForUrl(tab.url);
  if (!site) throw new Error('Open https://car-soccer.com or https://turball.io first.');
  await chrome.storage.session.remove(disabledKey(tabId));
  await arm(tabId, site, { reload: true });
}

async function disableForTab(tabId) {
  // Explicit Disable must override the automatic navigation listener,
  // including during the reload that restores the original game.
  await chrome.storage.session.set({ [disabledKey(tabId)]: true });
  try { await arming.get(tabId); } catch {}
  if (armedTabs.has(tabId)) {
    await detach(tabId, { state: 'disabled', enabled: false, message: 'Auto-patching paused on this tab.' });
  }
  const tab = await chrome.tabs.get(tabId);
  setStatus(tabId, { site: siteForUrl(tab.url)?.id || null, enabled: false,
    state: 'disabled', message: 'Paused for this tab. Use Enable + reload to resume.' });
  await chrome.tabs.reload(tabId, { bypassCache: true });
}

function decodeBody(body, base64Encoded) {
  if (!base64Encoded) return body;
  const binary = atob(body);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; ++i) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}
function encodeBody(source) {
  const bytes = new TextEncoder().encode(source);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}
function safeHeaders(headers = []) {
  const strip = new Set(['content-length','content-encoding','etag','content-md5']);
  const result = headers.filter(h => !strip.has(String(h.name).toLowerCase()));
  if (!result.some(h => String(h.name).toLowerCase() === 'content-type')) {
    result.push({ name: 'Content-Type', value: 'text/javascript; charset=utf-8' });
  }
  result.push({ name: 'Cache-Control', value: 'no-store' });
  return result;
}

chrome.debugger.onEvent.addListener(async (source, method, params) => {
  const tabId = source.tabId;
  const site = armedTabs.get(tabId);
  if (!tabId || !site || method !== 'Fetch.requestPaused') return;
  const requestId = params.requestId;
  const url = params.request?.url || '';

  if (!site.request.test(url)) {
    try { await command(tabId, 'Fetch.continueResponse', { requestId }); } catch {}
    return;
  }

  try {
    const response = await command(tabId, 'Fetch.getResponseBody', { requestId });
    const original = decodeBody(response.body, response.base64Encoded);
    // Turball loads dozens of shared chunks. Only the gameplay module exports
    // startGame; let every other response pass through unmodified. This also
    // prevents accidental rewrites of third-party or unrelated modules.
    if (site.id === 'turball' && !/\bexport\s*\{[^}]{0,256}\bas\s+startGame\b/.test(original)) {
      await command(tabId, 'Fetch.continueResponse', { requestId });
      return;
    }
    setStatus(tabId, { site: site.id, enabled: true, state: 'patching',
      message: `Found ${site.label} gameplay module ${new URL(url).pathname.split('/').pop()}; checking patch compatibility…` });
    const patched = site.patch(original);
    await command(tabId, 'Fetch.fulfillRequest', {
      requestId,
      responseCode: params.responseStatusCode || 200,
      responsePhrase: params.responseStatusText || 'OK',
      responseHeaders: safeHeaders(params.responseHeaders),
      body: encodeBody(patched),
    });
    // We never need to keep the debugger attached while playing.
    await detach(tabId, { site: site.id, enabled: true, state: 'patched',
      message: `${site.label}: patched ${new URL(url).pathname.split('/').pop()}. AI trainer ready.` });
  } catch (error) {
    const reason = String(error?.message || error);
    console.error(`[${site.label} AI Trainer]`, error);
    try { await command(tabId, 'Fetch.continueResponse', { requestId }); }
    catch {
      try { await command(tabId, 'Fetch.failRequest', { requestId, errorReason: 'Failed' }); } catch {}
    }
    await detach(tabId, { state: /Unsupported Turball build|anchor missing|expected one anchor|Post-patch check/i.test(reason) ? 'unsupported' : 'error', enabled: false,
      message: `${site.label} ${new URL(url).pathname.split('/').pop()} could not be patched: ${reason}. Game left unmodified. Save this gameplay JS module from DevTools > Network for an updated patch.` });
  }
});

chrome.debugger.onDetach.addListener((source, reason) => {
  const tabId = source.tabId;
  if (!tabId) return;
  const site = armedTabs.get(tabId);
  if (!site) return; // expected one-shot detach
  armedTabs.delete(tabId);
  setStatus(tabId, { site: site.id, enabled: false, state: 'detached',
    message: `Debugger detached unexpectedly: ${reason}. Use Enable + reload.` });
});

// Attach before the main document begins loading. Afterward the Fetch
// interception routes the correct script by both hostname and pathname.
chrome.webNavigation.onBeforeNavigate.addListener(details => {
  if (details.frameId !== 0 || !details.tabId || details.tabId < 0) return;
  const site = siteForUrl(details.url);
  if (!site) {
    if (armedTabs.has(details.tabId)) {
      void detach(details.tabId, { state: 'idle', enabled: false, message: 'Left supported game website.' });
    }
    return;
  }
  void (async () => {
    if (await isPaused(details.tabId)) return;
    await arm(details.tabId, site);
  })().catch(error => {
    console.warn(`[AI Trainer] auto-activation on ${site.label} failed:`, error);
  });
});

chrome.tabs.onRemoved.addListener(tabId => {
  armedTabs.delete(tabId);
  statusByTab.delete(tabId);
  chrome.storage.session.remove([disabledKey(tabId), `gct-status-${tabId}`]).catch(() => {});
});

// When installed while a game tab is already open, reload that tab once so
// its main/gameplay module can be intercepted. On ordinary service-worker
// wake-ups we do NOT reload tabs or interrupt games.
chrome.runtime.onInstalled.addListener(() => {
  void (async () => {
    const tabs = await chrome.tabs.query({ url: [
      'https://car-soccer.com/*', 'https://turball.io/*',
    ] });
    for (const tab of tabs) {
      if (!tab.id) continue;
      const site = siteForUrl(tab.url);
      if (!site || await isPaused(tab.id)) continue;
      try { await arm(tab.id, site, { reload: true }); }
      catch (error) { console.warn('[AI Trainer] installation activation:', error); }
    }
  })();
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    const tabId = message.tabId ?? sender.tab?.id;
    if (!tabId) throw new Error('No tab selected.');
    if (message.type === 'gct-select-model') {
      await selectModel(message.modelId);
      sendResponse({ ok: true }); return;
    }
    if (message.type === 'gct-enable') {
      await enableForTab(tabId);
      sendResponse({ ok: true, status: statusByTab.get(tabId) }); return;
    }
    if (message.type === 'gct-disable') {
      await disableForTab(tabId);
      sendResponse({ ok: true, status: statusByTab.get(tabId) }); return;
    }
    if (message.type === 'gct-status') {
      const key = `gct-status-${tabId}`;
      const stored = await chrome.storage.session.get(key);
      const status = statusByTab.get(tabId) || stored[key] || {
        enabled: false, state: 'idle', site: null,
        message: 'Open a supported game or use Enable + reload.',
      };
      sendResponse({ ok: true, status }); return;
    }
    throw new Error('Unknown message.');
  })().catch(error => sendResponse({ ok: false, error: String(error?.message || error) }));
  return true;
});
