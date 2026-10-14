import { loadCatalog } from './catalog.js';
import { createPreferences } from './preferences.js';
import { createList } from './list.js';
import { createDetail } from './detail.js';
import { createCatalogControls } from './controls.js';
import { createSelect } from './select.js';
import { replaceContent } from './motion.js';
import { el, button, externalLink, icon, pageState, repository } from './elements.js';
import { t } from './i18n.js';

const preferences = createPreferences();
const main = document.getElementById('main');
const header = document.getElementById('header');
const footer = document.getElementById('footer');
const toolbar = document.getElementById('toolbar');
const listState = { query: '', status: '', language: '', sort: 'updated', page: 1 };
let catalog;
let view;
let failed = false;
let listScroll = 0;
let previousGame = false;
let previousAppId;
let revision = 'main';
let controls;
let headerFields = [];
const scroller = () => main.querySelector('.game-list') || main;

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
  headerFields.forEach(field => field.dispose());
  const themeField = createSelect({ label: t(locale, 'theme'), options: [['auto', t(locale, 'auto')], ['light', t(locale, 'light')], ['dark', t(locale, 'dark')]], value: preferences.theme, onChange: value => preferences.setTheme(value), className: 'header-field' });
  const localeField = createSelect({ label: t(locale, 'language'), options: [['zh', '简体中文'], ['en', 'English']], value: locale, className: 'header-field locale-field', onChange: value => {
    preferences.setLocale(value);
    renderShell();
    renderControls();
    renderRoute(false);
    headerFields[1].focus();
  } });
  headerFields = [themeField, localeField];
  replaceContent(header, el('div', { className: 'header-inner' },
    el('a', { className: 'brand', href: '#/', 'aria-label': t(locale, 'title') }, el('span', { className: 'brand-icon' }, icon('translate')), el('span', {}, t(locale, 'title'))),
    el('div', { className: 'header-actions' },
      themeField.node, localeField.node,
      externalLink('GitHub', repository, 'icon-text', 'github'))));
  header.querySelector('a[target]').setAttribute('aria-label', t(locale, 'github'));
  replaceContent(footer, el('div', { className: 'footer-inner' }, el('p', {}, t(locale, 'footer')),
    el('div', { className: 'footer-links' },
      el('a', { href: `${repository}/blob/main/README${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'usageGuide')),
      el('a', { href: `${repository}/blob/main/CONTRIBUTING${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'contribute')))));
}

function renderControls() {
  controls?.dispose();
  controls = createCatalogControls({ games: catalog?.games || [], locale: preferences.locale, state: listState, onChange: () => {
    if (!catalog) return;
    const current = route();
    if (current.appId || current.invalid) {
      history.pushState(null, '', '#/');
      renderRoute(false);
    } else view?.refresh?.();
    scroller().scrollTo({ top: 0, behavior: 'instant' });
  } });
  toolbar.setAttribute('aria-label', t(preferences.locale, 'search'));
  replaceContent(toolbar, controls.node);
}

function route() {
  const match = /^#\/game\/(\d+)(?:\/([a-z0-9][a-z0-9-]{0,63}))?\/?$/.exec(location.hash);
  return match ? { appId: match[1], variantId: match[2] } : location.hash && location.hash !== '#/' && location.hash !== '#main' ? { invalid: true } : {};
}

function renderRoute(navigating = true) {
  const current = route();
  const locale = preferences.locale;
  const scroll = scroller().scrollTop;
  if (navigating && !previousGame) listScroll = scroll;
  view?.dispose?.();
  view = null;
  main.setAttribute('aria-busy', String(!catalog && !failed));
  if (!catalog) {
    replaceContent(main, failed
      ? pageState(locale, 'loadError', 'loadErrorNote', button(t(locale, 'retry'), initialize, 'tonal'))
      : pageState(locale, 'loading'));
    return;
  }
  const game = catalog.games.find(entry => entry.appId === current.appId);
  if (current.invalid || (current.appId && (!game || current.variantId && !game.variants.some(variant => variant.id === current.variantId)))) {
    replaceContent(main, pageState(locale, 'notFound', 'notFoundNote', el('a', { className: 'button tonal', href: '#/' }, t(locale, 'back'))));
    document.title = t(locale, 'title');
    previousGame = true;
  } else {
    view = game ? createDetail({ game, locale, revision, variantId: current.variantId, onVariant: variantId => {
      history.replaceState(null, '', `#/game/${game.appId}/${variantId}`);
    } }) : createList({ ...catalog, locale, state: listState, onReset: () => controls.reset() });
    replaceContent(main, view.node);
    document.title = game ? `${game.name} · ${t(locale, 'title')}` : t(locale, 'title');
    previousGame = Boolean(game);
    if (game) previousAppId = game.appId;
  }
  if (navigating) {
    scroller().scrollTo({ top: previousGame ? 0 : listScroll, behavior: 'instant' });
    const focus = (!previousGame && previousAppId && main.querySelector(`a[href="#/game/${previousAppId}"]`)) || main.querySelector('h1');
    if (focus?.tagName === 'H1') focus.setAttribute('tabindex', '-1');
    focus?.focus({ preventScroll: true });
  } else scroller().scrollTop = scroll;
}

async function initialize() {
  failed = false;
  renderRoute(false);
  try { [catalog] = await Promise.all([loadCatalog(), loadRevision]); } catch { failed = true; }
  if (catalog) controls.setGames(catalog.games);
  renderRoute(false);
}

window.addEventListener('hashchange', () => renderRoute());
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  main.focus({ preventScroll: true });
  scroller().scrollTo({ top: 0, behavior: 'instant' });
});
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    controls.focusSearch();
  }
});
renderShell();
renderControls();
initialize();
