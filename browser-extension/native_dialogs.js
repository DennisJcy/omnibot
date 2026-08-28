// Capture native JavaScript dialogs while preserving browser behavior.
(function() {
  if (window.__omnibotNativeDialogsInstalled) return;
  window.__omnibotNativeDialogsInstalled = true;

  // Keep closed roots inspectable by Omnibot's read path without changing the
  // mode returned to the page or exposing an enumerable property.
  const nativeAttachShadow = Element.prototype.attachShadow;
  if (nativeAttachShadow && !Element.prototype.__omnibotAttachShadowWrapped) {
    const attachShadow = function(init) {
      const root = nativeAttachShadow.call(this, init);
      if (init && init.mode === 'closed') {
        try {
          Object.defineProperty(this, '__omnibotClosedShadowRoot', {
            configurable: false,
            enumerable: false,
            value: root
          });
        } catch (_) {}
      }
      return root;
    };
    Object.defineProperty(attachShadow, '__omnibotWrapped', { value: true });
    Element.prototype.attachShadow = attachShadow;
    Object.defineProperty(Element.prototype, '__omnibotAttachShadowWrapped', { value: true });
  }

  const nativeAlert = window.alert.bind(window);
  const nativeConfirm = window.confirm.bind(window);
  const nativePrompt = window.prompt.bind(window);

  function notify(type, message, defaultValue) {
    const payload = {
      type,
      message: String(message ?? ''),
      defaultPrompt: defaultValue == null ? '' : String(defaultValue),
      timestamp: Date.now()
    };
    try {
      document.documentElement.setAttribute('data-omnibot-last-dialog', JSON.stringify(payload));
    } catch (_) {}
    try {
      window.postMessage({
        source: 'omnibot-native-dialog',
        ...payload
      }, '*');
    } catch (_) {}
    try {
      document.dispatchEvent(new CustomEvent('__omnibot_native_dialog__', {
        bubbles: true,
        composed: true,
        detail: payload
      }));
    } catch (_) {}
  }

  window.alert = function(message) {
    notify('alert', message, '');
    return nativeAlert(message);
  };

  window.confirm = function(message) {
    notify('confirm', message, '');
    return nativeConfirm(message);
  };

  window.prompt = function(message, defaultValue) {
    notify('prompt', message, defaultValue);
    return nativePrompt(message, defaultValue);
  };
})();
