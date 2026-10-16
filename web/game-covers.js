import { el, icon } from './elements.js';

export async function loadCoverImages() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(new URL('./steam-covers.json', document.baseURI), { cache: 'no-cache', signal: controller.signal });
    if (!response.ok) return {};
    const images = await response.json();
    return images && typeof images === 'object' && !Array.isArray(images) ? images : {};
  } catch { return {}; }
  finally { clearTimeout(timeout); }
}

export function cover(appId, large = false, resolvedUrl) {
  const node = el('span', { className: `cover${large ? ' cover-large' : ''}`, 'aria-hidden': 'true' }, icon('translate'));
  const legacyUrl = `https://cdn.akamai.steamstatic.com/steam/apps/${encodeURIComponent(appId)}/header.jpg`;
  const prefix = `https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/${encodeURIComponent(appId)}/`;
  const sources = [...new Set([typeof resolvedUrl === 'string' && resolvedUrl.startsWith(prefix) ? resolvedUrl : null, legacyUrl].filter(Boolean))];
  let sourceIndex = 0;
  const image = el('img', {
    alt: '', loading: 'lazy', decoding: 'async', referrerpolicy: 'no-referrer', width: 184, height: 86,
    onerror: () => {
      if (++sourceIndex < sources.length) image.src = sources[sourceIndex];
      else image.remove();
    },
  });
  image.src = sources[0];
  node.append(image);
  return node;
}
