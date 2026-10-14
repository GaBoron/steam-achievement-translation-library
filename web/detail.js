import { createPreview } from './preview.js';
import { el, append, button, cover, externalLink, icon, repository, statusMark } from './elements.js';
import { t, formatDate, formatSize, variantLabel, gameCount } from './i18n.js';
import { displayLanguages } from './languages.js';
import { animateChange, bindDisclosure } from './motion.js';

export function createDetail({ game, locale, revision = 'main', variantId, onVariant }) {
  const root = el('article', { className: 'detail-page' });
  const sourceRevision = /^[a-f0-9]{40}$/.test(revision) ? revision : 'main';
  const feedback = el('p', { role: 'status', className: 'share-feedback', 'aria-live': 'polite' });
  const share = button(t(locale, 'share'), async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      feedback.textContent = t(locale, 'copied');
    } catch { feedback.textContent = t(locale, 'copyFailed'); }
    animateChange(feedback);
  }, 'text-button', 'link');
  append(root, el('div', { className: 'detail-navigation' },
    el('a', { className: 'button text-button back-button', href: '#/' }, icon('back'), t(locale, 'back')), share),
    feedback);

  const metadata = el('dl', { className: 'game-facts' });
  const fact = (label, value) => metadata.append(el('div', {}, el('dt', {}, t(locale, label)), el('dd', {}, value)));
  fact('updatedAt', el('time', { datetime: game.updatedAt }, formatDate(game.updatedAt, locale)));
  fact('contributors', game.contributors.length ? game.contributors.map((name, index) => [index ? ', ' : '',
    el('a', { href: `https://github.com/${encodeURIComponent(name)}`, target: '_blank', rel: 'noopener noreferrer' }, name)]).flat() : t(locale, 'unknown'));

  append(root, el('header', { className: 'game-heading' }, cover(game.appId, true),
    el('div', { className: 'game-heading-text' }, el('h1', {}, game.name),
      el('p', { className: 'detail-app-id' }, el('span', {}, `Steam App ID ${game.appId}`),
        el('span', {}, t(locale, 'achievements', { count: gameCount(game, locale) }))),
      el('div', { className: 'detail-heading-status' }, statusMark(game.status, locale))),
    externalLink(t(locale, 'steam'), `https://store.steampowered.com/app/${game.appId}/`, 'text-button detail-store-link')),
    game.status !== 'current' && el('div', { className: 'warning', role: 'note' }, icon('warning'),
      el('p', {}, t(locale, game.status === 'outdated' ? 'outdatedWarning' : game.status === 'possibly_ineffective' ? 'ineffectiveWarning' : 'unknownWarning'))));

  const variants = el('section', { className: 'detail-downloads variants-section', 'aria-labelledby': 'variants-title' },
    el('h2', { id: 'variants-title' }, t(locale, 'availableVariants')));
  for (const variant of game.variants) {
    const languageText = displayLanguages(variant.languages, locale).join(' · ') || t(locale, 'noLanguages');
    const description = variant.description?.[locale];
    const showTitle = game.variants.length > 1 || variant.id !== 'default' || Boolean(variant.label?.[locale]);
    const downloads = el('div', { className: 'variant-downloads' });
    if (variant.binPath) downloads.append(el('a', { className: 'button filled', href: `./${variant.binPath}`, download: `UserGameStatsSchema_${game.appId}.bin` }, icon('download'), t(locale, 'binDownload')));
    if (variant.jsonPath) downloads.append(el('a', { className: 'button tonal', href: `./${variant.jsonPath}`, download: `UserGameStatsSchema_${game.appId}.json` }, icon('download'), t(locale, 'jsonDownload')));
    if (!variant.binPath && !variant.jsonPath) downloads.append(el('p', { className: 'muted' }, t(locale, 'missingFile')));

    const details = el('dl', { className: 'file-facts' });
    const addDetail = (label, value) => details.append(el('div', {}, el('dt', {}, label), el('dd', {}, value)));
    addDetail(t(locale, 'variantId'), el('code', {}, variant.id));
    addDetail(t(locale, 'binSize'), formatSize(variant.size, locale));
    if (variant.jsonPath) {
      addDetail(t(locale, 'jsonSize'), formatSize(variant.jsonSize, locale));
      addDetail(t(locale, 'jsonVersion'), variant.jsonVersion ?? t(locale, 'unknown'));
    }
    addDetail('BIN SHA-256', el('code', { className: 'checksum' }, variant.sha256 || t(locale, 'unknown')));
    const sources = el('div', { className: 'file-source-links' });
    for (const [format, path] of [['BIN', variant.binPath], ['JSON', variant.jsonPath]]) {
      if (!path) continue;
      const link = externalLink(format, `${repository}/blob/${sourceRevision}/${path}`);
      link.setAttribute('aria-label', `${t(locale, 'source')} (${format})`);
      sources.append(link);
    }
    if (sources.childElementCount) addDetail(t(locale, 'source'), sources);
    variants.append(el('article', { className: 'variant', id: `variant-${variant.id}`, 'aria-label': variantLabel(variant, locale) },
      el('div', { className: 'variant-top' },
        el('div', { className: 'variant-text' }, showTitle && el('h3', {}, variantLabel(variant, locale)),
          description && el('p', { className: 'variant-description' }, description),
          el('p', { className: 'variant-meta' }, t(locale, 'achievements', { count: variant.count ?? t(locale, 'unknown') }), ' · BIN ', formatSize(variant.size, locale)),
          el('p', { className: 'variant-languages' }, languageText)), downloads),
      el('details', { className: 'file-details' }, el('summary', {}, t(locale, 'fileDetails')), details)));
  }
  if (!game.variants.length) variants.append(el('p', { className: 'muted' }, t(locale, 'noVariants')));
  variants.append(el('p', { className: 'usage-note' }, t(locale, 'usageNote'), ' ',
    el('a', { className: 'usage-guide', href: `${repository}/blob/main/README${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'usageGuide'))));
  root.append(el('div', { className: 'detail-body' }, variants,
    el('aside', { className: 'detail-context', 'aria-label': t(locale, 'gameDetails') }, metadata)));
  const preview = createPreview({ game, locale, variantId, onVariant });
  root.append(preview.node);
  const disclosures = [...root.querySelectorAll('details')].map(bindDisclosure);
  return { node: root, dispose() { preview.dispose(); disclosures.forEach(dispose => dispose()); } };
}
