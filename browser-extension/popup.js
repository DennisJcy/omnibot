let _msgs = null;
let _currentLang = 'zh_CN';

document.addEventListener('DOMContentLoaded', () => {
  const manifest = chrome.runtime.getManifest();
  document.getElementById('version').textContent = 'v' + manifest.version;

  document.getElementById('reconnectBtn').addEventListener('click', reconnect);
  document.getElementById('helpBtn').addEventListener('click', openHelp);
  document.getElementById('langSelect').addEventListener('change', (e) => {
    const lang = e.target.value;
    chrome.storage.local.set({ lang });
    initLang();
  });

  initLang();
});

async function initLang() {
  const { lang } = await chrome.storage.local.get(['lang']);
  const resolved = normalizeLang(lang || detectLang());
  document.getElementById('langSelect').value = resolved;
  await loadLang(resolved);
  applyLang();
  refreshUI();
}

function normalizeLang(lang) {
  return lang === 'zh' ? 'zh_CN' : lang;
}

function detectLang() {
  const ui = chrome.i18n.getUILanguage();
  return ui && ui.startsWith('zh') ? 'zh_CN' : 'en';
}

async function loadLang(lang) {
  _currentLang = lang;
  try {
    const resp = await fetch(chrome.runtime.getURL('_locales/' + lang + '/messages.json'));
    _msgs = await resp.json();
  } catch (e) {
    _msgs = {};
  }
}

function t(key, ...args) {
  const entry = _msgs ? _msgs[key] : null;
  if (!entry) return key;
  let text = entry.message;
  if (args.length) {
    const placeholders = entry.placeholders || {};
    Object.keys(placeholders).forEach((ph, i) => {
      text = text.replace(new RegExp('\\$' + ph + '\\$', 'g'), args[i] != null ? args[i] : '');
    });
  }
  return text;
}

function applyLang() {
  document.documentElement.lang = _currentLang === 'zh_CN' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-ph]').forEach((el) => {
    el.placeholder = t(el.dataset.i18nPh);
  });
}

async function refreshUI() {
  const status = await chrome.runtime.sendMessage({ cmd: 'get_status' }).catch(() => ({ connected: false, port: null }));
  updateConnection(status);
}

function updateConnection(status) {
  const dot = document.getElementById('dot');
  const text = document.getElementById('connText');
  const port = document.getElementById('portDisplay');
  if (status && status.connected) {
    dot.className = 'dot on';
    text.textContent = t('connected');
    port.textContent = t('port_label', status.port || '--');
  } else {
    dot.className = 'dot off';
    text.textContent = t('disconnected');
    port.textContent = '--';
  }
}

async function reconnect() {
  await chrome.runtime.sendMessage({ cmd: 'reconnect' }).catch(() => {});
  setTimeout(() => refreshUI(), 1500);
}

function openHelp() {
  chrome.tabs.create({ url: chrome.runtime.getURL('help.html') });
}
