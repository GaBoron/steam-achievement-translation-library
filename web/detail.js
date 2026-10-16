import { createPreview } from './preview.js';
import { createTranslationFiles } from './translation-files.js';
import { createDetailTabs } from './detail-tabs.js';
import { el, append, button, externalLink, githubAvatar, icon, repository, statusMark } from './elements.js';
import { cover } from './game-covers.js';
import { t, formatDate, gameCount } from './i18n.js';
import { displayLanguages } from './languages.js';
import { animateChange } from './motion.js';

export function createDetail({ game, locale, revision = 'main', variantId, initialTab, onVariant, coverImages = {} }) {
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
      el('div', { className: 'project-identity' }, cover(game.appId, true, coverImages[game.appId]),
        el('div', { className: 'project-heading' }, el('h1', {}, game.name),
          el('p', { className: 'project-summary' }, `Steam App ID ${game.appId}`),
          el('div', { className: 'project-metadata' },
            el('span', {}, icon('trophy'), t(locale, 'achievements', { count: gameCount(game, locale) })),
            el('span', {}, icon('layers'), t(locale, 'variants', { count: game.variants.length })), statusMark(game.status, locale)))),
      el('div', { className: 'project-actions' }, primaryAction, share)), feedback);

  const sidebar = el('aside', { className: 'project-sidebar', 'aria-label': t(locale, 'gameDetails') });
  const sidebarSection = (key, ...children) => sidebar.append(el('section', { className: 'sidebar-section panel' }, el('h2', {}, t(locale, key)), children));
  const languages = displayLanguages(game.languages, locale);
  sidebarSection('languages', languages.length
    ? el('ul', { className: 'project-languages' }, languages.map(name => el('li', {}, name)))
    : el('p', { className: 'muted' }, t(locale, 'noLanguages')));
  sidebarSection('contributors', game.contributors.length
    ? el('ul', { className: 'project-contributors' }, game.contributors.map(name => el('li', {},
      el('a', { href: `https://github.com/${encodeURIComponent(name)}`, target: '_blank', rel: 'noopener noreferrer' }, githubAvatar(name), name))))
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

  const files = createTranslationFiles({ game, locale, revision: sourceRevision });
  const variants = files.node;
  const preview = createPreview({ game, locale, variantId, onVariant });
  preview.node.classList.add('panel');
  const tabs = createDetailTabs({ label: t(locale, 'gameDetails'), initial: initialTab, panels: [
    { id: 'downloads', label: t(locale, 'downloads'), iconName: 'layers', node: variants },
    { id: 'preview', label: t(locale, 'preview'), iconName: 'translate', node: preview.node },
  ] });
  if (game.status !== 'current') tabs.node.prepend(el('div', { className: 'warning', role: 'note' }, icon('warning'),
    el('p', {}, t(locale, game.status === 'outdated' ? 'outdatedWarning' : game.status === 'possibly_ineffective' ? 'ineffectiveWarning' : 'unknownWarning'))));
  root.append(el('div', { className: 'project-body' }, tabs.node, sidebar));
  return { node: root, get tab() { return tabs.selectedId; }, dispose() { preview.dispose(); files.dispose(); } };
}
