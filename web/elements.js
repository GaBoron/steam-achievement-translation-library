import { statusLabel, t } from './i18n.js';

export const repository = 'https://github.com/GaBoron/steam-achievement-translation-library';

export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'className') node.className = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'value') node.value = value;
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  append(node, ...children);
  return node;
}

export function append(node, ...children) {
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && typeof child !== 'boolean') {
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
  }
  return node;
}

// Original SVG strokes on a 24px grid; no icon font or third-party assets.
const paths = {
  search: 'M16 16 21 21M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z',
  close: 'm6 6 12 12M18 6 6 18',
  arrow: 'M4 12h15m-6-6 6 6-6 6',
  back: 'M20 12H5m6-6-6 6 6 6',
  download: 'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
  external: 'M13 4h7v7m0-7L10 14M9 4H4v16h16v-5',
  translate: 'M3 4h7a2 2 0 0 1 2 2v14a4 4 0 0 0-4-2H3ZM21 4h-7a2 2 0 0 0-2 2v14a4 4 0 0 1 4-2h5ZM6 8h3M6 12h3M15 8h3M15 12h3',
  warning: 'm12 3 10 18H2ZM12 9v5m0 3v.1',
  info: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 11v6m0-10v.1',
  link: 'm9 14 6-4M9 17l-2 1a4 4 0 0 1-4-7l3-2a4 4 0 0 1 5 1m2 4a4 4 0 0 0 5 1l3-2a4 4 0 0 0-4-7l-2 1',
  theme: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 3v18',
  language: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18Z',
  filter: 'M4 6h16M7 12h10M10 18h4',
  check: 'm5 12 4 4L19 6',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2',
  layers: 'm3 7 9-4 9 4-9 4Zm0 5 9 4 9-4M3 17l9 4 9-4',
  trophy: 'M8 3h8v7a4 4 0 0 1-8 0ZM8 5H4v3a4 4 0 0 0 4 4M16 5h4v3a4 4 0 0 1-4 4M12 14v6M8 21h8',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  github: 'M6 7v9m0-9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 7v2a4 4 0 0 1-4 4H6',
};

export function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', paths[name] || paths.info);
  svg.append(path);
  return svg;
}

export function button(label, action, kind = 'tonal', iconName) {
  return el('button', { className: `button ${kind}`, type: 'button', onclick: action }, iconName && icon(iconName), label);
}

export function externalLink(label, href, kind = 'text-button', iconName = 'external') {
  return el('a', { className: `button ${kind}`, href, target: '_blank', rel: 'noopener noreferrer' }, label, icon(iconName));
}

export function statusMark(status, locale) {
  return el('span', { className: `status ${status === 'current' ? 'current' : 'attention'}` },
    icon(status === 'current' ? 'check' : 'warning'), statusLabel(status, locale));
}

export function githubAvatar(name) {
  const node = el('span', { className: 'contributor-avatar', 'aria-hidden': 'true' }, icon('user'));
  const image = el('img', {
    src: `https://github.com/${encodeURIComponent(name)}.png?size=80`,
    alt: '', loading: 'lazy', decoding: 'async', referrerpolicy: 'no-referrer', width: 40, height: 40,
    onerror: () => image.remove(),
  });
  node.append(image);
  return node;
}

export function pageState(locale, titleKey, noteKey, action) {
  return el('div', { className: 'page-state' }, icon(titleKey === 'loading' ? 'translate' : 'info'),
    el('h1', {}, t(locale, titleKey)), noteKey && el('p', {}, t(locale, noteKey)), action);
}
