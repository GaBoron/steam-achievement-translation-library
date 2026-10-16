import { filterGames } from './catalog.js';
import { el, button, icon, statusMark } from './elements.js';
import { cover } from './game-covers.js';
import { t, formatDate, gameCount, variantLabel } from './i18n.js';
import { displayLanguages } from './languages.js';
import { clampPage, createPagination } from './pagination.js';
import { replaceContent, animateChange } from './motion.js';

const pageSize = 60;

export function createList({ games, locale, state, sortNode, invalidCount = 0, onReset, coverImages = {} }) {
  const root = el('section', { className: 'catalog-page', 'aria-labelledby': 'games-title' });
  const resultCount = el('p', { className: 'result-count', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
  const results = el('ul', { className: 'game-list', 'aria-label': t(locale, 'games') });
  const pagination = el('div', { className: 'list-pagination' });
  const topPagination = el('div', { className: 'list-pagination-top' });
  let disposed = false;

  const reset = () => {
    if (onReset) { onReset(); return; }
    Object.assign(state, { query: '', status: '', language: '', sort: 'updated', page: 1 });
    refresh();
  };

  const row = game => {
    const languages = displayLanguages(game.languages, locale);
    const href = `#/game/${game.appId}`;
    const contributors = el('span', { className: 'resource-contributors' });
    if (game.contributors.length) {
      contributors.append(`${t(locale, 'by')} `);
      game.contributors.slice(0, 2).forEach((name, index) => {
        if (index) contributors.append(', ');
        contributors.append(el('a', { href: `https://github.com/${encodeURIComponent(name)}`, target: '_blank', rel: 'noopener noreferrer' }, name));
      });
      if (game.contributors.length > 2) contributors.append(` ${t(locale, 'moreContributors', { count: locale === 'zh' ? game.contributors.length : game.contributors.length - 2 })}`);
    }
    const description = game.variants.map(variant => variant.description?.[locale]).filter(Boolean).join(' / ')
      || (game.variants.length > 1 ? game.variants.map(variant => variantLabel(variant, locale)).join(' / ') : '');
    return el('li', {}, el('article', { className: 'resource-row' },
      el('a', { className: 'resource-cover', href, tabindex: '-1', 'aria-hidden': 'true' }, cover(game.appId, false, coverImages[game.appId])),
      el('div', { className: 'resource-info' },
        el('div', { className: 'resource-title' }, el('h2', {}, el('a', { className: 'resource-title-link', href, title: game.name }, game.name)), contributors),
        el('p', { className: 'resource-summary', title: description }, `Steam App ID ${game.appId}`, description && el('span', {}, description))),
      el('div', { className: 'resource-tags', title: languages.join(', ') }, statusMark(game.status, locale),
        el('span', { className: 'resource-languages' }, icon('language'),
          languages.length ? languages.slice(0, 4).map(name => el('span', {}, name)) : t(locale, 'unknown'),
          languages.length > 4 && el('span', {}, `+${languages.length - 4}`))),
      el('div', { className: 'resource-stats' },
        el('span', {}, icon('trophy'), t(locale, 'achievements', { count: gameCount(game, locale) })),
        el('span', {}, icon('layers'), t(locale, 'variants', { count: game.variants.length })),
        el('time', { datetime: game.updatedAt, title: t(locale, 'updatedAt') }, icon('clock'), formatDate(game.updatedAt, locale))),
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
      topPagination.replaceChildren();
      replaceContent(pagination, el('div', { className: 'empty-state' }, icon('search'),
        el('h2', {}, t(locale, 'noResults')), el('p', {}, t(locale, 'noResultsNote')),
        button(t(locale, 'resetFilters'), reset)));
      return;
    }
    const pager = () => createPagination({ locale, page: state.page, totalPages, onChange: page => {
        state.page = page;
        refresh();
        results.querySelector('.resource-title-link')?.focus({ preventScroll: true });
        root.scrollIntoView({ block: 'start', behavior: 'instant' });
      } });
    replaceContent(topPagination, pager());
    replaceContent(pagination, pager());
  }

  root.append(el('h1', { id: 'games-title', className: 'sr-only' }, t(locale, 'games')),
    el('div', { className: 'list-heading' }, sortNode, topPagination), resultCount,
    results, pagination);
  if (invalidCount > 0) results.before(el('p', { className: 'catalog-advisory' }, icon('info'), t(locale, 'invalidEntries', { count: invalidCount })));
  refresh();
  return { node: root, refresh, dispose: () => { disposed = true; } };
}
