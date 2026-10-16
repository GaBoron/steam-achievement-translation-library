import { el, icon, externalLink, repository } from './elements.js';
import { t, formatSize, variantLabel } from './i18n.js';
import { displayLanguages } from './languages.js';
import { bindDisclosure } from './motion.js';

export function createPrimaryDownload({ game, locale, variantId }) {
  const node = el('a', { className: 'button filled' });
  function setVariant(id) {
    const variant = game.variants.find(entry => entry.id === id)
      || game.variants.find(entry => entry.id === 'default') || game.variants[0];
    const format = variant?.binPath ? 'bin' : 'json';
    const path = variant?.binPath || variant?.jsonPath;
    node.hidden = !path;
    if (!path) {
      node.removeAttribute('href');
      node.removeAttribute('download');
      return;
    }
    const label = t(locale, format === 'bin' ? 'binDownload' : 'jsonDownload');
    node.setAttribute('href', `./${path}`);
    node.setAttribute('download', `UserGameStatsSchema_${game.appId}.${format}`);
    node.setAttribute('title', `${label} · ${variantLabel(variant, locale)}`);
    node.replaceChildren(icon('download'), label);
  }
  setVariant(variantId);
  return { node, setVariant };
}

/** Version rows own download presentation and expandable integrity information. */
export function createTranslationFiles({ game, locale, revision }) {
  const root = el('section', { className: 'translations-panel' },
    el('h2', { id: 'variants-title', tabindex: '-1', className: 'sr-only' }, t(locale, 'availableVariants')));
  const columns = el('div', { className: 'version-columns', 'aria-hidden': 'true' },
    el('span', {}, t(locale, 'translation')), el('span', {}, t(locale, 'languages')), el('span', {}, t(locale, 'downloads')));
  if (game.variants.length) root.append(columns);
  for (const variant of game.variants) {
    const languages = displayLanguages(variant.languages, locale);
    const description = variant.description?.[locale];
    const downloads = el('div', { className: 'variant-downloads' });
    for (const [format, path, key] of [['bin', variant.binPath, 'binDownload'], ['json', variant.jsonPath, 'jsonDownload']]) {
      if (!path) continue;
      downloads.append(el('a', { className: `button ${format === 'bin' ? 'filled' : 'tonal'}`, href: `./${path}`,
        'aria-label': t(locale, key), title: t(locale, key),
        download: `UserGameStatsSchema_${game.appId}.${format}` }, format === 'bin' && icon('download'), format.toUpperCase()));
    }
    if (!downloads.childElementCount) downloads.append(el('p', { className: 'muted' }, t(locale, 'missingFile')));
    const facts = el('dl', { className: 'file-facts' });
    const fact = (label, value) => facts.append(el('div', {}, el('dt', {}, label), el('dd', {}, value)));
    fact(t(locale, 'variantId'), el('code', {}, variant.id));
    fact(t(locale, 'languages'), languages.join(', ') || t(locale, 'noLanguages'));
    fact(t(locale, 'binSize'), formatSize(variant.size, locale));
    if (variant.jsonPath) {
      fact(t(locale, 'jsonSize'), formatSize(variant.jsonSize, locale));
      fact(t(locale, 'jsonVersion'), variant.jsonVersion ?? t(locale, 'unknown'));
    }
    fact('BIN SHA-256', el('code', { className: 'checksum' }, variant.sha256 || t(locale, 'unknown')));
    const sources = el('div', { className: 'file-source-links' });
    for (const [format, path] of [['BIN', variant.binPath], ['JSON', variant.jsonPath]]) {
      if (!path) continue;
      const link = externalLink(format, `${repository}/blob/${revision}/${path}`);
      link.setAttribute('aria-label', `${t(locale, 'source')} (${format})`);
      sources.append(link);
    }
    if (sources.childElementCount) fact(t(locale, 'source'), sources);
    root.append(el('article', { className: 'translation-variant', id: `variant-${variant.id}`, 'aria-label': variantLabel(variant, locale) },
      el('div', { className: 'variant-identity' }, el('span', { className: 'variant-icon' }, icon('layers')),
        el('div', { className: 'variant-text' }, el('h3', {}, variantLabel(variant, locale)),
          description && el('p', { className: 'variant-description' }, description),
          el('p', { className: 'variant-meta' },
            t(locale, 'achievements', { count: variant.count ?? t(locale, 'unknown') }), ' · ', formatSize(variant.size, locale)))),
      el('div', { className: 'variant-languages', title: languages.join(', '), 'aria-label': languages.join(', ') },
        languages.length ? languages.slice(0, 3).map(name => el('span', {}, name)) : t(locale, 'noLanguages'),
        languages.length > 3 && el('span', {}, `+${languages.length - 3}`)),
      downloads,
      el('details', { className: 'file-details' }, el('summary', {}, t(locale, 'fileDetails')), facts)));
  }
  if (!game.variants.length) root.append(el('p', { className: 'panel muted' }, t(locale, 'noVariants')));
  root.append(el('p', { className: 'usage-note panel' }, icon('info'), el('span', {}, t(locale, 'usageNote'), ' ',
    el('a', { href: `${repository}/blob/main/README${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'usageGuide')))));
  const disclosures = [...root.querySelectorAll('details')].map(bindDisclosure);
  return { node: root, dispose() { disclosures.forEach(dispose => dispose()); } };
}
