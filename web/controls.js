/** The search and filters belong to the persistent application shell. */
import { el, button, icon } from './elements.js';
import { createSelect } from './select.js';
import { createFilterGroup } from './filter-group.js';
import { bindDisclosure } from './motion.js';
import { t, statusLabel } from './i18n.js';
import { isStandardLanguage, languageName, OTHER_LANGUAGE } from './languages.js';

function catalogOptions(games, locale) {
  const statuses = [...new Set(['current', 'outdated', 'possibly_ineffective', ...games.map(game => game.status)])];
  const codes = [...new Set(games.flatMap(game => game.languages))];
  const languages = codes.filter(isStandardLanguage).sort((a, b) =>
    languageName(a, locale).localeCompare(languageName(b, locale), locale)).map(code => [code, languageName(code, locale)]);
  if (codes.some(code => !isStandardLanguage(code))) languages.push([OTHER_LANGUAGE, languageName(OTHER_LANGUAGE, locale)]);
  return {
    statuses: [['', t(locale, 'allStatuses')], ...statuses.map(status => [status, statusLabel(status, locale)])],
    languages: [['', t(locale, 'allLanguages')], ...languages],
  };
}

export function createCatalogControls({ games, locale, state, onChange }) {
  const root = el('div', { className: 'catalog-filters' });
  const mobile = matchMedia('(max-width: 1023px)');
  const lifetime = new AbortController();
  let frame;
  const changed = () => {
    state.page = 1;
    onChange();
  };
  const search = el('input', {
    type: 'search', value: state.query, placeholder: t(locale, 'search'), 'aria-label': t(locale, 'search'),
    autocomplete: 'off', spellcheck: 'false',
    oninput: event => {
      state.query = event.target.value;
      clear.hidden = !state.query;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(changed);
    },
  });
  const clear = button('', () => {
    state.query = '';
    search.value = '';
    clear.hidden = true;
    changed();
    search.focus();
  }, 'icon-button', 'close');
  clear.setAttribute('aria-label', t(locale, 'clearSearch'));
  clear.hidden = !state.query;
  const options = catalogOptions(games, locale);
  const change = key => value => { state[key] = value; changed(); };
  const fields = [
    createFilterGroup({ label: t(locale, 'status'), options: options.statuses, value: state.status, onChange: change('status') }),
    createFilterGroup({ label: t(locale, 'languages'), options: options.languages, value: state.language, onChange: change('language'), className: 'language-filter' }),
  ];
  const sort = createSelect({ label: t(locale, 'sort'), options: [['updated', t(locale, 'updated')], ['name', t(locale, 'name')], ['achievements', t(locale, 'achievementsSort')]], value: state.sort, onChange: change('sort'), className: 'sort-field' });
  const summary = el('summary', {}, icon('filter'), el('span', {}, t(locale, 'filters')));
  const panel = el('details', { className: 'filter-panel' }, summary, el('div', { className: 'filter-content' }, fields.map(field => field.node)));
  panel.open = !mobile.matches;
  let disclosure = bindDisclosure(panel);
  const setOpen = open => {
    disclosure();
    panel.open = open;
    disclosure = bindDisclosure(panel);
  };
  mobile.addEventListener('change', () => setOpen(!mobile.matches), { signal: lifetime.signal });
  document.addEventListener('pointerdown', event => {
    if (mobile.matches && panel.open && !root.contains(event.target)) setOpen(false);
  }, { signal: lifetime.signal });
  document.addEventListener('focusin', event => {
    if (mobile.matches && panel.open && !root.contains(event.target)) setOpen(false);
  }, { signal: lifetime.signal });
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape' && mobile.matches && panel.open) {
      event.preventDefault(); setOpen(false); summary.focus();
    }
  });
  const resetButton = button(t(locale, 'clear'), () => reset(), 'text-button filter-reset');
  resetButton.setAttribute('aria-label', t(locale, 'resetFilters'));
  root.append(panel, resetButton);
  const searchNode = el('div', { className: 'search-bar' }, icon('search'), search,
    el('kbd', { className: 'search-shortcut', 'aria-hidden': 'true' }, 'Ctrl K'), clear);
  function reset() {
    Object.assign(state, { query: '', status: '', language: '', sort: 'updated', page: 1 });
    search.value = '';
    clear.hidden = true;
    fields[0].setValue('');
    fields[1].setValue('');
    sort.setValue('updated');
    if (mobile.matches) setOpen(false);
    changed();
    search.focus();
  }
  return {
    node: root, search: searchNode, sort: sort.node,
    focusSearch: () => search.focus(),
    setGames(data) {
      const next = catalogOptions(data, locale);
      fields[0].setOptions(next.statuses);
      fields[1].setOptions(next.languages);
    },
    reset,
    dispose() { cancelAnimationFrame(frame); lifetime.abort(); disclosure(); sort.dispose(); },
  };
}
