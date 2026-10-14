import { el, button } from './elements.js';
import { t } from './i18n.js';

export function clampPage(page, totalPages) {
  const last = Math.max(1, Math.trunc(totalPages) || 1);
  return Math.min(last, Math.max(1, Number.isFinite(page) ? Math.trunc(page) : 1));
}

export function pageNumbers(page, totalPages) {
  const last = Math.max(1, Math.trunc(totalPages) || 1);
  const current = clampPage(page, last);
  if (last <= 7) return Array.from({ length: last }, (_, index) => index + 1);
  const firstNearby = Math.max(2, Math.min(current - 1, last - 3));
  const lastNearby = Math.min(last - 1, Math.max(current + 1, 4));
  const result = [1];
  if (firstNearby > 2) result.push('…');
  for (let value = firstNearby; value <= lastNearby; value++) result.push(value);
  if (lastNearby < last - 1) result.push('…');
  result.push(last);
  return result;
}

export function createPagination({ locale, page, totalPages, onChange, labelKey = 'pagination' }) {
  const current = clampPage(page, totalPages);
  const last = Math.max(1, Math.trunc(totalPages) || 1);
  const choose = value => {
    if (value !== current && value >= 1 && value <= last) onChange(value);
  };
  const previous = button('', () => choose(current - 1), 'text-button page-button page-direction', 'back');
  previous.setAttribute('aria-label', t(locale, 'previousPage'));
  previous.disabled = current === 1;
  const next = button('', () => choose(current + 1), 'text-button page-button page-direction', 'arrow');
  next.setAttribute('aria-label', t(locale, 'nextPage'));
  next.disabled = current === last;
  return el('nav', { className: 'pagination', 'aria-label': t(locale, labelKey) },
    el('p', { className: 'pagination-summary muted', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' },
      t(locale, 'pageSummary', { page: current, total: last })),
    el('div', { className: 'pagination-buttons' }, previous,
      pageNumbers(current, last).map(value => {
        if (typeof value !== 'number') return el('span', { className: 'pagination-gap', 'aria-hidden': 'true' }, value);
        const pageButton = button(String(value), () => choose(value), `page-button ${value === current ? 'tonal' : 'text-button'}`);
        pageButton.setAttribute('aria-label', t(locale, 'goToPage', { page: value }));
        if (value === current) pageButton.setAttribute('aria-current', 'page');
        return pageButton;
      }), next));
}
