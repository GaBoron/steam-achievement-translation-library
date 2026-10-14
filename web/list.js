import { filterGames } from './catalog.js';
import { el, button, cover, icon, statusMark } from './elements.js';
import { t, formatDate, gameCount } from './i18n.js';
import { displayLanguages } from './languages.js';
import { clampPage, createPagination } from './pagination.js';
import { replaceContent, animateChange } from './motion.js';

const pageSize = 60;

export function createList({ games, locale, state, sortNode, invalidCount = 0, onReset }) {
  const root = el('section', { className: 'catalog-page', 'aria-labelledby': 'games-title' });
  const resultCount = el('p', { className: 'result-count', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
  const results = el('ul', { className: 'game-list', 'aria-label': t(locale, 'games') });
  const pagination = el('div', { className: 'list-pagination' });
  let disposed = false;

  const reset = () => {
    if (onReset) { onReset(); return; }
    Object.assign(state, { query: '', status: '', language: '', sort: 'updated', page: 1 });
    refresh();
  };

  const row = game => {
    const languages = displayLanguages(game.languages, locale);
    const languagesText = languages.length
      ? languages.slice(0, 4).join(locale === 'zh' ? '、' : ', ')
        + (languages.length > 4 ? ` +${languages.length - 4}` : '')
      : t(locale, 'unknown');
    const names = game.contributors.slice(0, 2).join(', ')
      + (game.contributors.length > 2 ? ` ${t(locale, 'moreContributors', { count: locale === 'zh' ? game.contributors.length : game.contributors.length - 2 })}` : '');
    const attribution = names && t(locale, 'byContributors', { names });
    return el('li', {}, el('a', { className: 'resource-row', href: `#/game/${game.appId}` },
      cover(game.appId),
      el('div', { className: 'resource-info' }, el('div', { className: 'resource-title' }, el('h2', {}, game.name),
          attribution && el('span', { className: 'resource-contributors', title: game.contributors.join(', ') }, attribution)),
        el('p', { className: 'resource-meta' }, el('span', {}, `Steam App ID ${game.appId}`),
          el('span', {}, t(locale, 'achievements', { count: gameCount(game, locale) })),
          el('span', {}, t(locale, 'variants', { count: game.variants.length })))),
      el('p', { className: 'resource-languages', title: languages.join(', ') }, languagesText),
      el('div', { className: 'resource-stats' }, statusMark(game.status, locale),
        el('time', { datetime: game.updatedAt, title: t(locale, 'updatedAt') }, formatDate(game.updatedAt, locale))),
    ));
  };

  function refresh() {
    if (disposed) return;
    const filtered = filterGames(games, state, locale);
    const totalPages = Math.ceil(filtered.length / pageSize);
    state.page = clampPage(state.page, totalPages);
    const label = t(locale, 'results', { count: filtered.length });
    if (resultCount.textContent !== label) {
      resultCount.textContent = label;
      animateChange(resultCount);
    }
    const start = (state.page - 1) * pageSize;
    replaceContent(results, ...filtered.slice(start, start + pageSize).map(row));
    if (!filtered.length) {
      replaceContent(pagination, el('div', { className: 'empty-state' }, icon('search'),
        el('h2', {}, t(locale, 'noResults')), el('p', {}, t(locale, 'noResultsNote')),
        button(t(locale, 'resetFilters'), reset)));
      return;
    }
    replaceContent(pagination, createPagination({ locale, page: state.page, totalPages, onChange: page => {
        state.page = page;
        refresh();
        results.querySelector('a')?.focus({ preventScroll: true });
        results.scrollTo({ top: 0, behavior: 'instant' });
      } }));
  }

  root.append(el('div', { className: 'list-heading' },
    el('div', { className: 'list-heading-title' }, el('h1', { id: 'games-title' }, t(locale, 'games')), resultCount),
    sortNode),
    results, pagination);
  if (invalidCount > 0) results.before(el('p', { className: 'catalog-advisory' }, icon('info'), t(locale, 'invalidEntries', { count: invalidCount })));
  refresh();
  return { node: root, refresh, dispose: () => { disposed = true; } };
}
