import { loadCatalog } from './catalog.js';
import { createPreferences } from './preferences.js';
import { createList } from './list.js';
import { createDetail } from './detail.js';
import { el, button, externalLink, icon, pageState, repository, selectField } from './elements.js';
import { t } from './i18n.js';

const preferences = createPreferences();
const main = document.getElementById('main');
const header = document.getElementById('header');
const footer = document.getElementById('footer');
const listState = { query: '', status: '', language: '', sort: 'updated' };
let catalog;
let view;
let failed = false;
let listScroll = 0;
let previousGame = false;
let revision = 'main';

const metaAbort = new AbortController();
const metaTimeout = setTimeout(() => metaAbort.abort(), 5000);
const loadRevision = fetch('./site-meta.json', { cache: 'no-cache', signal: metaAbort.signal })
  .then(response => response.ok ? response.json() : null)
  .then(meta => { if (/^[a-f0-9]{40}$/.test(meta?.revision)) revision = meta.revision; })
  .catch(() => {}).finally(() => clearTimeout(metaTimeout));

function renderShell() {
  const locale = preferences.locale;
  document.title = t(locale, 'title');
  document.querySelector('.skip-link').textContent = t(locale, 'skip');
  document.querySelector('meta[name="description"]').content = t(locale, 'search');
  header.replaceChildren(el('div', { className: 'header-inner' },
    el('a', { className: 'brand', href: '#/' }, el('span', { className: 'brand-icon' }, icon('translate')), el('span', {}, t(locale, 'title'))),
    el('div', { className: 'header-actions' },
      selectField(t(locale, 'theme'), [['auto', t(locale, 'auto')], ['light', t(locale, 'light')], ['dark', t(locale, 'dark')]], preferences.theme, value => preferences.setTheme(value), 'header-field'),
      selectField(t(locale, 'language'), [['zh', '简体中文'], ['en', 'English']], locale, value => {
        preferences.setLocale(value);
        renderShell();
        renderRoute(false);
        header.querySelector('.locale-field select').focus();
      }, 'header-field locale-field'),
      externalLink('GitHub', repository, 'icon-text', 'github'))));
  header.querySelector('a[target]').setAttribute('aria-label', t(locale, 'github'));
  footer.replaceChildren(el('p', {}, t(locale, 'footer')),
    el('div', { className: 'footer-links' },
      el('a', { href: `${repository}/blob/main/README${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'usageGuide')),
      el('a', { href: `${repository}/blob/main/CONTRIBUTING${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'contribute'))));
}

function route() {
  const match = /^#\/game\/(\d+)(?:\/([a-z0-9][a-z0-9-]{0,63}))?\/?$/.exec(location.hash);
  return match ? { appId: match[1], variantId: match[2] } : location.hash && location.hash !== '#/' && location.hash !== '#main' ? { invalid: true } : {};
}

function renderRoute(navigating = true) {
  const current = route();
  const locale = preferences.locale;
  if (navigating && !previousGame) listScroll = window.scrollY;
  view?.dispose?.();
  view = null;
  main.setAttribute('aria-busy', String(!catalog && !failed));
  if (!catalog) {
    main.replaceChildren(failed
      ? pageState(locale, 'loadError', 'loadErrorNote', button(t(locale, 'retry'), initialize, 'tonal'))
      : pageState(locale, 'loading'));
    return;
  }
  const game = catalog.games.find(entry => entry.appId === current.appId);
  if (current.invalid || (current.appId && (!game || current.variantId && !game.variants.some(variant => variant.id === current.variantId)))) {
    main.replaceChildren(pageState(locale, 'notFound', 'notFoundNote', el('a', { className: 'button tonal', href: '#/' }, t(locale, 'back'))));
    previousGame = true;
  } else {
    view = game ? createDetail({ game, locale, revision, variantId: current.variantId, onVariant: variantId => {
      history.replaceState(null, '', `#/game/${game.appId}/${variantId}`);
    } }) : createList({ ...catalog, locale, state: listState });
    main.replaceChildren(view.node);
    document.title = game ? `${game.name} · ${t(locale, 'title')}` : t(locale, 'title');
    previousGame = Boolean(game);
  }
  if (navigating) {
    window.scrollTo({ top: previousGame ? 0 : listScroll, behavior: 'instant' });
    const heading = main.querySelector('h1');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({ preventScroll: true });
  }
}

async function initialize() {
  failed = false;
  renderRoute(false);
  try { [catalog] = await Promise.all([loadCatalog(), loadRevision]); } catch { failed = true; }
  renderRoute(false);
}

window.addEventListener('hashchange', () => renderRoute());
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  main.focus({ preventScroll: true });
  main.scrollIntoView({ behavior: 'instant', block: 'start' });
});
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && view?.focusSearch) {
    event.preventDefault();
    view.focusSearch();
  }
});
renderShell();
initialize();
