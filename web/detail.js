import { createPreview } from './preview.js';
import { createDetailTabs } from './detail-tabs.js';
import { el, append, button, cover, externalLink, icon, repository, statusMark } from './elements.js';
import { t, formatDate, formatSize, variantLabel, gameCount } from './i18n.js';
import { displayLanguages } from './languages.js';
import { animateChange, bindDisclosure } from './motion.js';

export function createDetail({ game, locale, revision = 'main', variantId, initialTab, onVariant }) {
  const root = el('article', { className: 'project-page' });
  const sourceRevision = /^[a-f0-9]{40}$/.test(revision) ? revision : 'main';
  const feedback = el('p', { role: 'status', className: 'share-feedback', 'aria-live': 'polite' });
  const share = button(t(locale, 'share'), async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      feedback.textContent = t(locale, 'copied');
    } catch { feedback.textContent = t(locale, 'copyFailed'); }
    animateChange(feedback);
  }, 'tonal', 'link');
  const direct = game.variants.length === 1 ? game.variants[0] : null;
  const directPath = direct?.binPath || direct?.jsonPath;
  const primaryAction = directPath
    ? el('a', { className: 'button filled', href: `./${directPath}`,
        download: `UserGameStatsSchema_${game.appId}.${direct.binPath ? 'bin' : 'json'}` },
      icon('download'), t(locale, direct.binPath ? 'binDownload' : 'jsonDownload'))
    : button(t(locale, 'viewDownloads'), () => {
      tabs.show('downloads');
      const heading = variants.querySelector('h2');
      heading.focus({ preventScroll: true });
      variants.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    }, 'filled', 'download');

  append(root, el('div', { className: 'project-breadcrumb' },
    el('a', { href: '#/' }, icon('back'), t(locale, 'back'))),
    el('header', { className: 'project-header' },
      el('div', { className: 'project-identity' }, cover(game.appId, true),
        el('div', { className: 'project-heading' }, el('h1', {}, game.name),
          el('div', { className: 'project-summary' }, el('span', {}, `Steam App ID ${game.appId}`), statusMark(game.status, locale)))),
      el('div', { className: 'project-actions' }, primaryAction, share)), feedback);

  const sidebar = el('aside', { className: 'project-sidebar', 'aria-label': t(locale, 'gameDetails') });
  const sidebarSection = (key, ...children) => sidebar.append(el('section', { className: 'sidebar-section panel' }, el('h2', {}, t(locale, key)), children));
  const languages = displayLanguages(game.languages, locale);
  sidebarSection('languages', languages.length
    ? el('ul', { className: 'project-languages' }, languages.map(name => el('li', {}, name)))
    : el('p', { className: 'muted' }, t(locale, 'noLanguages')));
  sidebarSection('contributors', game.contributors.length
    ? el('ul', { className: 'project-contributors' }, game.contributors.map(name => el('li', {},
      el('a', { href: `https://github.com/${encodeURIComponent(name)}`, target: '_blank', rel: 'noopener noreferrer' }, name))))
    : el('p', { className: 'muted' }, t(locale, 'unknown')));
  const facts = el('dl', { className: 'project-facts' });
  const fact = (key, value) => facts.append(el('div', {}, el('dt', {}, t(locale, key)), el('dd', {}, value)));
  fact('updatedAt', el('time', { datetime: game.updatedAt }, formatDate(game.updatedAt, locale)));
  fact('achievementCount', gameCount(game, locale));
  fact('translationCount', String(game.variants.length));
  sidebarSection('gameDetails', facts);
  sidebarSection('links', el('div', { className: 'project-links' },
    externalLink(t(locale, 'steam'), `https://store.steampowered.com/app/${game.appId}/`),
    externalLink(t(locale, 'source'), `${repository}/tree/${sourceRevision}/files/${game.appId}`)));

  const variants = el('section', { className: 'translations-panel panel' },
    el('h2', { id: 'variants-title', tabindex: '-1' }, t(locale, 'availableVariants')));
  for (const variant of game.variants) {
    const languageText = displayLanguages(variant.languages, locale).join(', ') || t(locale, 'noLanguages');
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
    variants.append(el('article', { className: 'translation-variant', id: `variant-${variant.id}`, 'aria-label': variantLabel(variant, locale) },
      el('div', { className: 'variant-top' },
        el('div', { className: 'variant-text' }, showTitle && el('h3', {}, variantLabel(variant, locale)),
          description && el('p', { className: 'variant-description' }, description),
          el('p', { className: 'variant-meta' },
            game.variants.length > 1 && `${t(locale, 'achievements', { count: variant.count ?? t(locale, 'unknown') })} / `,
            'BIN ', formatSize(variant.size, locale)),
          game.variants.length > 1 && el('p', { className: 'variant-languages' }, languageText)), downloads),
      el('details', { className: 'file-details' }, el('summary', {}, t(locale, 'fileDetails')), details)));
  }
  if (!game.variants.length) variants.append(el('p', { className: 'muted' }, t(locale, 'noVariants')));
  variants.append(el('p', { className: 'usage-note' }, t(locale, 'usageNote'), ' ',
    el('a', { href: `${repository}/blob/main/README${locale === 'en' ? '_EN' : ''}.md`, target: '_blank', rel: 'noopener noreferrer' }, t(locale, 'usageGuide'))));
  const preview = createPreview({ game, locale, variantId, onVariant });
  preview.node.classList.add('panel');
  const tabs = createDetailTabs({ label: t(locale, 'gameDetails'), initial: initialTab, panels: [
    { id: 'downloads', label: t(locale, 'downloads'), node: variants },
    { id: 'preview', label: t(locale, 'preview'), node: preview.node },
  ] });
  if (game.status !== 'current') tabs.node.prepend(el('div', { className: 'warning', role: 'note' }, icon('warning'),
    el('p', {}, t(locale, game.status === 'outdated' ? 'outdatedWarning' : game.status === 'possibly_ineffective' ? 'ineffectiveWarning' : 'unknownWarning'))));
  root.append(el('div', { className: 'project-body' }, tabs.node, sidebar));
  const disclosures = [...variants.querySelectorAll('details')].map(bindDisclosure);
  return { node: root, get tab() { return tabs.selectedId; }, dispose() { preview.dispose(); disclosures.forEach(dispose => dispose()); } };
}
