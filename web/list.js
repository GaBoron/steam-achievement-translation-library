import { filterGames } from './catalog.js';
import { el, button, cover, icon, selectField, statusMark } from './elements.js';
import { t, languageName, formatDate, statusLabel, gameCount } from './i18n.js';

const pageSize = 60;

export function createList({ games, locale, state, invalidCount = 0 }) {
  const root = el('section', { className: 'catalog-page', 'aria-labelledby': 'games-title' });
  const resultCount = el('p', { className: 'result-count', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
  const results = el('ul', { className: 'game-list', 'aria-label': t(locale, 'games') });
  const more = el('div', { className: 'list-pagination' });
  let visible = state.visible || pageSize;
  let filtered = [];
  let frame;

  const search = el('input', {
    type: 'search', value: state.query, placeholder: t(locale, 'search'), 'aria-label': t(locale, 'search'),
    autocomplete: 'off', spellcheck: 'false',
    oninput: event => {
      state.query = event.target.value;
      clear.hidden = !state.query;
      visible = pageSize;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(refresh);
    },
  });
  const clear = button('', () => {
    state.query = '';
    search.value = '';
    clear.hidden = true;
    visible = pageSize;
    refresh();
    search.focus();
  }, 'icon-button', 'close');
  clear.setAttribute('aria-label', t(locale, 'clearSearch'));
  clear.hidden = !state.query;
  const searchBar = el('div', { className: 'search-bar' }, icon('search'), search,
    el('kbd', { className: 'search-shortcut', 'aria-hidden': 'true' }, 'Ctrl K'), clear);

  const change = key => value => {
    state[key] = value;
    visible = pageSize;
    refresh();
  };
  const statuses = [...new Set(['current', 'outdated', 'possibly_ineffective', ...games.map(game => game.status)])];
  const languages = [...new Set(games.flatMap(game => game.languages))].sort((a, b) =>
    languageName(a, locale).localeCompare(languageName(b, locale), locale));
  const filters = el('div', { className: 'filters' },
    selectField(t(locale, 'status'), [['', t(locale, 'allStatuses')], ...statuses.map(status => [status, statusLabel(status, locale)])], state.status, change('status')),
    selectField(t(locale, 'languages'), [['', t(locale, 'allLanguages')], ...languages.map(language => [language, languageName(language, locale)])], state.language, change('language')),
    selectField(t(locale, 'sort'), [['updated', t(locale, 'updated')], ['name', t(locale, 'name')], ['achievements', t(locale, 'achievementsSort')]], state.sort, change('sort'), 'sort-field'),
  );

  const reset = () => {
    Object.assign(state, { query: '', status: '', language: '', sort: 'updated' });
    search.value = '';
    clear.hidden = true;
    const selects = filters.querySelectorAll('select');
    selects[0].value = '';
    selects[1].value = '';
    selects[2].value = 'updated';
    visible = pageSize;
    refresh();
    search.focus();
  };

  const row = game => {
    const languagesText = game.languages.length
      ? game.languages.slice(0, 2).map(language => languageName(language, locale)).join(locale === 'zh' ? '、' : ', ')
        + (game.languages.length > 2 ? ` +${game.languages.length - 2}` : '')
      : t(locale, 'unknown');
    return el('li', {}, el('a', { className: 'game-row', href: `#/game/${game.appId}` },
      cover(game.appId),
      el('div', { className: 'game-text' }, el('h2', {}, game.name),
        el('p', { className: 'game-meta' }, el('span', {}, `App ID ${game.appId}`),
          el('span', {}, t(locale, 'achievements', { count: gameCount(game, locale) })),
          game.variants.length > 1 && el('span', {}, t(locale, 'variants', { count: game.variants.length })))),
      el('div', { className: 'game-status' }, statusMark(game.status, locale)),
      el('p', { className: 'game-languages', title: game.languages.map(code => languageName(code, locale)).join(', ') }, languagesText),
      el('time', { className: 'game-date', datetime: game.updatedAt }, formatDate(game.updatedAt, locale)),
      el('span', { className: 'row-arrow' }, icon('arrow')),
    ));
  };

  function refresh() {
    filtered = filterGames(games, state, locale);
    state.visible = visible;
    resultCount.textContent = t(locale, 'results', { count: filtered.length });
    results.replaceChildren(...filtered.slice(0, visible).map(row));
    more.replaceChildren();
    if (!filtered.length) {
      more.append(el('div', { className: 'empty-state' }, icon('search'),
        el('h2', {}, t(locale, 'noResults')), el('p', {}, t(locale, 'noResultsNote')),
        button(t(locale, 'resetFilters'), reset)));
      return;
    }
    more.append(el('p', { className: 'muted' }, t(locale, 'showing', { shown: Math.min(visible, filtered.length), total: filtered.length })));
    if (visible < filtered.length) {
      more.append(button(t(locale, 'showMore'), () => {
        const firstNewIndex = visible;
        visible += pageSize;
        refresh();
        results.children[firstNewIndex]?.querySelector('a')?.focus({ preventScroll: true });
      }, 'tonal'));
    }
  }

  root.append(el('div', { className: 'section-heading' }, el('h1', { id: 'games-title' }, t(locale, 'games')), resultCount),
    searchBar, filters,
    invalidCount > 0 && el('p', { className: 'catalog-advisory' }, icon('info'), t(locale, 'invalidEntries', { count: invalidCount })),
    results, more);
  refresh();
  return { node: root, focusSearch: () => search.focus(), dispose: () => cancelAnimationFrame(frame) };
}
