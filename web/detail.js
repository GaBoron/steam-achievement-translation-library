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
  fact('submittedAt', el('time', { datetime: game.submittedAt }, formatDate(game.submittedAt, locale)));
  fact('achievementCount', gameCount(game, locale));
  fact('contributors', game.contributors.length ? game.contributors.map((name, index) => [index ? ', ' : '',
    el('a', { href: `https://github.com/${encodeURIComponent(name)}`, target: '_blank', rel: 'noopener noreferrer' }, name)]).flat() : t(locale, 'unknown'));

  append(root, el('header', { className: 'game-heading' }, cover(game.appId, true),
    el('div', { className: 'game-heading-text' }, el('h1', {}, game.name),
      el('p', { className: 'detail-app-id' }, `Steam App ID ${game.appId}`), statusMark(game.status, locale)),
    externalLink(t(locale, 'steam'), `https://store.steampowered.com/app/${game.appId}/`, 'outlined')),
    game.status !== 'current' && el('div', { className: 'warning', role: 'note' }, icon('warning'),
      el('p', {}, t(locale, game.status === 'outdated' ? 'outdatedWarning' : game.status === 'possibly_ineffective' ? 'ineffectiveWarning' : 'unknownWarning'))),
    metadata,
    el('div', { className: 'detail-languages' }, el('h2', {}, t(locale, 'languages')),
      el('p', {}, game.languages.length ? displayLanguages(game.languages, locale).join(' · ') : t(locale, 'noLanguages'))));

  const variants = el('section', { className: 'variants-section', 'aria-labelledby': 'variants-title' },
    el('h2', { id: 'variants-title' }, t(locale, 'availableVariants')));
  for (const variant of game.variants) {
    const languageText = displayLanguages(variant.languages, locale).join(' · ') || t(locale, 'noLanguages');
    const description = variant.description?.[locale];
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
    if (variant.binPath) addDetail(t(locale, 'source'), externalLink(t(locale, 'source'), `${repository}/blob/${sourceRevision}/${variant.binPath}`));
    if (variant.jsonPath) addDetail(`${t(locale, 'source')} (JSON)`, externalLink(`${t(locale, 'source')} (JSON)`, `${repository}/blob/${sourceRevision}/${variant.jsonPath}`));
    variants.append(el('article', { className: 'variant', id: `variant-${variant.id}` },
      el('div', { className: 'variant-top' },
        el('div', { className: 'variant-text' }, el('h3', {}, variantLabel(variant, locale)),
          description && el('p', { className: 'variant-description' }, description),
          el('p', { className: 'variant-meta' }, t(locale, 'achievements', { count: variant.count ?? t(locale, 'unknown') }), ' · BIN ', formatSize(variant.size, locale)),
          el('p', { className: 'variant-languages' }, languageText)), downloads),
      el('details', { className: 'file-details' }, el('summary', {}, t(locale, 'fileDetails')), details)));
  }
  if (!game.variants.length) variants.append(el('p', { className: 'muted' }, t(locale, 'noVariants')));
  append(root, variants,
    el('aside', { className: 'usage-note' }, icon('info'), el('div', {}, el('h2', {}, t(locale, 'usageTitle')),
      el('p', {}, t(locale, 'usageNote')),
      externalLink(t(locale, 'usageGuide'), `${repository}/blob/main/README${locale === 'en' ? '_EN' : ''}.md`))));
  const preview = createPreview({ game, locale, variantId, onVariant });
  root.append(preview.node);
  const disclosures = [...root.querySelectorAll('details')].map(bindDisclosure);
  return { node: root, dispose() { preview.dispose(); disclosures.forEach(dispose => dispose()); } };
}
