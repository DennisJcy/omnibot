// offscreen.js - runs inside the offscreen document. Has its own browsing context
// and can access the clipboard via document.execCommand('paste'/'copy') which
// works in extension pages with clipboardRead/clipboardWrite permissions
// without requiring document focus or user activation.

function _readClipboardViaExecCommand() {
  const ta = document.createElement('textarea');
  ta.style.position = 'fixed';
  ta.style.top = '0';
  ta.style.left = '0';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.focus();
  const ok = document.execCommand('paste');
  const text = ta.value;
  document.body.removeChild(ta);
  if (!ok) throw new Error('execCommand paste returned false');
  return text;
}

function _writeClipboardViaExecCommand(text) {
  const ta = document.createElement('textarea');
  ta.value = String(text || '');
  ta.style.position = 'fixed';
  ta.style.top = '0';
  ta.style.left = '0';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(ta);
  if (!ok) throw new Error('execCommand copy returned false');
}

async function _readClipboardViaNavigator() {
  return await navigator.clipboard.readText();
}

async function _writeClipboardViaNavigator(text) {
  await navigator.clipboard.writeText(String(text || ''));
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.cmd !== 'clipboard') return false;
  (async () => {
    const op = msg.method;
    try {
      let text = '';
      if (op === 'readText') {
        try {
          text = _readClipboardViaExecCommand();
        } catch (e) {
          text = await _readClipboardViaNavigator();
        }
        sendResponse({ ok: true, data: { text: String(text || '') } });
      } else if (op === 'writeText') {
        try {
          _writeClipboardViaExecCommand(msg.text);
        } catch (e) {
          await _writeClipboardViaNavigator(msg.text);
        }
        sendResponse({ ok: true, data: { text: String(msg.text || '') } });
      } else {
        sendResponse({ ok: false, error: 'unknown clipboard method: ' + op });
      }
    } catch (e) {
      sendResponse({ ok: false, error: String(e && e.message || e) });
    }
  })();
  return true;
});

// keepalive ping
setInterval(() => {
  chrome.runtime.sendMessage({ cmd: 'offscreen_ping' }).catch(() => {});
}, 20000);

chrome.runtime.sendMessage({ cmd: 'offscreen_ping' }).catch(() => {});
