function switchTab(groupId, btn, name) {
  var group = document.getElementById(groupId);
  if (!group) return;
  group.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
  btn.classList.add('active');
  var parent = group.parentElement;
  parent.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
  var target = parent.querySelector('#tab-' + name);
  if (target) target.classList.add('active');
}

document.querySelectorAll('.tab[data-group]').forEach(function(btn) {
  btn.addEventListener('click', function() {
    switchTab(this.dataset.group, this, this.dataset.tab);
  });
});

document.querySelectorAll('.tab-link').forEach(function(link) {
  link.addEventListener('click', function(e) {
    e.preventDefault();
    var tabName = this.dataset.tab;
    var section = document.getElementById('install-skills');
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(function() {
      var group = document.getElementById('skills-tabs');
      if (!group) return;
      var tabBtn = group.querySelector('.tab[data-tab="' + tabName + '"]');
      if (tabBtn) switchTab('skills-tabs', tabBtn, tabName);
    }, 300);
  });
});

var sections = document.querySelectorAll('h1[id], h2[id], h3[id]');
var links = document.querySelectorAll('.sidebar a');
window.addEventListener('scroll', function() {
  var current = '';
  sections.forEach(function(s) {
    if (window.scrollY >= s.offsetTop - 100) current = s.id;
  });
  links.forEach(function(l) {
    if (!l.classList.contains('tab-link')) {
      l.classList.toggle('active', l.getAttribute('href') === '#' + current);
    }
  });
});

// --- i18n ---
function applyHelpLang(lang) {
  lang = normalizeHelpLang(lang);
  document.documentElement.lang = lang === 'zh_CN' ? 'zh-CN' : 'en';
  // Use Chrome's built-in i18n with the locale directory
  // chrome.i18n.getMessage uses the UI locale, not configurable at runtime.
  // So we fetch the messages.json directly for the selected language.
  fetch(chrome.runtime.getURL('_locales/' + lang + '/messages.json'))
    .then(function(r) { return r.json(); })
    .then(function(msgs) {
      function t(key) {
        var entry = msgs[key];
        return entry ? entry.message : key;
      }
      document.querySelectorAll('[data-i18n]').forEach(function(el) {
        var key = el.dataset.i18n;
        var text = t(key);
        var arg = el.dataset.i18nArg;
        if (arg) text = text.replace('$agent$', arg);
        el.textContent = text;
      });
      document.title = t('help_title');
    });
}

function normalizeHelpLang(lang) {
  return lang === 'zh' ? 'zh_CN' : lang;
}

document.getElementById('helpLangSelect').addEventListener('change', function(e) {
  var lang = e.target.value;
  chrome.storage.local.set({ lang: lang });
  applyHelpLang(lang);
});

// Init language from storage or detect from browser
chrome.storage.local.get(['lang'], function(result) {
  var lang = normalizeHelpLang(result.lang);
  if (!lang) {
    var ui = chrome.i18n.getUILanguage();
    lang = ui && ui.startsWith('zh') ? 'zh_CN' : 'en';
  }
  document.getElementById('helpLangSelect').value = lang;
  applyHelpLang(lang);
});
