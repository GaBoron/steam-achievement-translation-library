import { loadPreview } from './catalog.js';
import { el, button, selectField } from './elements.js';
import { t, languageName, languageTag, variantLabel } from './i18n.js';

const batch = 60;

export function createPreview({ game, locale, variantId, onVariant }) {
  let selected = game.variants.find(variant => variant.id === variantId) || game.variants[0];
  let language;
  let requested = false;
  let rows = null;
  let shown = batch;
  let generation = 0;
  let disposed = false;
  const root = el('section', { className: 'preview-section', 'aria-labelledby': 'preview-title' });
  const controls = el('div', { className: 'preview-controls' });
  const content = el('div', { className: 'preview-content' });
  const chooseLanguage = () => {
    if (!selected.languages.includes(language)) {
      const preferred = locale === 'zh' ? 'schinese' : 'english';
      language = selected.languages.includes(preferred) ? preferred : selected.languages[0];
    }
  };

  function renderControls() {
    chooseLanguage();
    controls.replaceChildren(
      selectField(t(locale, 'previewVariant'), game.variants.map(variant => [variant.id, variantLabel(variant, locale)]), selected.id, value => {
        selected = game.variants.find(variant => variant.id === value);
        rows = null;
        shown = batch;
        generation++;
        onVariant(selected.id);
        renderControls();
        controls.querySelector('select').focus();
        if (requested) fetchRows();
        else renderPrompt();
      }),
      selectField(t(locale, 'previewLanguage'), selected.languages.map(code => [code, languageName(code, locale)]), language, value => {
        language = value;
        if (rows) renderRows();
      }),
    );
    if (!selected.languages.length) controls.lastElementChild.querySelector('select').disabled = true;
  }

  function renderPrompt() {
    content.setAttribute('aria-busy', 'false');
    content.replaceChildren(selected.jsonPath
      ? button(t(locale, 'loadPreview'), () => { requested = true; fetchRows(); }, 'tonal')
      : el('p', { className: 'muted' }, t(locale, 'previewUnavailable')));
  }

  async function fetchRows() {
    const version = ++generation;
    if (!selected.jsonPath) { renderPrompt(); return; }
    content.setAttribute('aria-busy', 'true');
    content.replaceChildren(el('p', { role: 'status', className: 'loading-line' }, t(locale, 'previewLoading')));
    try {
      const next = await loadPreview(game, selected);
      if (disposed || version !== generation) return;
      rows = next;
      renderRows();
    } catch (error) {
      if (disposed || version !== generation) return;
      content.replaceChildren(el('div', { className: 'inline-error', role: 'alert' },
        el('p', {}, t(locale, error.code === 'preview-format' ? 'previewMismatch' : 'previewError')),
        button(t(locale, 'retry'), fetchRows, 'tonal')));
    } finally {
      if (!disposed && version === generation) content.setAttribute('aria-busy', 'false');
    }
  }

  function renderRows() {
    content.replaceChildren();
    if (!rows.length) { content.append(el('p', { className: 'muted' }, t(locale, 'previewEmpty'))); return; }
    const result = el('p', { className: 'muted', role: 'status' }, t(locale, 'previewResults', { count: rows.length }));
    const list = el('ol', { className: 'achievement-list', lang: languageTag(language) },
      rows.slice(0, shown).map((row, index) => {
        const translation = row.translations[language];
        return el('li', {}, el('span', { className: 'achievement-number', 'aria-hidden': 'true' }, String(index + 1).padStart(2, '0')),
          el('div', {}, el('h3', {}, translation?.name || t(locale, 'emptyName')),
            el('p', { className: !translation?.description ? 'muted' : '' }, translation ? translation.description || t(locale, 'emptyDescription') : t(locale, 'translationUnavailable')),
            el('code', { className: 'achievement-id' }, row.id)));
      }));
    content.append(result, list);
    if (shown < rows.length) content.append(button(t(locale, 'showMore'), () => {
      const firstNew = shown;
      shown += batch;
      renderRows();
      const heading = content.querySelectorAll('h3')[firstNew];
      heading?.setAttribute('tabindex', '-1');
      heading?.focus();
    }, 'text-button'));
  }

  root.append(el('h2', { id: 'preview-title' }, t(locale, 'preview')),
    el('p', { className: 'section-note' }, t(locale, 'previewNote')), controls, content);
  renderControls();
  renderPrompt();
  return { node: root, dispose: () => { disposed = true; generation++; } };
}
