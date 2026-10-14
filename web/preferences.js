import { transitionTheme } from './motion.js';

const key = 'satl-web-preferences';

export function createPreferences() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch { /* Storage is optional. */ }
  const requestedLocale = new URLSearchParams(location.search).get('lang');
  const systemLocale = navigator.language?.toLowerCase().startsWith('zh') ? 'zh' : 'en';
  let locale = ['zh', 'en'].includes(requestedLocale) ? requestedLocale
    : ['zh', 'en'].includes(saved.locale) ? saved.locale : systemLocale;
  let theme = ['auto', 'light', 'dark'].includes(saved.theme) ? saved.theme : 'auto';
  const systemTheme = matchMedia('(prefers-color-scheme: dark)');
  const apply = () => {
    document.documentElement.dataset.theme = theme === 'auto' ? (systemTheme.matches ? 'dark' : 'light') : theme;
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
  };
  const save = () => {
    try { localStorage.setItem(key, JSON.stringify({ locale, theme })); } catch { /* Private browsing remains usable. */ }
    apply();
  };
  systemTheme.addEventListener('change', () => { if (theme === 'auto') transitionTheme(apply); });
  apply();
  return {
    get locale() { return locale; },
    get theme() { return theme; },
    setLocale(value) {
      if (!['zh', 'en'].includes(value)) return;
      locale = value;
      const url = new URL(location.href);
      url.searchParams.set('lang', value);
      history.replaceState(null, '', url);
      save();
    },
    setTheme(value) {
      if (!['auto', 'light', 'dark'].includes(value)) return;
      theme = value;
      transitionTheme(save);
    },
  };
}
