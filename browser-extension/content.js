;(function(){ if (/streamlit/i.test(document.title)) return;

document.addEventListener('__omnibot_native_dialog__', (event) => {
  try {
    chrome.runtime.sendMessage({ cmd: 'dialogCaptureEvent', event: event.detail || {} });
  } catch (_) {}
}, true);

window.addEventListener('message', (event) => {
  try {
    const data = event.data || {};
    if (data.source !== 'omnibot-native-dialog') return;
    chrome.runtime.sendMessage({
      cmd: 'dialogCaptureEvent',
      event: {
        type: data.type || '',
        message: data.message || '',
        defaultPrompt: data.defaultPrompt || '',
        timestamp: data.timestamp || Date.now()
      }
    });
  } catch (_) {}
});

// Remove meta CSP tags
document.querySelectorAll('meta[http-equiv="Content-Security-Policy"]').forEach(e => e.remove());

// Operation glow effect during MCP operations
(function(){
  if(window.self!==window.top)return;

  let operationCount = 0;
  let hideTimer = null;

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
    (document.documentElement||document.body).appendChild(host);
    return host;
  }

  function setOperationGlow(action) {
    if (action === 'show') {
      operationCount++;
      clearTimeout(hideTimer);
      const host = ensureOperationGlow();
      requestAnimationFrame(() => { host.style.opacity = '1'; });
      return;
    }

    operationCount = Math.max(0, operationCount - 1);
    if (operationCount > 0) return;
    const host = document.getElementById('omni-operation-glow-host');
    if (!host) return;
    host.style.opacity = '0';
    hideTimer = setTimeout(() => {
      const current = document.getElementById('omni-operation-glow-host');
      if (current && operationCount === 0) current.remove();
    }, 220);
  }

  window.__omniOperationGlow = setOperationGlow;

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.cmd === 'rainbow-glow') {
      setOperationGlow(msg.action);
      sendResponse && sendResponse({ ok: true });
    }
    if (msg.cmd === 'tab-favicon-set') {
      try {
        const originals = [];
        document.querySelectorAll('link[rel*="icon"]').forEach(function(link) {
          originals.push(link.outerHTML);
          link.remove();
        });
        var link = document.createElement('link');
        link.rel = 'icon';
        link.href = msg.svgUri;
        link.setAttribute('data-omnibot-favicon', '1');
        (document.head || document.documentElement).appendChild(link);
        sendResponse({ ok: true, originals: originals });
      } catch (e) { sendResponse({ ok: false, error: e.message }); }
      return true;
    }
    if (msg.cmd === 'tab-favicon-restore') {
      try {
        document.querySelectorAll('link[data-omnibot-favicon]').forEach(function(link) { link.remove(); });
        (msg.originals || []).forEach(function(html) {
          var temp = document.createElement('template');
          temp.innerHTML = html;
          var el = temp.content.firstChild;
          if (el) (document.head || document.documentElement).appendChild(el);
        });
        sendResponse({ ok: true });
      } catch (e) { sendResponse({ ok: false, error: e.message }); }
      return true;
    }
  });
})();

// Visualize CDP mouse input in the page viewport. CDP dispatches browser input
// events but does not move the browser-host cursor, so this Shadow DOM layer
// mirrors the exact coordinates and phases sent by the daemon.
(function(){
  if (window.self !== window.top) return;
  // mouse_visual.js is the single runtime renderer for the visible cursor.
  // Keep this older bridge dormant so it cannot fight the standalone script
  // over opacity or transform state on the shared Shadow DOM host.
  return;
  if (window.__omnibotMouseVisualLegacy) return;
  window.__omnibotMouseVisualLegacy = true;

  let host = null;
  let root = null;
  let pointer = null;
  let trail = null;
  let pressed = false;
  let last = null;
  let hideTimer = null;
  // The source PNG's arrow tip is about (20.5, 7) CSS pixels after its
  // 0.5x render. The holder is translated up by 2.5px, so compensate for
  // both the image and holder to keep the visible tip on the event point.
  const TIP_OFFSET_X = 0;
  const TIP_OFFSET_Y = 0;

  function ensureMouseVisual() {
    if (host && host.isConnected) return;
    host = document.createElement('div');
    host.id = 'omnibot-mouse-visual';
    host.setAttribute('aria-hidden', 'true');
    host.style.cssText = 'all:initial;position:fixed;inset:0;pointer-events:none;z-index:2147483646;contain:strict';
    root = host.attachShadow({mode: 'open'});
    root.innerHTML = `
      <style>
        :host { all: initial; }
        .pointer { position: absolute; left: 0; top: 0; width: 24px; height: 24px; opacity: 0; transform-origin: 12px 12px; will-change: transform, opacity; transition: opacity 100ms ease; }
        .pointer.visible { opacity: 1; }
        .pointer-holder { transform: none; }
        /* cursor-chat.png already contains the diagonal arrow geometry; do not rotate it again. */
        .pointer-asset { display: block; width: 19px; height: 25px; background: #050505; clip-path: polygon(0 0,0 84%,27% 65%,43% 100%,56% 94%,40% 57%,82% 58%); filter: drop-shadow(0 0 4px rgba(51,156,255,.95)) drop-shadow(0 0 13px rgba(51,156,255,.58)); user-select: none; }
        .pointer.down .pointer-asset { filter: drop-shadow(0 0 6px rgba(51,156,255,.98)) drop-shadow(0 0 15px rgba(51,156,255,.58)); }
        .trail { position: fixed; width: 7px; height: 7px; border-radius: 50%; background: rgba(45,212,191,.55); box-shadow: 0 0 9px rgba(45,212,191,.7); transform: translate(-50%,-50%); animation: fade 420ms ease-out forwards; }
        .pulse { position: fixed; width: 18px; height: 18px; border: 3px solid #fbbf24; border-radius: 50%; transform: translate(-50%,-50%); animation: pulse 520ms ease-out forwards; }
        @keyframes fade { from { opacity: .9; transform: translate(-50%,-50%) scale(1); } to { opacity: 0; transform: translate(-50%,-50%) scale(.25); } }
        @keyframes pulse { from { opacity: .95; transform: translate(-50%,-50%) scale(.35); } to { opacity: 0; transform: translate(-50%,-50%) scale(2.8); } }
      </style>
      <div class="pointer"><div class="pointer-holder"><div class="pointer-asset" aria-hidden="true"></div></div></div><div class="trail-layer"></div><div class="pulse-layer"></div>`;
    document.documentElement.appendChild(host);
    pointer = root.querySelector('.pointer');
    trail = root.querySelector('.trail-layer');
    return host;
  }

  function move(x, y, dragging) {
    ensureMouseVisual();
    pointer.classList.add('visible');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => pointer.classList.remove('visible'), 1200);
    pointer.style.transform = `translate3d(${x - TIP_OFFSET_X}px, ${y - TIP_OFFSET_Y}px, 0)`;
    pointer.classList.toggle('down', pressed || dragging);
    if (last && (Math.abs(last.x - x) + Math.abs(last.y - y) > 3)) {
      const dot = document.createElement('i'); dot.className = 'trail'; dot.style.left = `${x}px`; dot.style.top = `${y}px`;
      trail.appendChild(dot); setTimeout(() => dot.remove(), 450);
    }
    last = {x, y};
  }

  function pulse(x, y) {
    ensureMouseVisual();
    const layer = root.querySelector('.pulse-layer');
    const ring = document.createElement('i'); ring.className = 'pulse'; ring.style.left = `${x}px`; ring.style.top = `${y}px`;
    layer.appendChild(ring); setTimeout(() => ring.remove(), 560);
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.cmd !== 'mouse-visual') return;
    const event = msg.event || {};
    const x = Number(event.x), y = Number(event.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    if (event.type === 'press') { pressed = true; move(x, y, false); }
    else if (event.type === 'release') { move(x, y, false); pressed = false; pointer.classList.remove('down'); pulse(x, y); }
    else if (event.type === 'drag') move(x, y, true);
    else if (event.type === 'move') move(x, y, false);
    sendResponse && sendResponse({ok: true});
  });
})();

// Only the top document owns the visible cursor. Child-frame navigations must
// not ask the background worker to replay the tab's last pointer event onto
// the top document, otherwise an old click appears again at its stale point.
if (window.self === window.top) {
  try { chrome.runtime.sendMessage({cmd: 'mouse-visual-ready'}); } catch (_) {}
}

new MutationObserver(muts => {
  for (const m of muts) for (const n of m.addedNodes) {
    if (n.id === TID || (n.querySelector && n.querySelector('#' + TID))) {
      const el = n.id === TID ? n : n.querySelector('#' + TID);
      handle(el);
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

async function handle(el) {
  try {
    const text = el.textContent.trim();
    if (!text) { el.textContent = JSON.stringify({ ok: false, error: 'empty request' }); return; }
    const req = JSON.parse(text);
    const cmd = req.cmd;
    let resp;
    if (cmd === 'cdp') {
      resp = await chrome.runtime.sendMessage({ cmd: 'cdp', method: req.method, params: req.params || {}, tabId: req.tabId });
    } else if (cmd === 'batch') {
      resp = await chrome.runtime.sendMessage({ cmd: 'batch', commands: req.commands, tabId: req.tabId });
    } else if (cmd === 'tabs') {
      resp = await chrome.runtime.sendMessage({ cmd: 'tabs', method: req.method, tabId: req.tabId });
    } else if (cmd === 'networkCapture') {
      resp = await chrome.runtime.sendMessage({ cmd: 'networkCapture', op: req.op || req.method || 'logs', tabId: req.tabId });
    } else if (cmd === 'dialogCapture') {
      resp = await chrome.runtime.sendMessage({ cmd: 'dialogCapture', op: req.op || req.method || 'logs', tabId: req.tabId, accept: req.accept, promptText: req.promptText });
    } else if (cmd === 'devtools') {
      resp = await chrome.runtime.sendMessage({ cmd: 'devtools', method: req.method, tabId: req.tabId });
    } else {
      resp = { ok: false, error: 'unknown cmd: ' + cmd };
    }
    el.textContent = JSON.stringify(resp);
  } catch (e) {
    el.textContent = JSON.stringify({ ok: false, error: e.message });
  }
}
})();
