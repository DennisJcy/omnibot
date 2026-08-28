// Standalone cursor bridge, independent from the larger content bridge.
(() => {
  if (window.top !== window.self || window.__omnibotStandaloneMouseVisual) return;
  window.__omnibotStandaloneMouseVisual = true;
  let host = document.getElementById('omnibot-mouse-visual');
  let root = host && host.shadowRoot;
  if (!host || !root) {
    host = document.createElement('div');
    host.id = 'omnibot-mouse-visual';
    host.setAttribute('aria-hidden', 'true');
    host.style.cssText = 'all:initial;position:fixed;inset:0;pointer-events:none;z-index:2147483647;contain:strict';
    root = host.attachShadow({mode: 'open'});
    root.innerHTML = `<style>
    .pointer{position:absolute;left:0;top:0;width:24px;height:24px;transform-origin:12px 12px;will-change:transform}
    .asset-holder{transform:translate3d(12px,-2.5px,0)}
    .asset{display:block;width:23px;height:24px;filter:drop-shadow(0 0 6px rgba(51,156,255,.9)) drop-shadow(0 0 15px rgba(51,156,255,.48));transform:rotate(44deg) scale(1);transform-origin:0 0;user-select:none}
    .ring{position:fixed;width:18px;height:18px;border:3px solid #fbbf24;border-radius:50%;transform:translate(-50%,-50%);animation:omni-mouse-pulse 520ms ease-out forwards}
    @keyframes omni-mouse-pulse{from{opacity:.95;transform:translate(-50%,-50%) scale(.35)}to{opacity:0;transform:translate(-50%,-50%) scale(2.8)}}
    </style><div class="pointer"><div class="asset-holder"><img class="asset" draggable="false" aria-hidden="true"></div></div><div class="rings"></div>`;
    document.documentElement.appendChild(host);
    root.querySelector('.asset').src = chrome.runtime.getURL('cursor-chat.png');
  }
  // content.js owns the legacy-compatible host when it is already present.
  // Do not attach a second listener or override its visibility state.
  if (root.querySelector('.pointer-asset')) return;
  const pointer = root.querySelector('.pointer');
  let hideTimer = null;
  pointer.style.opacity = '0';
  pointer.style.transition = 'opacity 100ms ease';
  function renderMouseVisual(event) {
    const x = Number(event.x), y = Number(event.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    pointer.style.opacity = '1';
    clearTimeout(hideTimer);
    // A coordinate action may take longer than the CDP round-trip itself.
    // Keep the cursor visible long enough for people to observe it after the
    // CLI responds, without leaving a stale pointer on the page indefinitely.
    hideTimer = setTimeout(() => { pointer.style.opacity = '0'; }, 4500);
    // Match ChatGPT's resting transform: its outer -44deg rotation cancels
    // the +44deg image rotation, leaving the native diagonal arrow intact.
    pointer.style.transform = `translate3d(${x - 12}px,${y - 12}px,0) rotate(-44deg)`;
    if (event.type === 'release') {
      const ring = document.createElement('i');
      ring.className = 'ring'; ring.style.left = `${x}px`; ring.style.top = `${y}px`;
      root.querySelector('.rings').appendChild(ring);
      setTimeout(() => ring.remove(), 560);
    }
  }
  // The background reinjection fallback uses this hook to distinguish a
  // current content script from a stale one left behind by extension reload.
  window.__omnibotMouseVisualRender = renderMouseVisual;
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.cmd !== 'mouse-visual') return;
    renderMouseVisual(msg.event || {});
  });
  try { chrome.runtime.sendMessage({cmd: 'mouse-visual-ready'}); } catch (_) {}
})();
