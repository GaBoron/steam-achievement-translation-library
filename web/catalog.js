import { isStandardLanguage, OTHER_LANGUAGE } from './languages.js';
import { matchesTranslation } from './translation-integrity.js';

/** Catalog V2 is the directory; translation JSON is loaded only for previews. */
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' ? value.trim() : '';
const integer = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const languages = value => Array.isArray(value)
  ? [...new Set(value.filter(item => typeof item === 'string' && /^[a-z][a-z0-9_]{1,31}$/.test(item)))]
  : [];
const bilingual = value => object(value) ? { zh: text(value.zh), en: text(value.en) } : {};
const validDate = value => text(value) && Number.isFinite(Date.parse(text(value))) ? text(value) : null;
const statusCode = value => value == null ? 'current' : typeof value === 'string' ? text(value) || 'current' : 'unknown';

export class CatalogError extends Error {
  constructor(code) {
    super(code);
    this.name = 'CatalogError';
    this.code = code;
  }
}

export function parseCatalog(payload) {
  if (!object(payload) || payload.version !== 2 || !object(payload.games)) {
    throw new CatalogError('catalog-format');
  }
  const games = [];
  let invalidCount = 0;
  for (const [appId, game] of Object.entries(payload.games)) {
    if (!/^\d+$/.test(appId) || !object(game) || !text(game.name) || !object(game.variants)) {
      invalidCount++;
      continue;
    }
    const variants = [];
    let invalidVariant = false;
    for (const [id, value] of Object.entries(game.variants)) {
      if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(id) || !object(value)) {
        invalidVariant = true;
        continue;
      }
      const stem = `files/${appId}/${id}/UserGameStatsSchema_${appId}`;
      const json = object(value.json) ? value.json : {};
      const standalone = value.format === 'json';
      if ((value.format && !['bin', 'json'].includes(value.format)) ||
          (standalone && (json.version !== 2 || !/^[a-f0-9]{64}$/.test(json.sha256)))) {
        invalidVariant = true;
        continue;
      }
      variants.push({
        id,
        label: bilingual(value.label),
        description: bilingual(value.description),
        languages: languages(value.languages),
        count: integer(value.achievements),
        size: integer(value.size),
        sha256: /^[a-f0-9]{64}$/.test(value.sha256) ? value.sha256 : null,
        jsonVersion: integer(json.version),
        jsonSize: integer(json.size),
        jsonSha256: /^[a-f0-9]{64}$/.test(json.sha256) ? json.sha256 : null,
        binPath: standalone ? null : `${stem}.bin`,
        jsonPath: object(value.json) ? `${stem}.json` : null,
      });
    }
    if (!variants.length) {
      invalidCount++;
      continue;
    }
    if (invalidVariant) invalidCount++;
    variants.sort((a, b) => a.id === b.id ? 0 : a.id === 'default' ? -1 : b.id === 'default' ? 1 : a.id.localeCompare(b.id));
    const counts = variants.map(variant => variant.count).filter(value => value !== null);
    games.push({
      appId,
      name: text(game.name),
      status: statusCode(game.status),
      updatedAt: validDate(game.updated_at),
      submittedAt: validDate(game.submitted_at),
      contributors: Array.isArray(game.contributors) ? [...new Set(game.contributors.map(text).filter(Boolean))] : [],
      variants,
      languages: [...new Set(variants.flatMap(variant => variant.languages))].sort(),
      // A game is not the sum of its alternative variants.
      achievementCount: counts.length ? Math.max(...counts) : null,
      achievementMin: counts.length ? Math.min(...counts) : null,
    });
  }
  // An empty catalog is a valid empty state; a completely corrupt one is an error.
  if (!games.length && invalidCount) throw new CatalogError('catalog-format');
  return { games, invalidCount };
}

async function fetchPayload(path, code) {
  let response;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    response = await fetch(new URL(path, document.baseURI), { cache: 'no-cache', signal: controller.signal });
    if (!response.ok) throw new CatalogError(code);
    try {
      const bytes = await response.arrayBuffer();
      if (bytes.byteLength > 32 * 1024 * 1024) throw new Error('Download exceeds 32 MiB');
      return { payload: JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)), bytes };
    } catch {
      throw new CatalogError(code === 'catalog-load' ? 'catalog-format' : 'preview-format');
    }
  } catch (error) {
    throw error instanceof CatalogError ? error : new CatalogError(code);
  } finally {
    clearTimeout(timeout);
  }
}

export async function loadCatalog() {
  return parseCatalog((await fetchPayload('index-v2.json', 'catalog-load')).payload);
}

const fold = value => value.normalize('NFKC').toLocaleLowerCase().trim();

export function filterGames(games, { query = '', status = '', language = '', sort = 'updated' } = {}, locale = 'zh') {
  const terms = fold(query).replace(/@/g, '').split(/\s+/).filter(Boolean);
  const filtered = games.filter(game => {
    if (status && status !== 'all' && game.status !== status) return false;
    if (language && language !== 'all') {
      if (language === OTHER_LANGUAGE ? !game.languages.some(code => !isStandardLanguage(code)) : !game.languages.includes(language)) return false;
    }
    const haystack = fold(`${game.name} ${game.appId} ${game.contributors.join(' ')}`);
    return terms.every(term => haystack.includes(term));
  });
  const collator = new Intl.Collator(locale === 'zh' ? 'zh-CN' : 'en', { numeric: true, sensitivity: 'base' });
  const nameOrder = (a, b) => collator.compare(a.name, b.name) || collator.compare(a.appId, b.appId);
  return filtered.sort((a, b) => {
    if (sort === 'name') return nameOrder(a, b);
    if (sort === 'achievements') return (b.achievementCount ?? -1) - (a.achievementCount ?? -1) || nameOrder(a, b);
    return (Date.parse(b.updatedAt) || 0) - (Date.parse(a.updatedAt) || 0) || nameOrder(a, b);
  });
}

const previews = new Map();

export async function loadPreview(game, variant) {
  if (!variant.jsonPath || ![1, 2].includes(variant.jsonVersion)) throw new CatalogError('preview-format');
  const key = `${game.appId}/${variant.id}/${variant.jsonSha256 || variant.sha256}`;
  if (previews.has(key)) return previews.get(key);
  const pending = (async () => {
    const { payload, bytes } = await fetchPayload(variant.jsonPath, 'preview-load');
    if (!object(payload) || !await matchesTranslation(payload, bytes, game, variant) ||
        !object(payload.achievements) || !Array.isArray(payload.languages) ||
        payload.languages.length !== variant.languages.length ||
        new Set(payload.languages).size !== payload.languages.length ||
        payload.languages.some(language => !variant.languages.includes(language))) {
      throw new CatalogError('preview-format');
    }
    const rows = Object.entries(payload.achievements).map(([id, value]) => {
      if (!object(value) || !object(value.translations)) throw new CatalogError('preview-format');
      const translations = Object.create(null);
      for (const language of variant.languages) {
        const translation = value.translations[language];
        if (!object(translation) || typeof translation.name !== 'string' || typeof translation.description !== 'string') {
          throw new CatalogError('preview-format');
        }
        translations[language] = { name: translation.name, description: translation.description };
      }
      return { id, translations };
    });
    if (variant.count !== null && rows.length !== variant.count) throw new CatalogError('preview-format');
    return rows;
  })();
  previews.set(key, pending);
  try {
    return await pending;
  } catch (error) {
    previews.delete(key); // A failed request must remain retryable.
    throw error;
  }
}
