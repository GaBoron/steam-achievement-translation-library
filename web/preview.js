import { loadPreview } from './catalog.js';
import { el, button } from './elements.js';
import { t, variantLabel } from './i18n.js';
import { isStandardLanguage, languageName, languageTag, OTHER_LANGUAGE } from './languages.js';
import { clampPage, createPagination } from './pagination.js';
import { createSelect } from './select.js';
import { replaceContent, animateChange } from './motion.js';

const pageSize = 60;

export function createPreview({ game, locale, variantId, onVariant }) {
  let selected = game.variants.find(variant => variant.id === variantId) || game.variants[0];
  let language;
  let requested = false;
  let rows = null;
  let page = 1;
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

  const languageOptions = () => [
    ...selected.languages.filter(isStandardLanguage).map(code => [code, languageName(code, locale)]),
    ...selected.languages.filter(code => !isStandardLanguage(code)).map(code =>
      [code, `${languageName(OTHER_LANGUAGE, locale)} · ${code}`, languageName(OTHER_LANGUAGE, locale)]),
  ];
  chooseLanguage();
  const variantPicker = createSelect({
    label: t(locale, 'previewVariant'),
    options: game.variants.map(variant => [variant.id, variantLabel(variant, locale)]),
    value: selected.id,
    onChange: value => {
      const variant = game.variants.find(entry => entry.id === value);
      if (!variant) return;
      selected = variant;
      rows = null;
      page = 1;
      generation++;
      chooseLanguage();
      languagePicker.setOptions(languageOptions());
      languagePicker.setValue(language || '');
      languagePicker.setDisabled(!selected.languages.length);
      animateChange(languagePicker.node);
      onVariant(selected.id);
      if (requested) fetchRows();
      else renderPrompt();
    },
  });
  const languagePicker = createSelect({
    label: t(locale, 'previewLanguage'), options: languageOptions(), value: language || '',
    onChange: value => {
      language = value;
      page = 1;
      if (rows) renderRows();
    },
  });
  languagePicker.setDisabled(!selected.languages.length);
  controls.append(variantPicker.node, languagePicker.node);

  function renderPrompt() {
    content.setAttribute('aria-busy', 'false');
    replaceContent(content, selected.jsonPath
      ? button(t(locale, 'loadPreview'), () => { requested = true; fetchRows(); }, 'tonal')
      : el('p', { className: 'muted' }, t(locale, 'previewUnavailable')));
  }

  async function fetchRows() {
    const version = ++generation;
    if (!selected.jsonPath) { renderPrompt(); return; }
    content.setAttribute('aria-busy', 'true');
    replaceContent(content, el('p', { role: 'status', className: 'loading-line' }, t(locale, 'previewLoading')));
    try {
      const next = await loadPreview(game, selected);
      if (disposed || version !== generation) return;
      rows = next;
      renderRows();
    } catch (error) {
      if (disposed || version !== generation) return;
      replaceContent(content, el('div', { className: 'inline-error', role: 'alert' },
        el('p', {}, t(locale, error.code === 'preview-format' ? 'previewMismatch' : 'previewError')),
        button(t(locale, 'retry'), fetchRows, 'tonal')));
    } finally {
      if (!disposed && version === generation) content.setAttribute('aria-busy', 'false');
    }
  }

  function renderRows() {
    if (!rows.length) { replaceContent(content, el('p', { className: 'muted' }, t(locale, 'previewEmpty'))); return; }
    const totalPages = Math.ceil(rows.length / pageSize);
    page = clampPage(page, totalPages);
    const start = (page - 1) * pageSize;
    const result = el('p', { className: 'muted', role: 'status' }, t(locale, 'previewResults', { count: rows.length }));
    const list = el('ol', { className: 'achievement-list', lang: languageTag(language), start: start + 1 },
      rows.slice(start, start + pageSize).map((row, index) => {
        const translation = row.translations[language];
        return el('li', {}, el('span', { className: 'achievement-number', 'aria-hidden': 'true' }, String(start + index + 1).padStart(2, '0')),
          el('div', {}, el('h3', {}, translation?.name || t(locale, 'emptyName')),
            el('p', { className: !translation?.description ? 'muted' : '' }, translation ? translation.description || t(locale, 'emptyDescription') : t(locale, 'translationUnavailable')),
            el('code', { className: 'achievement-id' }, row.id)));
      }));
    replaceContent(content, result, list, createPagination({ locale, page, totalPages, labelKey: 'previewPagination',
      onChange: value => {
        page = value;
        renderRows();
        const heading = content.querySelector('h3');
        heading?.setAttribute('tabindex', '-1');
        heading?.focus({ preventScroll: true });
        content.querySelector('.achievement-list')?.scrollIntoView({ block: 'start',
          behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
      },
    }));
  }

  root.append(el('h2', { id: 'preview-title' }, t(locale, 'preview')),
    el('p', { className: 'section-note' }, t(locale, 'previewNote')), controls, content);
  renderPrompt();
  return { node: root, dispose: () => {
    disposed = true;
    generation++;
    variantPicker.dispose();
    languagePicker.dispose();
  } };
}
