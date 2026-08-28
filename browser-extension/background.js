try { importScripts('config.js'); } catch (_) {}

const DEFAULT_BRIDGE_CONFIG = {
  bridgeHost: typeof DEFAULT_BRIDGE_HOST !== 'undefined' ? DEFAULT_BRIDGE_HOST : '127.0.0.1',
  bridgePort: typeof DEFAULT_BRIDGE_PORT !== 'undefined' ? DEFAULT_BRIDGE_PORT : 18765,
};
let bridgeConfig = { ...DEFAULT_BRIDGE_CONFIG };
let connecting = false;
let connectionGeneration = 0;
let currentPort = null;
let creatingOffscreenDocument = null;
const CONNECTION_STATUS_KEYS = ['lastConnectAttemptAt', 'lastConnectedAt', 'lastConnectError'];
let connectionStatus = { lastConnectAttemptAt: null, lastConnectedAt: null, lastConnectError: null };

async function ensureOffscreenDocument() {
  if (!chrome.offscreen || !chrome.offscreen.createDocument) return;
  if (creatingOffscreenDocument) return creatingOffscreenDocument;
  const url = chrome.runtime.getURL('offscreen.html');
  const contexts = chrome.runtime.getContexts
    ? await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'], documentUrls: [url] })
    : [];
  if (contexts.length > 0) return;
  creatingOffscreenDocument = chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['BLOBS'],
    justification: 'Keep the Omnibot MV3 service worker awake enough to maintain the local daemon WebSocket.'
  }).catch(() => {}).finally(() => { creatingOffscreenDocument = null; });
  return creatingOffscreenDocument;
}

const consoleCaptureByTab = new Map();
const mouseVisualByTab = new Map();

function getConsoleCapture(tabId) {
  const key = String(tabId);
  if (!consoleCaptureByTab.has(key)) {
    consoleCaptureByTab.set(key, { attached: false, entries: [] });
  }
  return consoleCaptureByTab.get(key);
}

function pushConsoleCaptureEntry(tabId, event) {
  const state = getConsoleCapture(tabId);
  state.entries.push(event);
  if (state.entries.length > 500) state.entries.splice(0, state.entries.length - 500);
}

const networkCaptureByTab = new Map();

function getNetworkCapture(tabId) {
  const key = String(tabId);
  if (!networkCaptureByTab.has(key)) {
    networkCaptureByTab.set(key, { attached: false, enabled: false, entries: [] });
  }
  return networkCaptureByTab.get(key);
}

function pushNetworkCaptureEntry(tabId, event) {
  const state = getNetworkCapture(tabId);
  if (!state.enabled) return;
  state.entries.push(event);
  if (state.entries.length > 1000) state.entries.splice(0, state.entries.length - 1000);
}

const dialogCaptureByTab = new Map();

const DEBUGGER_IDLE_TTL_MS = 30_000;
const DEBUGGER_LEASE_ALARM_PREFIX = 'omnibot-debugger-lease:';
const debuggerSessionsByTab = new Map();

function debuggerLeaseAlarmName(tabId) {
  return `${DEBUGGER_LEASE_ALARM_PREFIX}${Number(tabId)}`;
}

function getDebuggerSession(tabId) {
  const id = Number(tabId);
  if (!debuggerSessionsByTab.has(id)) {
    debuggerSessionsByTab.set(id, {
      owned: false,
      attaching: null,
      detaching: null,
      inFlight: 0,
      expiresAt: 0,
      timer: null,
    });
  }
  return debuggerSessionsByTab.get(id);
}

function setCaptureAttachedState(tabId, attached) {
  const key = String(tabId);
  if (consoleCaptureByTab.has(key)) consoleCaptureByTab.get(key).attached = attached;
  if (networkCaptureByTab.has(key)) networkCaptureByTab.get(key).attached = attached;
  if (dialogCaptureByTab.has(key)) dialogCaptureByTab.get(key).attached = attached;
}

function clearDebuggerLeaseTimer(session) {
  if (session.timer) clearTimeout(session.timer);
  session.timer = null;
}

function removeDebuggerSession(tabId, session) {
  const id = Number(tabId);
  if (debuggerSessionsByTab.get(id) !== session) return;
  clearDebuggerLeaseTimer(session);
  debuggerSessionsByTab.delete(id);
  setCaptureAttachedState(id, false);
}

function scheduleDebuggerLeaseCleanup(tabId, session) {
  const id = Number(tabId);
  if (session.timer) clearTimeout(session.timer);
  const delay = Math.max(100, session.expiresAt - Date.now());
  session.timer = setTimeout(() => { cleanupDebuggerSession(id); }, delay);
  // Creating an alarm with the same name replaces the previous schedule.  Do
  // not clear it first: chrome.alarms.clear is asynchronous and could otherwise
  // race with this replacement and remove the newly-created alarm.
  try { chrome.alarms.create(debuggerLeaseAlarmName(id), { when: Date.now() + delay }); } catch (_) {}
}

function renewDebuggerSession(tabId, session) {
  const id = Number(tabId);
  session.expiresAt = Date.now() + DEBUGGER_IDLE_TTL_MS;
  scheduleDebuggerLeaseCleanup(id, session);
  return session;
}

function touchDebuggerSession(tabId) {
  const id = Number(tabId);
  return renewDebuggerSession(id, getDebuggerSession(id));
}

function refreshDebuggerSessionIfAttached(tabId) {
  const session = debuggerSessionsByTab.get(Number(tabId));
  if (session && (session.owned || session.attaching || session.detaching)) {
    renewDebuggerSession(tabId, session);
  }
}

async function ensureDebuggerAttached(tabId) {
  const id = Number(tabId);
  const session = getDebuggerSession(id);
  if (session.detaching) await session.detaching;
  if (session.owned) return session;
  if (!session.attaching) {
    session.attaching = chrome.debugger.attach({ tabId: id }, '1.3')
      .then(() => {
        session.owned = true;
      })
      .finally(() => {
        session.attaching = null;
      });
  }
  await session.attaching;
  return session;
}

async function withDebugger(tabId, callback) {
  const id = Number(tabId);
  const session = touchDebuggerSession(id);
  session.inFlight += 1;
  try {
    await ensureDebuggerAttached(id);
    return await callback(id);
  } finally {
    session.inFlight = Math.max(0, session.inFlight - 1);
    if (debuggerSessionsByTab.get(id) === session) renewDebuggerSession(id, session);
  }
}

async function cleanupDebuggerSession(tabId) {
  const id = Number(tabId);
  const session = debuggerSessionsByTab.get(id);
  if (!session) return;
  if (session.inFlight > 0 || session.attaching || Date.now() < session.expiresAt) {
    scheduleDebuggerLeaseCleanup(id, session);
    return;
  }
  if (!session.owned) {
    if (!session.detaching) removeDebuggerSession(id, session);
    return;
  }
  session.owned = false;
  session.detaching = chrome.debugger.detach({ tabId: id }).catch(() => {});
  await session.detaching;
  session.detaching = null;
  if (session.inFlight === 0 && !session.owned) {
    removeDebuggerSession(id, session);
  } else {
    renewDebuggerSession(id, session);
  }
}

function getDialogCapture(tabId) {
  const key = String(tabId);
  if (!dialogCaptureByTab.has(key)) {
    dialogCaptureByTab.set(key, { attached: false, entries: [] });
  }
  return dialogCaptureByTab.get(key);
}

function dialogEntryKey(entry) {
  return [entry.type || '', entry.message || '', entry.defaultPrompt || ''].join('\u0000');
}

function pushDialogCaptureEntry(tabId, params) {
  const state = getDialogCapture(tabId);
  const entry = {
    type: params.type || '',
    message: params.message || '',
    defaultPrompt: params.defaultPrompt || '',
    hasBrowserHandler: !!params.hasBrowserHandler,
    timestamp: Date.now()
  };
  const previous = state.entries[state.entries.length - 1];
  if (previous && dialogEntryKey(previous) === dialogEntryKey(entry) && entry.timestamp - previous.timestamp < 1000) {
    state.entries[state.entries.length - 1] = {
      ...previous,
      hasBrowserHandler: previous.hasBrowserHandler || entry.hasBrowserHandler,
      timestamp: entry.timestamp
    };
    return;
  }
  state.entries.push(entry);
  if (state.entries.length > 100) state.entries.splice(0, state.entries.length - 100);
}

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!source || !source.tabId) return;
  if (['Runtime.consoleAPICalled', 'Runtime.exceptionThrown', 'Log.entryAdded'].includes(method)) {
    pushConsoleCaptureEntry(source.tabId, { method, params, timestamp: Date.now() });
    return;
  }
  if (['Network.requestWillBeSent', 'Network.responseReceived', 'Network.loadingFailed', 'Network.loadingFinished'].includes(method)) {
    pushNetworkCaptureEntry(source.tabId, { method, params, timestamp: Date.now() });
    return;
  }
  if (method === 'Page.javascriptDialogOpening') {
    pushDialogCaptureEntry(source.tabId, params || {});
  }
});

chrome.debugger.onDetach.addListener((source) => {
  if (!source || source.tabId === undefined) return;
  const session = debuggerSessionsByTab.get(Number(source.tabId));
  setCaptureAttachedState(source.tabId, false);
  if (!session || session.detaching) return;
  session.owned = false;
  removeDebuggerSession(source.tabId, session);
});

async function ensureConsoleCaptureAttached(tabId) {
  const state = getConsoleCapture(tabId);
  await withDebugger(tabId, async (id) => {
    await chrome.debugger.sendCommand({ tabId: id }, 'Runtime.enable', {});
    await chrome.debugger.sendCommand({ tabId: id }, 'Log.enable', {});
  });
  state.attached = true;
}

async function ensureNetworkCaptureAttached(tabId) {
  const state = getNetworkCapture(tabId);
  await withDebugger(tabId, async (id) => {
    await chrome.debugger.sendCommand({ tabId: id }, 'Network.enable', {});
  });
  state.attached = true;
}

async function ensureDialogCaptureAttached(tabId) {
  const state = getDialogCapture(tabId);
  await withDebugger(tabId, async (id) => {
    await chrome.debugger.sendCommand({ tabId: id }, 'Page.enable', {});
  });
  state.attached = true;
}

async function handleDialogCapture(msg, sender) {
  const tabId = msg.tabId || sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId', entries: [] };
  const op = msg.op || 'logs';
  try {
    await ensureDialogCaptureAttached(tabId);
    const state = getDialogCapture(tabId);
    if (op === 'clear') {
      state.entries.length = 0;
      return { ok: true, entries: [] };
    }
    if (op === 'handle') {
      const params = { accept: !!msg.accept };
      if (msg.promptText !== undefined) params.promptText = String(msg.promptText);
      await chrome.debugger.sendCommand({ tabId }, 'Page.handleJavaScriptDialog', params);
      return { ok: true, handled: true, entries: state.entries.slice(-100) };
    }
    if (op === 'logs' || op === 'dialogLogs') {
      return { ok: true, entries: state.entries.slice(-100) };
    }
    return { ok: false, error: 'Unknown dialogCapture op: ' + op, entries: state.entries.slice(-100) };
  } catch (e) {
    return { ok: false, error: e.message || String(e), entries: [] };
  }
}

async function handleDialogCaptureEvent(msg, sender) {
  const tabId = sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId' };
  pushDialogCaptureEntry(tabId, msg.event || {});
  return { ok: true };
}

async function handleNetworkCapture(msg, sender) {
  const tabId = msg.tabId || sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId' };
  const op = msg.op || msg.method || 'logs';
  try {
    await ensureNetworkCaptureAttached(tabId);
    const state = getNetworkCapture(tabId);
    if (op === 'start') {
      state.entries.length = 0;
      state.enabled = true;
      return { ok: true, entries: [] };
    }
    if (op === 'stop') {
      state.enabled = false;
      return { ok: true, entries: state.entries.slice(-1000) };
    }
    if (op === 'clear') {
      state.entries.length = 0;
      return { ok: true, entries: [] };
    }
    if (op === 'logs' || op === 'networkLogs') {
      return { ok: true, entries: state.entries.slice(-1000) };
    }
    return { ok: false, error: 'Unknown networkCapture op: ' + op, entries: state.entries.slice(-1000) };
  } catch (e) {
    return { ok: false, error: e.message || String(e), entries: [] };
  }
}

async function handleConsoleCapture(msg, sender) {
  const tabId = msg.tabId || sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId' };
  const op = msg.op || 'logs';
  try {
    await ensureConsoleCaptureAttached(tabId);
    const state = getConsoleCapture(tabId);
    if (op === 'clear') {
      state.entries.length = 0;
      await chrome.debugger.sendCommand({ tabId }, 'Console.clearMessages', {});
    }
    return { ok: true, entries: state.entries.slice(-500) };
  } catch (e) {
    return { ok: false, error: e.message || String(e), entries: [] };
  }
}

async function recordConnectionStatus(patch) {
  connectionStatus = { ...connectionStatus, ...patch };
  try { await chrome.storage.local.set({ connectionStatus, ...connectionStatus }); } catch (_) {}
}

async function loadBridgeConfig() {
  bridgeConfig = await chrome.storage.local.get(DEFAULT_BRIDGE_CONFIG);
  bridgeConfig.bridgeHost = normalizeBridgeHost(bridgeConfig.bridgeHost || DEFAULT_BRIDGE_CONFIG.bridgeHost);
  bridgeConfig.bridgePort = normalizeBridgePort(bridgeConfig.bridgeHost, bridgeConfig.bridgePort);
  return bridgeConfig;
}

function normalizeBridgeHost(host) {
  return String(host || DEFAULT_BRIDGE_CONFIG.bridgeHost).replace(/^wss?:\/\//, '').replace(/\/+$/, '');
}

function normalizeBridgePort(host, port) {
  const parsedPort = Number(port);
  if (Number.isInteger(parsedPort) && parsedPort > 0 && parsedPort <= 65535) return parsedPort;
  return isLocalBridge(host) ? DEFAULT_BRIDGE_CONFIG.bridgePort : '';
}

function isLocalBridge(host) {
  return /^(127\.0\.0\.1|localhost)$/.test(host);
}

async function ensureBrowserClientId() {
  const stored = await chrome.storage.local.get(['browserClientId']);
  if (stored.browserClientId) return stored.browserClientId;
  const id = `${navigator.userAgent.includes('Edg/') ? 'edge' : 'chromium'}-${chrome.runtime.id}-${crypto.randomUUID()}`;
  await chrome.storage.local.set({ browserClientId: id });
  return id;
}

function currentBrowserName() {
  if (navigator.userAgent.includes('Edg/')) return 'edge';
  if (navigator.userAgent.includes('OPR/') || navigator.userAgent.includes('Opera/')) return 'opera';
  return 'chrome';
}

async function hasDaemonHealthEndpoint(port) {
  const host = bridgeConfig.bridgeHost || DEFAULT_BRIDGE_CONFIG.bridgeHost;
  try {
    const resp = await fetch(`http://${host}:${port + 1}/api/health`);
    return resp.ok;
  } catch (_) {
    return false;
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: [9999],
    addRules: [{
      id: 9999, priority: 1,
      action: { type: 'modifyHeaders', responseHeaders: [
        { header: 'content-security-policy', operation: 'remove' },
        { header: 'content-security-policy-report-only', operation: 'remove' }
      ]},
      condition: { urlFilter: '*', resourceTypes: ['main_frame', 'sub_frame'] }
    }]
  });
});

async function handleExtMessage(msg, sender) {
  if (msg.tabId !== undefined && msg.tabId !== null) refreshDebuggerSessionIfAttached(msg.tabId);
  if (msg.cmd === 'offscreen_ping') {
    await ensureConnected();
    return { ok: true, connected: ws && ws.readyState === WebSocket.OPEN };
  }
  if (msg.cmd === 'get_status') {
    await ensureConnected();
    const cached = await chrome.storage.local.get(CONNECTION_STATUS_KEYS);
    return {
      connected: ws && ws.readyState === WebSocket.OPEN,
      port: currentPort,
      lastConnectAttemptAt: cached.lastConnectAttemptAt || connectionStatus.lastConnectAttemptAt,
      lastConnectedAt: cached.lastConnectedAt || connectionStatus.lastConnectedAt,
      lastConnectError: cached.lastConnectError || connectionStatus.lastConnectError,
    };
  }

  if (msg.cmd === 'reconnect') {
    const socket = ws;
    // Invalidate any async connection attempt before closing the old socket.
    // Its delayed onclose callback must not clear the replacement connection.
    connectionGeneration += 1;
    connecting = false;
    if (ws === socket) ws = null;
    currentPort = null;
    if (socket) socket.close();
    connectWS();
    return { ok: true };
  }

  if (msg.cmd === 'cdp') return await handleCDP(msg, sender);
  if (msg.cmd === 'consoleCapture') return await handleConsoleCapture(msg, sender);
  if (msg.cmd === 'networkCapture') return await handleNetworkCapture(msg, sender);
  if (msg.cmd === 'dialogCapture') return await handleDialogCapture(msg, sender);
  if (msg.cmd === 'dialogCaptureEvent') return await handleDialogCaptureEvent(msg, sender);
  if (msg.cmd === 'devtools' && msg.method === 'networkLogs') {
    return await handleNetworkCapture({ ...msg, cmd: 'networkCapture', op: 'logs' }, sender);
  }
  if (msg.cmd === 'batch') return await handleBatch(msg, sender);
  if (msg.cmd === 'clipboard') return await handleClipboard(msg, sender);
  if (msg.cmd === 'upload') {
    return { ok: false, error: 'upload requires browser file chooser support and is not available in the current extension transport' };
  }
  if (msg.cmd === 'tabs') {
    try {
      if (msg.method === 'switch') {
        const tab = await chrome.tabs.update(msg.tabId, { active: true });
        await chrome.windows.update(tab.windowId, { focused: true });
        return { ok: true };
      } else if (msg.method === 'close') {
        await chrome.tabs.remove(msg.tabId);
        return { ok: true };
      } else if (msg.method === 'create') {
        const tab = await chrome.tabs.create({ url: msg.url, active: false });
        const readyTab = await waitForScriptableTab(tab.id);
        const metadata = readyTab || await chrome.tabs.get(tab.id);
        return { ok: true, data: { id: metadata.id, url: metadata.url, title: metadata.title } };
      } else {
        const tabs = (await chrome.tabs.query({})).filter(t => isScriptable(t.url));
        const data = tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active, windowId: t.windowId }));
        return { ok: true, data };
      }
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'history') {
    try {
      if (msg.method !== 'search') return { ok: false, error: 'Unknown history method: ' + msg.method };
      const items = await chrome.history.search({
        text: String(msg.text || ''),
        startTime: Number.isFinite(Number(msg.startTime)) ? Number(msg.startTime) : undefined,
        endTime: Number.isFinite(Number(msg.endTime)) ? Number(msg.endTime) : undefined,
        maxResults: Math.max(1, Math.min(100, Number(msg.maxResults) || 20)),
      });
      return { ok: true, data: items.map(item => ({
        id: item.id,
        url: item.url || '',
        title: item.title || '',
        lastVisitTime: item.lastVisitTime || null,
        visitCount: item.visitCount || 0,
      })) };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'bookmarks') {
    try {
      if (msg.method !== 'getTree') return { ok: false, error: 'Unknown bookmarks method: ' + msg.method };
      return { ok: true, data: await chrome.bookmarks.getTree() };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'downloads') {
    try {
      if (msg.method === 'search') {
        const query = { query: Array.isArray(msg.query) ? msg.query.map(String) : [] };
        if (msg.id !== undefined && msg.id !== null && msg.id !== '') query.id = String(msg.id);
        if (msg.limit !== undefined) query.limit = Math.max(1, Math.min(100, Number(msg.limit) || 20));
        const items = await chrome.downloads.search(query);
        return { ok: true, data: items };
      }
      if (msg.method === 'open') {
        await chrome.downloads.open(String(msg.id));
        return { ok: true };
      }
      return { ok: false, error: 'Unknown downloads method: ' + msg.method };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'sessions') {
    try {
      if (msg.method !== 'recentlyClosed') return { ok: false, error: 'Unknown sessions method: ' + msg.method };
      const items = await chrome.sessions.getRecentlyClosed({
        maxResults: Math.max(1, Math.min(25, Number(msg.maxResults) || 10)),
      });
      return { ok: true, data: items };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'topSites') {
    try {
      if (msg.method !== 'get') return { ok: false, error: 'Unknown topSites method: ' + msg.method };
      return { ok: true, data: await chrome.topSites.get() };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'notifications') {
    console.log('[omnibot] notifications route received', { method: msg.method, id: msg.id || '' });
    try {
      if (msg.method !== 'create') return { ok: false, error: 'Unknown notifications method: ' + msg.method };
      const options = {
        type: 'basic',
        iconUrl: chrome.runtime.getURL('icons/icon-128.png'),
        title: String(msg.title || 'Omnibot'),
        message: String(msg.message || ''),
        priority: Math.max(0, Math.min(2, Number(msg.priority) || 0)),
      };
      // Use the callback form for compatibility with Chromium workers that
      // expose notifications APIs without Promise support.
      const id = await new Promise((resolve, reject) => {
        chrome.notifications.create(String(msg.id || ''), options, (createdId) => {
          const error = chrome.runtime.lastError;
          if (error) reject(new Error(error.message));
          else resolve(createdId);
        });
      });
      console.log('[omnibot] notifications.create succeeded', id);
      return { ok: true, data: { id } };
    } catch (e) {
      console.error('[omnibot] notifications.create failed:', e);
      return { ok: false, error: e.message || String(e), name: e.name || 'Error', stack: e.stack || '' };
    }
  }
  if (msg.cmd === 'windows') {
    try {
      if (msg.method !== 'create') return { ok: false, error: 'Unknown windows method: ' + msg.method };
      const win = await chrome.windows.create({ url: msg.url || 'about:blank', focused: false });
      const tab = win.tabs && win.tabs[0];
      return {
        ok: true,
        data: {
          windowId: win.id,
          tab: tab ? { id: tab.id, url: tab.url, title: tab.title } : null,
        },
      };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'tabStatus') {
    try {
      if (msg.method === 'cleanup') {
        const tabId = msg.tabId;
        await cleanupTabStatus(tabId);
        return { ok: true };
      }
      return { ok: false, error: 'Unknown tabStatus method: ' + msg.method };
    } catch (e) {
      if (String(e && e.message || '').includes('No tab with id')) {
        console.log('[omnibot] tab already gone during status cleanup:', msg.tabId);
        return { ok: true, gone: true };
      }
      return { ok: false, error: e.message };
    }
  }
  if (msg.cmd === 'tabGroups') {
    try {
      if (msg.method === 'group') {
        const tabId = msg.tabId;
        const title = msg.title || '';
        let tab = await callChromeApi(chrome.tabs.get, [tabId], chrome.tabs);
        let groupId = tab.groupId;
        if (groupId && groupId !== -1) {
          const groupTabs = await callChromeApi(chrome.tabs.query, [{ groupId: tab.groupId, windowId: tab.windowId }], chrome.tabs);
          if (groupTabs.length > 1) {
            const group = await callChromeApi(chrome.tabGroups.get, [tab.groupId], chrome.tabGroups);
            if (isOmnibotStatusTitle(group.title)) {
              // A target=_blank/noopener tab can inherit the source's
              // transient status group. Clear that whole stale group before
              // moving the source to its next status.
              await callChromeApi(chrome.tabs.ungroup, [groupTabs.map(item => item.id)], chrome.tabs);
            } else {
              await callChromeApi(chrome.tabs.ungroup, [tabId], chrome.tabs);
            }
            groupId = await callChromeApi(chrome.tabs.group, [{ tabIds: [tabId] }], chrome.tabs);
          }
        } else {
          groupId = await callChromeApi(chrome.tabs.group, [{ tabIds: [tabId] }], chrome.tabs);
        }
        await callChromeApi(chrome.tabGroups.update, [groupId, { title, collapsed: false }], chrome.tabGroups);
        tab = await callChromeApi(chrome.tabs.get, [tabId], chrome.tabs);
        return { ok: true, data: { groupId: tab.groupId } };
      } else if (msg.method === 'ungroup') {
        const tabId = msg.tabId;
        await cleanupTabStatus(tabId);
        return { ok: true };
      } else if (msg.method === 'get') {
        const tabId = msg.tabId;
        const tab = await callChromeApi(chrome.tabs.get, [tabId], chrome.tabs);
        if (!tab.groupId || tab.groupId === -1) {
          return { ok: true, data: { tabId, groupId: -1, grouped: false, favIconUrl: tab.favIconUrl || null } };
        }
        const group = await callChromeApi(chrome.tabGroups.get, [tab.groupId], chrome.tabGroups);
        return { ok: true, data: { tabId, groupId: tab.groupId, grouped: true, title: group.title, color: group.color, collapsed: group.collapsed, favIconUrl: tab.favIconUrl || null } };
      }
      return { ok: false, error: 'Unknown tabGroups method: ' + msg.method };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'tabFavicon') {
    try {
      if (msg.method === 'set') {
        await sendTabFavicon(msg.tabId, msg.iconKey);
        return { ok: true };
      } else if (msg.method === 'restore') {
        await _restoreTabFavicon(msg.tabId);
        return { ok: true };
      }
      return { ok: false, error: 'Unknown tabFavicon method: ' + msg.method };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'management') {
    try {
      if (msg.method === 'list') {
        const all = await chrome.management.getAll();
        return { ok: true, data: all.map(e => ({ id: e.id, name: e.name, enabled: e.enabled, type: e.type, version: e.version })) };
      }
      if (msg.method === 'reload') {
        chrome.alarms.create('tmwd-self-reload', { when: Date.now() + 200 });
        return { ok: true };
      }
      if (msg.method === 'disable') {
        await chrome.management.setEnabled(msg.extId, false);
        return { ok: true };
      }
      if (msg.method === 'enable') {
        await chrome.management.setEnabled(msg.extId, true);
        return { ok: true };
      }
      return { ok: false, error: 'Unknown method: ' + msg.method };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'contentSettings') {
    try {
      const type = msg.type || 'automaticDownloads';
      if (msg.method === 'get') {
        const primaryUrl = msg.url || 'https://example.com/';
        const setting = await callChromeApi(chrome.contentSettings[type].get, [{ primaryUrl }], chrome.contentSettings[type]);
        return { ok: true, data: setting };
      }
      const setting = msg.setting || 'allow';
      const pattern = msg.pattern || '<all_urls>';
      await callChromeApi(chrome.contentSettings[type].set, [{
        primaryPattern: pattern,
        setting: setting
      }], chrome.contentSettings[type]);
      return { ok: true };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  if (msg.cmd === 'mouseVisualState') {
    try {
      const tabId = Number(msg.tabId);
      const results = await chrome.scripting.executeScript({
        target: { tabId },
        func: () => {
          const host = document.getElementById('omnibot-mouse-visual');
          const root = host && host.shadowRoot;
          const asset = root && root.querySelector('.asset, .pointer-asset');
          const pointer = root && root.querySelector('.pointer');
          return {
            host: !!host,
            shadowRoot: !!root,
            pointer: !!pointer,
            asset: !!asset,
            assetComplete: !!(asset && asset.complete),
            pointerOpacity: pointer ? getComputedStyle(pointer).opacity : null,
          };
        },
      });
      return { ok: true, data: results && results[0] && results[0].result ? results[0].result : {} };
    } catch (e) { return { ok: false, error: e.message }; }
  }
  return { ok: false, error: 'Unknown cmd: ' + msg.cmd };
}

// Chromium versions differ on whether extension APIs expose Promise or
// callback forms. Keep browser-level operations working on both.
function callChromeApi(fn, args, receiver) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      callback(value);
    };
    const callback = (value) => {
      const error = chrome.runtime.lastError;
      if (error) finish(reject, new Error(error.message));
      else finish(resolve, value);
    };
    const useCallback = () => {
      try {
        fn.apply(receiver, [...args, callback]);
      } catch (error) {
        finish(reject, error);
      }
    };
    try {
      const result = fn.apply(receiver, args);
      if (result && typeof result.then === 'function') {
        result.then((value) => finish(resolve, value), (error) => finish(reject, error));
      } else if (result !== undefined) {
        finish(resolve, result);
      } else {
        useCallback();
      }
    } catch (error) {
      useCallback();
    }
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handleExtMessage(msg, sender).then(sendResponse);
  return true;
});

async function handleClipboard(msg, sender) {
  await ensureOffscreenDocument();
  const url = chrome.runtime.getURL('offscreen.html');
  const contexts = chrome.runtime.getContexts
    ? await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'], documentUrls: [url] })
    : [];
  if (contexts.length === 0) {
    return { ok: false, error: 'offscreen document not available' };
  }
  try {
    const res = await chrome.runtime.sendMessage({
      cmd: 'clipboard',
      method: msg.method,
      text: msg.text,
    });
    return res || { ok: false, error: 'no response from offscreen' };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}

async function handleBatch(msg, sender) {
  const R = [];
  const resolve$N = (params) => JSON.parse(JSON.stringify(params || {}).replace(/"\$(\d+)\.([^"]+)"/g,
    (_, i, path) => { let v = R[+i]; for (const k of path.split('.')) v = v[k]; return JSON.stringify(v); }));
  try {
    for (const c of msg.commands) {
      if (c.tabId === undefined && msg.tabId !== undefined) c.tabId = msg.tabId;
      if (c.cmd === 'tabs') {
        const tabs = (await chrome.tabs.query({})).filter(t => isScriptable(t.url));
        R.push({ ok: true, data: tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active, windowId: t.windowId })) });
      } else if (c.cmd === 'cdp') {
        const tabId = c.tabId || msg.tabId || sender.tab?.id;
        R.push(await withDebugger(tabId, (id) =>
          chrome.debugger.sendCommand({ tabId: id }, c.method, resolve$N(c.params))
        ));
      } else {
        R.push({ ok: false, error: 'unknown cmd: ' + c.cmd });
      }
    }
    return { ok: true, results: R };
  } catch (e) {
    return { ok: false, error: e.message, results: R };
  }
}

async function handleCDP(msg, sender) {
  const tabId = msg.tabId || sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId' };
  const watchNewTabs = !!msg.watchNewTabs;
  const browserClientId = await ensureBrowserClientId();
  let sourceStatusGroupId = -1;
  let sourceWindowId = -1;
  if (watchNewTabs) {
    try {
      const sourceTab = await chrome.tabs.get(Number(tabId));
      sourceWindowId = sourceTab.windowId;
      if (sourceTab.groupId && sourceTab.groupId !== -1) {
        const sourceGroup = await chrome.tabGroups.get(sourceTab.groupId);
        if (isOmnibotStatusTitle(sourceGroup.title)) sourceStatusGroupId = sourceTab.groupId;
      }
    } catch (_) {}
  }
  const candidateTabIds = new Set();
  // A global onCreated listener also sees tabs the user opens while an
  // automation command is in flight. openerTabId is not reliably populated
  // in the onCreated payload, so defer the ownership check until chrome.tabs
  // can return stable metadata for the candidate.
  const onCreated = (tab) => {
    candidateTabIds.add(tab.id);
  };
  if (watchNewTabs) chrome.tabs.onCreated.addListener(onCreated);
  try {
    const result = await withDebugger(tabId, async (id) => {
      const value = await chrome.debugger.sendCommand({ tabId: id }, msg.method, msg.params || {});
      // Give input dispatch a turn to reach the page before completing the command.
      if (msg.method === 'Input.dispatchKeyEvent') {
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      return value;
    });
    const ownedTabs = watchNewTabs
      ? await waitForOwnedNewTabs(candidateTabIds, tabId, sourceStatusGroupId, sourceWindowId)
      : [];
    const newTabs = ownedTabs.map(({ tab, ownershipReason }) => ({
      id: tab.id,
      url: tab.url,
      title: tab.title,
      openerTabId: tab.openerTabId,
      ownershipReason,
      browserClientId,
    }));
    return { ok: true, data: result, newTabs };
  } catch (e) {
    return { ok: false, error: e.message, newTabs: [] };
  } finally {
    if (watchNewTabs) chrome.tabs.onCreated.removeListener(onCreated);
  }
}

const isScriptable = url => url && /^https?:/.test(url);

async function waitForNewTabIds(newTabIds, timeoutMs = 800) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (newTabIds.size > 0) return Array.from(newTabIds);
    await new Promise(r => setTimeout(r, 80));
  }
  return Array.from(newTabIds);
}

async function waitForOwnedNewTabs(
  candidateTabIds,
  openerTabId,
  sourceStatusGroupId = -1,
  sourceWindowId = -1,
  timeoutMs = 2000,
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (sourceStatusGroupId === -1) {
      try {
        const sourceTab = await chrome.tabs.get(Number(openerTabId));
        sourceWindowId = sourceTab.windowId;
        if (sourceTab.groupId && sourceTab.groupId !== -1) {
          const sourceGroup = await chrome.tabGroups.get(sourceTab.groupId);
          if (isOmnibotStatusTitle(sourceGroup.title)) sourceStatusGroupId = sourceTab.groupId;
        }
      } catch (_) {}
    }
    const ownedTabs = [];
    for (const id of candidateTabIds) {
      try {
        const tab = await chrome.tabs.get(id);
        const openerMatches = tab.openerTabId === Number(openerTabId);
        // rel=noopener tabs omit openerTabId but still inherit the source
        // tab's short-lived Omnibot status group.
        const inheritedStatusGroup = sourceStatusGroupId !== -1
          && tab.groupId === sourceStatusGroupId
          && tab.windowId === sourceWindowId;
        if ((openerMatches || inheritedStatusGroup) && isScriptable(tab.url)) {
          ownedTabs.push({
            tab,
            ownershipReason: openerMatches ? 'opener' : 'status-group',
          });
        }
      } catch (_) {}
    }
    if (ownedTabs.length > 0) return ownedTabs;
    await new Promise(r => setTimeout(r, 80));
  }
  return [];
}

async function waitForScriptableTab(tabId, timeoutMs = 1800) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (isScriptable(tab.url)) return tab;
    } catch (_) {
      return null;
    }
    await new Promise(r => setTimeout(r, 120));
  }
  try {
    const tab = await chrome.tabs.get(tabId);
    return isScriptable(tab.url) ? tab : null;
  } catch (_) {
    return null;
  }
}

function buildExecScript(code, errorHandler) {
  return `(async () => {
    function smartProcessResult(result) {
      if (result === null || result === undefined || typeof result !== 'object') return result;
      try { if (result.window === result && result.document) return '[Window: ' + (result.location?.href || 'about:blank') + ']'; } catch(_){}
      if (typeof jQuery !== 'undefined' && result instanceof jQuery) {
        const elements = []; for (let i = 0; i < result.length; i++) { if (result[i] && result[i].nodeType === 1) elements.push(result[i].outerHTML); } return elements;
      }
      if (result instanceof NodeList || result instanceof HTMLCollection) {
        const elements = []; for (let i = 0; i < result.length; i++) { if (result[i] && result[i].nodeType === 1) elements.push(result[i].outerHTML); } return elements;
      }
      if (result.nodeType === 1) return result.outerHTML;
      if (!Array.isArray(result) && typeof result === 'object' && 'length' in result && typeof result.length === 'number') {
        const firstElement = result[0];
        if (firstElement && firstElement.nodeType === 1) {
          const elements = []; const length = Math.min(result.length, 100);
          for (let i = 0; i < length; i++) { const elem = result[i]; if (elem && elem.nodeType === 1) elements.push(elem.outerHTML); } return elements;
        }
      }
      try { return JSON.parse(JSON.stringify(result, function(key, value) { if (typeof value === 'object' && value !== null) { if (value.nodeType === 1) return value.outerHTML; if (value === window || value === document) return '[Object]'; try { if (value.window === value && value.document) return '[Window]'; } catch(_){} } return value; })); } catch (e) { return '[无法序列化: ' + e.message + ']'; }
    }
    try {
      const jsCode = ${JSON.stringify(code)}.trim();
      const lines = jsCode.split(/\\r?\\n/).filter(l => l.trim());
      const lastLine = lines.length > 0 ? lines[lines.length - 1].trim() : '';
      const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
      let r;
      function _air(c) { const ls = c.split(/\\r?\\n/); let i = ls.length - 1; while (i >= 0 && !ls[i].trim()) i--; if (i < 0) return c; const t = ls[i].trim(); if (/^(return |return;|return$|let |const |var |if |if\\(|for |for\\(|while |while\\(|switch|try |throw |class |function |async |import |export |\\/\\/|})/.test(t)) return c; ls[i] = ls[i].match(/^(\\s*)/)[1] + 'return ' + t; return ls.join('\\n'); }
      if (lastLine.startsWith('return')) {
        r = await (new AsyncFunction(jsCode))();
      } else {
        try { r = eval(jsCode); if (r instanceof Promise) r = await r; } catch (e) {
          if (e instanceof SyntaxError && (/return/i.test(e.message) || /await/i.test(e.message))) { r = await (new AsyncFunction(_air(jsCode)))(); } else throw e;
        }
      }
      return { ok: true, data: smartProcessResult(r) };
    } catch (e) {
      ${errorHandler}
    }
  })()`;
}

function buildPageScript(code) {
  return buildExecScript(code, `
      const errMsg = e.message || String(e);
      return { ok: false, error: { name: e.name || 'Error', message: errMsg, stack: e.stack || '' },
        csp: errMsg.includes('Refused to evaluate') || errMsg.includes('unsafe-eval') || errMsg.includes('Content Security Policy') };
  `);
}

function buildCdpScript(code) {
  return buildExecScript(code, `
      return { ok: false, error: { name: e.name || 'Error', message: e.message || String(e), stack: e.stack || '' } };
  `);
}

let ws = null;

function scheduleProbe() {
  chrome.alarms.create('tmwd-ws-probe', { delayInMinutes: 0.083 });
}

function scheduleKeepalive() {
  chrome.alarms.create('tmwd-ws-keepalive', { delayInMinutes: 0.4 });
}

async function isServerAlive() {
  try {
    const config = await loadBridgeConfig();
    if (!isLocalBridge(config.bridgeHost)) return true;
    const basePort = config.bridgePort || DEFAULT_BRIDGE_CONFIG.bridgePort;
    for (let i = 0; i < 3; i++) {
      const port = basePort + i;
      try {
        const ctrl = new AbortController();
        setTimeout(() => ctrl.abort(), 1500);
        await fetch(`http://${config.bridgeHost}:${port - 1}/api/health`, { signal: ctrl.signal });
        return true;
      } catch (e) {
        if (i === 2) return false;
      }
    }
    return false;
  } catch (e) {
    return false;
  }
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name.startsWith(DEBUGGER_LEASE_ALARM_PREFIX)) {
    const tabId = Number(alarm.name.slice(DEBUGGER_LEASE_ALARM_PREFIX.length));
    if (Number.isFinite(tabId)) await cleanupDebuggerSession(tabId);
    return;
  }
  if (alarm.name === 'tmwd-self-reload') {
    chrome.runtime.reload();
    return;
  }
  if (alarm.name === 'tmwd-ws-keepalive') {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'ping' })); } catch (_) {}
      scheduleKeepalive();
    } else {
      ws = null;
      currentPort = null;
      scheduleProbe();
    }
  }
  if (alarm.name === 'tmwd-ws-probe') {
    if (ws && ws.readyState <= 1) return;
    if (await isServerAlive()) {
      connectWS();
    } else {
      scheduleProbe();
    }
  }
});

async function handleWsExec(data, socket = ws) {
  const tabId = data.tabId;
  // ACK as soon as the WebSocket request is accepted.  Browser-level commands
  // must not lose their delivery acknowledgement while extension storage or
  // client-id recovery is waiting during service-worker startup.
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  if (tabId !== undefined && tabId !== null) refreshDebuggerSessionIfAttached(tabId);
  socket.send(JSON.stringify({ type: 'ack', id: data.id }));
  const browserClientId = await ensureBrowserClientId();
  let extensionCommand = null;
  try {
    const parsed = typeof data.code === 'string' ? JSON.parse(data.code) : data.code;
    const commands = new Set(['tabs', 'windows', 'tabGroups', 'tabStatus', 'tabFavicon', 'management', 'contentSettings', 'mouseVisualState', 'clipboard', 'history', 'bookmarks', 'downloads', 'sessions', 'topSites', 'notifications']);
    if (parsed && commands.has(parsed.cmd)) extensionCommand = parsed;
  } catch (_) {}
  if (extensionCommand) {
    try {
      const res = await handleExtMessage(extensionCommand, {});
      if (res && res.ok) {
        // Preserve the extension-command envelope.  The daemon uses `ok` to
        // distinguish a browser API result from a failed command.
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'result', id: data.id, result: res, browserClientId }));
      } else {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'error', id: data.id, error: (res && res.error) || 'Extension command failed', browserClientId }));
      }
    } catch (e) {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'error', id: data.id, error: e.message || String(e), browserClientId }));
    }
    return;
  }
  if (!tabId) {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'error', id: data.id, error: 'No tabId provided', browserClientId }));
    return;
  }
  const newTabIds = new Set();
  const onCreated = (tab) => {
    if (tab.openerTabId === Number(tabId)) newTabIds.add(tab.id);
  };
  chrome.tabs.onCreated.addListener(onCreated);
  try {
    let res;
    try {
      const result = await chrome.scripting.executeScript({
        target: { tabId },
        world: 'MAIN',
        func: async (s) => await eval(s),
        args: [buildPageScript(data.code)]
      });
      res = result[0]?.result;
      if (res === null || res === undefined) {
        res = { ok: false, error: { name: 'Error', message: 'executeScript returned null (possible CSP or context issue)', stack: '' }, csp: true };
      }
    } catch (e) {
      res = { ok: false, error: { name: e.name || 'Error', message: e.message || String(e), stack: e.stack || '' }, csp: true };
    }
    if (res && !res.ok && res.csp) {
      const wrappedCode = buildCdpScript(data.code);
      try {
        const cdpRes = await withDebugger(tabId, (id) =>
          chrome.debugger.sendCommand({ tabId: id }, 'Runtime.evaluate', {
            expression: wrappedCode, awaitPromise: true, returnByValue: true
          })
        );
        if (cdpRes.exceptionDetails) {
          const desc = cdpRes.exceptionDetails.exception?.description || 'CDP Error';
          res = { ok: false, error: { name: 'Error', message: desc, stack: desc } };
        } else {
          res = cdpRes.result.value;
        }
      } catch (cdpErr) {
        res = { ok: false, error: { name: 'Error', message: 'CDP fallback failed: ' + cdpErr.message, stack: '' } };
      }
    }
    if (newTabIds.size === 0) await new Promise(r => setTimeout(r, 200));
    chrome.tabs.onCreated.removeListener(onCreated);
    const newTabs = [];
    for (const id of newTabIds) {
      const t = await waitForScriptableTab(id);
      if (t) newTabs.push({id: t.id, url: t.url, title: t.title, openerTabId: t.openerTabId, browserClientId});
    }
    if (res?.ok) {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'result', id: data.id, result: res.data, newTabs, browserClientId }));
    } else {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'error', id: data.id, error: res?.error || 'Unknown error', newTabs, browserClientId }));
    }
  } catch (e) {
    const browserClientId = await ensureBrowserClientId();
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'error', id: data.id, error: { name: e.name || 'Error', message: e.message || String(e), stack: e.stack || '' }, browserClientId }));
  } finally {
    chrome.tabs.onCreated.removeListener(onCreated);
  }
}

function applyOperationGlow(action) {
  let count = window.__omniOperationGlowCount || 0;
  let hideTimer = window.__omniOperationGlowHideTimer || null;

  function ensureOperationGlow() {
    let host = document.getElementById('omni-operation-glow-host');
    if (host) return host;

    host = document.createElement('div');
    host.id = 'omni-operation-glow-host';
    host.setAttribute('aria-hidden', 'true');
    host.style.cssText = [
      'all:initial',
      'position:fixed',
      'inset:0',
      'display:block',
      'pointer-events:none',
      'z-index:2147483647',
      'opacity:0',
      'transition:opacity 180ms ease',
      'contain:strict'
    ].join(';');

    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        @keyframes omni-operation-breathe {
          0%, 100% { opacity: .68; filter: saturate(1.08); }
          50% { opacity: .95; filter: saturate(1.2); }
        }
        @keyframes omni-operation-sweep {
          0% { transform: translate3d(-42%, 0, 0); opacity: 0; }
          18%, 72% { opacity: .75; }
          100% { transform: translate3d(42%, 0, 0); opacity: 0; }
        }
        .frame {
          position: fixed;
          inset: 0;
          pointer-events: none;
          box-shadow:
            inset 0 0 30px rgba(45, 212, 191, .26),
            inset 0 0 72px rgba(59, 130, 246, .16);
          animation: omni-operation-breathe 1.45s ease-in-out infinite;
        }
        .edge {
          position: fixed;
          pointer-events: none;
          overflow: hidden;
        }
        .edge::before {
          content: "";
          position: absolute;
          background: linear-gradient(90deg, transparent, rgba(255, 214, 102, .72), rgba(45, 212, 191, .72), transparent);
          filter: blur(5px);
          animation: omni-operation-sweep 1.7s ease-in-out infinite;
        }
        .top, .bottom { left: 0; right: 0; height: 28px; }
        .top {
          top: 0;
          background: linear-gradient(to bottom, rgba(45, 212, 191, .52), rgba(255, 214, 102, .18) 38%, transparent 100%);
        }
        .bottom {
          bottom: 0;
          background: linear-gradient(to top, rgba(45, 212, 191, .44), rgba(59, 130, 246, .15) 42%, transparent 100%);
        }
        .top::before, .bottom::before { left: 0; right: 0; height: 12px; top: -3px; }
        .bottom::before { top: auto; bottom: -3px; }
        .left, .right { top: 0; bottom: 0; width: 28px; }
        .left {
          left: 0;
          background: linear-gradient(to right, rgba(45, 212, 191, .44), rgba(59, 130, 246, .15) 42%, transparent 100%);
        }
        .right {
          right: 0;
          background: linear-gradient(to left, rgba(45, 212, 191, .44), rgba(255, 214, 102, .14) 42%, transparent 100%);
        }
        .left::before, .right::before { top: 0; bottom: 0; width: 12px; left: -3px; transform: rotate(90deg); transform-origin: center; }
        .right::before { left: auto; right: -3px; transform: rotate(-90deg); }
      </style>
      <div class="frame"></div>
      <div class="edge top"></div>
      <div class="edge right"></div>
      <div class="edge bottom"></div>
      <div class="edge left"></div>
    `;
    (document.documentElement || document.body).appendChild(host);
    return host;
  }

  if (action === 'show') {
    count += 1;
    clearTimeout(hideTimer);
    const host = ensureOperationGlow();
    requestAnimationFrame(() => { host.style.opacity = '1'; });
  } else {
    count = Math.max(0, count - 1);
    if (count === 0) {
      const host = document.getElementById('omni-operation-glow-host');
      if (host) {
        host.style.opacity = '0';
        hideTimer = setTimeout(() => {
          const current = document.getElementById('omni-operation-glow-host');
          if (current && (window.__omniOperationGlowCount || 0) === 0) current.remove();
        }, 220);
      }
    }
  }

  window.__omniOperationGlowCount = count;
  window.__omniOperationGlowHideTimer = hideTimer;
}

async function sendOperationGlow(tabId, action, status) {
  try {
    await chrome.tabs.sendMessage(tabId, { cmd: 'rainbow-glow', action, status });
  } catch (err) {
    await chrome.scripting.executeScript({
      target: { tabId },
      world: 'ISOLATED',
      func: applyOperationGlow,
      args: [action]
    });
  }
}

async function cleanupTabStatus(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab.groupId && tab.groupId !== -1) {
      await chrome.tabs.ungroup(tabId);
    }
  } catch (err) {
    if (String(err && err.message || '').includes('No tab with id')) {
      console.log('[omnibot] tab already gone during status cleanup:', tabId);
      delete _tabOriginalFavicons[tabId];
      return;
    }
    console.log('[omnibot] tab group cleanup failed:', err.message);
  }
  try {
    await sendOperationGlow(tabId, 'hide', '');
  } catch (err) {
    console.log('[omnibot] operation glow cleanup failed:', err.message);
  }
  try {
    await _restoreTabFavicon(tabId);
  } catch (err) {
    console.log('[omnibot] favicon cleanup failed:', err.message);
  }
}

const FAVICON_SVGS = {
  read: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%233B82F6'/%3E%3Cpath fill='%23FFFFFF' d='M14.9 9.2 C13.5 8.3 11.9 7.9 10.1 7.9 C8.9 7.9 8 8.8 8 10 V20.8 C8 21.5 8.5 22 9.2 22 H10.3 C12.2 22 13.8 22.4 14.9 23.1 V9.2'/%3E%3Cpath fill='%23FFFFFF' d='M17.1 9.2 C18.2 8.3 19.8 7.9 21.9 7.9 C23.1 7.9 24 8.8 24 10 V20.8 C24 21.5 23.5 22 22.8 22 H21.7 C19.8 22 18.2 22.4 17.1 23.1 V9.2'/%3E%3Crect x='15' y='8.5' width='2' height='15.2' rx='1' fill='%23FFFFFF'/%3E%3C/svg%3E",
  navigate: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%2306B6D4'/%3E%3Cpath fill='%23FFFFFF' d='M23.8 7.4 18.9 20a2 2 0 0 1-1.1 1.1L5.2 26.6a.8.8 0 0 1-1-1L9.1 13a2 2 0 0 1 1.1-1.1l12.6-5.5a.8.8 0 0 1 1 1ZM16 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z'/%3E%3C/svg%3E",
  wait: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%2364748B'/%3E%3Cpath fill='%23FFFFFF' d='M16 5.5a10.5 10.5 0 1 0 0 21 10.5 10.5 0 0 0 0-21Zm1.2 10.1 4.1 2.4a1.2 1.2 0 1 1-1.2 2.1l-4.7-2.8a1.2 1.2 0 0 1-.6-1V10a1.2 1.2 0 1 1 2.4 0v5.6Z'/%3E%3C/svg%3E",
  screenshot: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%23A855F7'/%3E%3Cpath fill='%23FFFFFF' d='M11.2 8.5 12.5 7h7l1.3 1.5H23a3 3 0 0 1 3 3V22a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V11.5a3 3 0 0 1 3-3h2.2ZM16 22a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-2.2a2.8 2.8 0 1 1 0-5.6 2.8 2.8 0 0 1 0 5.6Z'/%3E%3C/svg%3E",
  click: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%23F59E0B'/%3E%3Cpath fill='%23FFFFFF' d='M9 6.5a1 1 0 0 1 1.3-.9l14 5.8a1 1 0 0 1-.1 1.9l-5.1 1.5 3.7 3.7a1.5 1.5 0 0 1 0 2.1l-2.2 2.2a1.5 1.5 0 0 1-2.1 0l-3.7-3.7-1.5 5.1a1 1 0 0 1-1.9.1L5.6 10.3A1 1 0 0 1 6.5 9H9V6.5Z'/%3E%3C/svg%3E",
  js_execute: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%23EF4444'/%3E%3Cpath fill='%23FFFFFF' d='M7 8.5A2.5 2.5 0 0 1 9.5 6h13A2.5 2.5 0 0 1 25 8.5v15a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 7 23.5v-15Zm4 5.1a1.2 1.2 0 0 0-1.7 1.7l2.7 2.7-2.7 2.7a1.2 1.2 0 0 0 1.7 1.7l3.5-3.5a1.2 1.2 0 0 0 0-1.7L11 13.6Zm5.5 7.9a1.2 1.2 0 0 0 0 2.4h5a1.2 1.2 0 0 0 0-2.4h-5Z'/%3E%3C/svg%3E",
  batch: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%236366F1'/%3E%3Cpath fill='%23FFFFFF' d='M7 8.5A1.5 1.5 0 0 1 8.5 7h5A1.5 1.5 0 0 1 15 8.5v5a1.5 1.5 0 0 1-1.5 1.5h-5A1.5 1.5 0 0 1 7 13.5v-5Zm10 0A1.5 1.5 0 0 1 18.5 7h5A1.5 1.5 0 0 1 25 8.5v5a1.5 1.5 0 0 1-1.5 1.5h-5a1.5 1.5 0 0 1-1.5-1.5v-5ZM7 18.5A1.5 1.5 0 0 1 8.5 17h5a1.5 1.5 0 0 1 1.5 1.5v5a1.5 1.5 0 0 1-1.5 1.5h-5A1.5 1.5 0 0 1 7 23.5v-5Zm10 0a1.5 1.5 0 0 1 1.5-1.5h5a1.5 1.5 0 0 1 1.5 1.5v5a1.5 1.5 0 0 1-1.5 1.5h-5a1.5 1.5 0 0 1-1.5-1.5v-5Z'/%3E%3C/svg%3E",
  scroll_down: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%230EA5E9'/%3E%3Cpath fill='%23FFFFFF' d='M16 6.5a1.5 1.5 0 0 1 1.5 1.5v11.4l4.2-4.2a1.5 1.5 0 1 1 2.1 2.1l-6.7 6.7a1.5 1.5 0 0 1-2.2 0l-6.7-6.7a1.5 1.5 0 1 1 2.1-2.1l4.2 4.2V8A1.5 1.5 0 0 1 16 6.5Z'/%3E%3C/svg%3E",
  scroll_up: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%230EA5E9'/%3E%3Cpath fill='%23FFFFFF' d='M16 25.5a1.5 1.5 0 0 1-1.5-1.5V12.6l-4.2 4.2a1.5 1.5 0 1 1-2.1-2.1L14.9 8a1.5 1.5 0 0 1 2.2 0l6.7 6.7a1.5 1.5 0 1 1-2.1 2.1l-4.2-4.2V24a1.5 1.5 0 0 1-1.5 1.5Z'/%3E%3C/svg%3E",
  new_tab: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%2306B6D4'/%3E%3Cpath fill='%23FFFFFF' d='M23.8 7.4 18.9 20a2 2 0 0 1-1.1 1.1L5.2 26.6a.8.8 0 0 1-1-1L9.1 13a2 2 0 0 1 1.1-1.1l12.6-5.5a.8.8 0 0 1 1 1ZM16 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z'/%3E%3C/svg%3E",
  done: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%2322C55E'/%3E%3Cpath fill='%23FFFFFF' d='M14.2 20.4 9.8 16a1.5 1.5 0 1 0-2.1 2.1l5.4 5.4a1.5 1.5 0 0 0 2.2-.1l9.2-11.5a1.5 1.5 0 1 0-2.3-1.9l-8 10.4Z'/%3E%3C/svg%3E",
  error: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%23DC2626'/%3E%3Cpath fill='%23FFFFFF' d='M10.7 8.6a1.5 1.5 0 0 0-2.1 2.1L13.9 16l-5.3 5.3a1.5 1.5 0 0 0 2.1 2.1l5.3-5.3 5.3 5.3a1.5 1.5 0 0 0 2.1-2.1L18.1 16l5.3-5.3a1.5 1.5 0 0 0-2.1-2.1L16 13.9l-5.3-5.3Z'/%3E%3C/svg%3E",
};

const BLANK_FAVICON_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3C/svg%3E";

const STATUS_TO_FAVICON = {
  '读取中': 'read',
  '导航中': 'navigate',
  '等待中': 'wait',
  '截图中': 'screenshot',
  '批量操作中': 'batch',
  '下滑中': 'scroll_down',
  '上滑中': 'scroll_up',
  '点击中': 'click',
  '移动中': 'click',
  '拖动中': 'click',
  '执行中': 'js_execute',
  '创建中': 'new_tab',
};

const COMPLETED_STATUSES = new Set([
  '已读取',
  '已导航',
  '等待完成',
  '已截图',
  '已操作',
  '已下滑',
  '已上滑',
  '已点击',
  '已移动',
  '已拖动',
  '已执行',
  '已创建',
]);

function isOmnibotStatusTitle(title) {
  const value = String(title || '');
  return Object.prototype.hasOwnProperty.call(STATUS_TO_FAVICON, value)
    || COMPLETED_STATUSES.has(value)
    || /^\d+s$/.test(value);
}

const _tabOriginalFavicons = {};

function setTabFavicon(svgUri) {
  const originals = [];
  document.querySelectorAll('link[rel*="icon"]').forEach(function(link) {
    originals.push(link.outerHTML);
    link.remove();
  });
  var link = document.createElement('link');
  link.rel = 'icon';
  link.href = svgUri;
  link.setAttribute('data-omnibot-favicon', '1');
  (document.head || document.documentElement).appendChild(link);
  return originals;
}

function restoreTabFavicon(originals, blankFaviconSvg) {
  var BLANK_FAVICON_SVG = blankFaviconSvg || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3C/svg%3E";
  function appendFallbackFavicon(favIconUrl) {
    var link = document.createElement('link');
    link.rel = 'icon';
    link.href = favIconUrl ? (favIconUrl === 'data:,' ? BLANK_FAVICON_SVG : favIconUrl) : BLANK_FAVICON_SVG;
    (document.head || document.documentElement).appendChild(link);
  }
  document.querySelectorAll('link[data-omnibot-favicon]').forEach(function(link) {
    link.remove();
  });
  var state = Array.isArray(originals) ? { links: originals, favIconUrl: null } : (originals || {});
  originals = state.links || [];
  if (originals && originals.length) {
    originals.forEach(function(html) {
      var temp = document.createElement('template');
      temp.innerHTML = html;
      var el = temp.content.firstChild;
      if (el) (document.head || document.documentElement).appendChild(el);
    });
    appendFallbackFavicon(state.favIconUrl);
  } else if (!originals || !originals.length) {
    appendFallbackFavicon(state.favIconUrl);
  }
}

function clearOmnibotFavicon() {
  document.querySelectorAll('link[data-omnibot-favicon]').forEach(function(link) {
    link.remove();
  });
}

async function sendTabFavicon(tabId, iconKey) {
  var svgUri = FAVICON_SVGS[iconKey];
  if (!svgUri) { console.log('[omnibot] sendTabFavicon: no SVG for key:', iconKey); return; }
  console.log('[omnibot] sendTabFavicon: injecting favicon for tab', tabId, 'key', iconKey);
  try {
    const originalTab = await chrome.tabs.get(tabId);
    var results = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      world: 'MAIN',
      func: setTabFavicon,
      args: [svgUri]
    });
    console.log('[omnibot] sendTabFavicon: executeScript MAIN world result:', results);
    if (!_tabOriginalFavicons[tabId] && results && results[0] && results[0].result) {
      _tabOriginalFavicons[tabId] = { links: results[0].result, favIconUrl: originalTab.favIconUrl || null };
    }
  } catch (err) {
    console.log('[omnibot] favicon set failed:', err.message);
  }
}

async function _restoreTabFavicon(tabId) {
  var originals = _tabOriginalFavicons[tabId];
  delete _tabOriginalFavicons[tabId];
  if (!originals) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tabId }, world: 'MAIN', func: clearOmnibotFavicon });
    } catch (err) {}
    return;
  }
  try {
    await chrome.scripting.executeScript({ target: { tabId: tabId }, world: 'MAIN', func: restoreTabFavicon, args: [originals, BLANK_FAVICON_SVG] });
  } catch (err) { console.log('[omnibot] favicon restore failed:', err.message); }
}

function handleWebSocketClose(socket) {
  // A close event can arrive after a replacement socket is already active.
  // Only the socket that still owns global connection state may clear it.
  if (ws !== socket) return;
  connectionGeneration += 1;
  connecting = false;
  ws = null;
  currentPort = null;
  scheduleProbe();
}

function setupWsHandlers(socket = ws) {
  if (!socket) return;
  socket.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'tabs_disconnected' && data.tab_ids) {
        for (const tabId of data.tab_ids) {
          try {
            await chrome.tabs.sendMessage(Number(tabId), { cmd: 'indicator-hide' });
          } catch (_) {}
        }
        return;
      }
      if (data.type === 'mouse_visual' && data.tabId !== undefined) {
        const tabId = Number(data.tabId);
        if (Number.isFinite(tabId)) {
          const event = data.event || {};
          mouseVisualByTab.set(String(tabId), { event, receivedAt: Date.now() });
          const deliver = () => chrome.tabs.sendMessage(tabId, { cmd: 'mouse-visual', event }).catch((err) => {
            console.log('[omnibot] mouse visualization delivery retry:', tabId, err.message);
          });
          // A page reload can finish after the daemon has already sent the
          // first event. Retry without blocking the worker on scripting API.
          deliver();
          setTimeout(deliver, 120);
          setTimeout(deliver, 600);
        }
        return;
      }
      if (data.groupStatus && data.tabId) {
        const statusTabId = Number(data.statusTabId ?? data.tabId);
        console.log('[omnibot] groupStatus received:', data.groupStatus, 'statusTabId:', statusTabId, 'tabId:', data.tabId);
        var codeObj = null;
        try { codeObj = typeof data.code === 'string' ? JSON.parse(data.code) : data.code; } catch (_) {}
        const isTabGroupsGroupCommand = codeObj && codeObj.cmd === 'tabGroups' && codeObj.method === 'group';
        if (!isTabGroupsGroupCommand) {
          handleExtMessage({cmd:'tabGroups', method:'group', tabId: statusTabId, title: data.groupStatus}, {}).catch(() => {});
        }
        const faviconKey = STATUS_TO_FAVICON[data.groupStatus];
        const isDone = COMPLETED_STATUSES.has(data.groupStatus);
        sendOperationGlow(statusTabId, isDone ? 'hide' : 'show', data.groupStatus).catch((err) => {
          console.log('[omnibot] operation glow failed:', err.message);
        });
        if (faviconKey) {
          console.log('[omnibot] favicon triggered:', faviconKey, 'for tab:', statusTabId);
          if (!(codeObj && codeObj.cmd === 'tabFavicon')) {
            sendTabFavicon(statusTabId, faviconKey).catch((err) => {
              console.log('[omnibot] favicon failed:', err.message);
            });
          }
          if (isDone) {
            setTimeout(() => _restoreTabFavicon(statusTabId), 2000);
          }
        } else {
          console.log('[omnibot] no favicon mapping for status:', data.groupStatus);
        }
      }
      if (data.id && data.code) {
        const browserClientId = await ensureBrowserClientId();
        let code = data.code;
        if (typeof code === 'string') {
          try { const p = JSON.parse(code); if (p && typeof p === 'object') code = p; } catch (_) {}
        }
        if (typeof code === 'object' && code !== null && code.cmd) {
          if (code.tabId === undefined && data.tabId !== undefined) code.tabId = data.tabId;
          const res = await handleExtMessage(code, {});
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: res.ok ? 'result' : 'error', id: data.id, result: res.data ?? res.results ?? res, error: res.error, newTabs: res.newTabs || [], browserClientId }));
        } else if (typeof code === 'string') {
          await handleWsExec(data, socket);
        } else if (typeof code === 'object' && code !== null) {
          const msg = code.tabId === undefined && data.tabId !== undefined ? { ...code, tabId: data.tabId } : code;
          const res = await handleExtMessage(msg, {});
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: res.ok ? 'result' : 'error', id: data.id, result: res.data ?? res.results ?? res, error: res.error, newTabs: res.newTabs || [], browserClientId }));
        }
      }
    } catch (e) {
      console.error('[omnibot] message parse error', e);
    }
  };
  socket.onclose = () => handleWebSocketClose(socket);
  socket.onerror = () => {};
}

async function ensureMouseVisualContentScript(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: installMouseVisualBridge,
    });
  } catch (err) {
    // Chrome internal/restricted pages cannot receive content scripts.
    console.log('[omnibot] mouse visual injection skipped:', tabId, err.message);
  }
}

// A small self-contained fallback for existing tabs. The full content bridge
// is still used on normal page loads, but this function guarantees that the
// visible cursor does not depend on content.js initialization order.
function installMouseVisualBridge() {
  if (window.__omnibotMouseVisualBridge) return;
  window.__omnibotMouseVisualBridge = true;
  // A page loaded after the current extension version exposes this renderer.
  // On extension reload, existing tabs can retain an old isolated-world flag
  // while their runtime listener is gone; only install the fallback when the
  // current renderer hook is absent.
  if (typeof window.__omnibotMouseVisualRender === 'function') return;
  let host = document.getElementById('omnibot-mouse-visual');
  let root;
  let pointer;
  let pressed = false;
  let hideTimer = null;
  if (host && host.shadowRoot) {
    root = host.shadowRoot;
  } else {
    host = document.createElement('div');
    host.id = 'omnibot-mouse-visual';
    host.style.cssText = 'all:initial;position:fixed;inset:0;pointer-events:none;z-index:2147483647;contain:strict';
    root = host.attachShadow({mode: 'open'});
  }
  // Replace a stale CSS cursor left by an older extension version with the
  // exact image-based renderer used by the ChatGPT browser extension.
  if (!root.querySelector('img.asset')) {
    root.innerHTML = `<style>
      .pointer{position:absolute;left:0;top:0;width:24px;height:24px;transform-origin:12px 12px;will-change:transform}
      .asset-holder{transform:translate3d(12px,-2.5px,0)}
      .asset{display:block;width:23px;height:24px;filter:drop-shadow(0 0 6px rgba(51,156,255,.9)) drop-shadow(0 0 15px rgba(51,156,255,.48));transform:rotate(44deg) scale(1);transform-origin:0 0}
      .ring{position:fixed;width:18px;height:18px;border:3px solid #fbbf24;border-radius:50%;transform:translate(-50%,-50%);animation:omni-pulse 520ms ease-out forwards}
      @keyframes omni-pulse{from{opacity:.95;transform:translate(-50%,-50%) scale(.35)}to{opacity:0;transform:translate(-50%,-50%) scale(2.8)}}
    </style><div class="pointer"><div class="asset-holder"><img class="asset" draggable="false"></div></div><div class="rings"></div>`;
    root.querySelector('.asset').src = chrome.runtime.getURL('cursor-chat.png');
  }
  pointer = root.querySelector('.pointer');
  pointer.style.opacity = '0';
  pointer.style.transition = 'opacity 100ms ease';
  const move = (x, y) => { pointer.style.transform = `translate3d(${x - 12}px,${y - 12}px,0) rotate(-44deg)`; };
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.cmd !== 'mouse-visual') return;
    const event = msg.event || {};
    const x = Number(event.x), y = Number(event.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    pointer.style.opacity = '1';
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { pointer.style.opacity = '0'; }, 4500);
    move(x, y);
    if (event.type === 'press') pressed = true;
    if (event.type === 'release') {
      pressed = false;
      const ring = document.createElement('i');
      ring.className = 'ring'; ring.style.left = `${x}px`; ring.style.top = `${y}px`;
      root.querySelector('.rings').appendChild(ring);
      setTimeout(() => ring.remove(), 560);
    }
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.cmd === 'mouse-visual-ready' && sender.tab && sender.tab.id != null) {
    const key = String(sender.tab.id);
    const pending = mouseVisualByTab.get(key);
    const isTopFrame = sender.frameId == null || sender.frameId === 0;
    const isFresh = pending && Date.now() - pending.receivedAt <= 1500;
    if (isTopFrame && isFresh) {
      chrome.tabs.sendMessage(sender.tab.id, { cmd: 'mouse-visual', event: pending.event }).catch(() => {});
    } else if (pending && !isFresh) {
      mouseVisualByTab.delete(key);
    }
    sendResponse && sendResponse({ok: true});
  }
});

async function ensureConnected() {
  if (ws && ws.readyState === WebSocket.OPEN) return true;
  if (connecting || (ws && ws.readyState === WebSocket.CONNECTING)) return false;
  await connectWS();
  return !!(ws && ws.readyState === WebSocket.OPEN);
}

async function connectWS() {
  if (connecting || (ws && ws.readyState <= 1)) return;
  const generation = ++connectionGeneration;
  connecting = true;
  ws = null;
  await loadBridgeConfig();
  await recordConnectionStatus({ lastConnectAttemptAt: new Date().toISOString(), lastConnectError: null });
  if (generation !== connectionGeneration) return;
  if (!(await isServerAlive())) {
    if (generation !== connectionGeneration) return;
    connecting = false;
    await recordConnectionStatus({ lastConnectError: 'daemon unavailable' });
    scheduleProbe();
    return;
  }
  const basePort = bridgeConfig.bridgePort || DEFAULT_BRIDGE_CONFIG.bridgePort;
  let lastError = null;
  for (let i = 0; i < 3; i++) {
    const port = basePort + i;
    const url = `ws://127.0.0.1:${port}`;
    try {
      const socket = await new Promise((resolve, reject) => {
        const socket = new WebSocket(url);
        const timer = setTimeout(() => { socket.close(); reject(new Error('timeout')); }, 2000);
        socket.onopen = () => { clearTimeout(timer); resolve(socket); };
        socket.onerror = () => { clearTimeout(timer); reject(new Error('connect failed')); };
      });
      if (generation !== connectionGeneration) {
        socket.close();
        return;
      }
      if (!(await hasDaemonHealthEndpoint(port))) {
        socket.close();
        throw new Error('daemon health endpoint unavailable');
      }
      if (generation !== connectionGeneration) {
        socket.close();
        return;
      }
      ws = socket;
      currentPort = port;
      // Install handlers before any awaited initialization below. The daemon
      // can send a command immediately after the WebSocket opens; delaying
      // this until after content-script setup loses the ACK and makes input
      // actions wait for their transport timeout.
      setupWsHandlers(socket);
      await recordConnectionStatus({ lastConnectedAt: new Date().toISOString(), lastConnectError: null });
      if (generation !== connectionGeneration) return;
      break;
    } catch (e) {
      if (generation !== connectionGeneration) return;
      lastError = e;
      ws = null;
      if (i === 2) {
        connecting = false;
        await recordConnectionStatus({ lastConnectError: lastError?.message || String(lastError) });
        scheduleProbe();
        return;
      }
    }
  }
  if (generation !== connectionGeneration) return;
  connecting = false;
  scheduleKeepalive();
  const browserClientId = await ensureBrowserClientId();
  const tabs = (await chrome.tabs.query({})).filter(t => isScriptable(t.url));
  if (generation !== connectionGeneration) return;
  const extensionVersion = chrome.runtime.getManifest().version || '';
  // Register the WebSocket before doing best-effort work on existing tabs.
  // scripting.executeScript can remain pending while an Edge internal page,
  // debugger attachment, or a page transition is settling.  Waiting for all
  // of those promises here leaves the daemon with an established TCP socket
  // but no ext_ready message, so it cannot create extension clients/sessions.
  const msg = { type: 'ext_ready', browserClientId, extensionId: chrome.runtime.id, extensionVersion, browser: currentBrowserName(), tabs: tabs.map(t => ({ id: t.id, url: t.url, title: t.title, groupId: t.groupId })) };
  if (ws && ws.readyState === WebSocket.OPEN && generation === connectionGeneration) ws.send(JSON.stringify(msg));
  // Existing tabs do not need to delay transport registration.  Injection is
  // deliberately best-effort and each call already handles restricted pages.
  Promise.all(tabs.map(t => ensureMouseVisualContentScript(t.id))).catch(() => {});
}

connectWS();
ensureOffscreenDocument();
chrome.runtime.onStartup.addListener(() => { connectWS(); ensureOffscreenDocument(); });
chrome.runtime.onInstalled.addListener(() => { connectWS(); ensureOffscreenDocument(); });

async function sendTabsUpdate() {
  try {
    await ensureConnected();
    const browserClientId = await ensureBrowserClientId();
    const tabs = (await chrome.tabs.query({})).filter(t => isScriptable(t.url) && !/streamlit/i.test(t.title));
    // The connection can close during either await above. Capture it only after
    // the asynchronous work so onclose cannot turn the global `ws` into null
    // between an earlier readiness check and this send.
    const socket = ws;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const msg = {
      type: 'tabs_update',
      browserClientId,
      extensionId: chrome.runtime.id,
      extensionVersion: chrome.runtime.getManifest().version || '',
      browser: currentBrowserName(),
      tabs: tabs.map(t => ({ id: t.id, url: t.url, title: t.title, groupId: t.groupId }))
    };
    socket.send(JSON.stringify(msg));
  } catch (err) {
    // Tab events are fire-and-forget. A concurrent disconnect or browser API
    // failure must not surface as an unhandled promise rejection in the worker.
    console.log('[omnibot] tabs update skipped:', err.message || String(err));
  }
}
chrome.tabs.onUpdated.addListener((_, changeInfo) => {
  if (changeInfo.status === 'complete') {
    // Existing tabs do not receive content_scripts again after an extension
    // reload; inject the visualization bridge when the document is ready.
    chrome.tabs.query({}).then(tabs => {
      const tab = tabs.find(item => item.id === _ && isScriptable(item.url));
      if (tab) ensureMouseVisualContentScript(tab.id);
    }).catch(() => {});
    sendTabsUpdate();
  }
});
chrome.tabs.onRemoved.addListener((tabId) => {
  const session = debuggerSessionsByTab.get(Number(tabId));
  if (session) removeDebuggerSession(tabId, session);
  const key = String(tabId);
  consoleCaptureByTab.delete(key);
  networkCaptureByTab.delete(key);
  dialogCaptureByTab.delete(key);
  mouseVisualByTab.delete(key);
  sendTabsUpdate();
});
chrome.tabs.onCreated.addListener(() => sendTabsUpdate());
chrome.tabs.onActivated.addListener(() => sendTabsUpdate());
