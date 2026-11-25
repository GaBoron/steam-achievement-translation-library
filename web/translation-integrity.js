/** Validate the format-specific integrity contract without inventing a BIN hash. */
export async function matchesTranslation(payload, bytes, game, variant) {
  if (!payload || payload.app_id !== game.appId || payload.variant_id !== variant.id ||
      payload.version !== variant.jsonVersion || bytes.byteLength !== variant.jsonSize) return false;
  if (variant.jsonVersion === 1) return !!variant.binPath && /^[a-f0-9]{64}$/.test(variant.sha256) && payload.source_sha256 === variant.sha256;
  if (variant.jsonVersion !== 2 || variant.binPath || !/^[a-f0-9]{64}$/.test(variant.jsonSha256)) return false;
  const fields = ['version', 'app_id', 'variant_id', 'languages', 'achievements'];
  if (Object.keys(payload).length !== fields.length || fields.some(key => !Object.hasOwn(payload, key))) return false;
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hex = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
  return hex === variant.jsonSha256;
}
