// Steamworks API codes, not store-only languages or schema-specific aliases.
// https://partner.steamgames.com/doc/store/localization/languages
const languages = {
  arabic: ['阿拉伯语', 'Arabic', 'ar'],
  brazilian: ['巴西葡萄牙语', 'Portuguese (Brazil)', 'pt-BR'],
  bulgarian: ['保加利亚语', 'Bulgarian', 'bg'],
  czech: ['捷克语', 'Czech', 'cs'],
  danish: ['丹麦语', 'Danish', 'da'],
  dutch: ['荷兰语', 'Dutch', 'nl'],
  english: ['英语', 'English', 'en'],
  finnish: ['芬兰语', 'Finnish', 'fi'],
  french: ['法语', 'French', 'fr'],
  german: ['德语', 'German', 'de'],
  greek: ['希腊语', 'Greek', 'el'],
  hungarian: ['匈牙利语', 'Hungarian', 'hu'],
  indonesian: ['印度尼西亚语', 'Indonesian', 'id'],
  italian: ['意大利语', 'Italian', 'it'],
  japanese: ['日语', 'Japanese', 'ja'],
  koreana: ['韩语', 'Korean', 'ko'],
  latam: ['拉丁美洲西班牙语', 'Spanish (Latin America)', 'es-419'],
  malay: ['马来语', 'Malay', 'ms'],
  norwegian: ['挪威语', 'Norwegian', 'nb'],
  polish: ['波兰语', 'Polish', 'pl'],
  portuguese: ['葡萄牙语', 'Portuguese', 'pt-PT'],
  romanian: ['罗马尼亚语', 'Romanian', 'ro'],
  russian: ['俄语', 'Russian', 'ru'],
  schinese: ['简体中文', 'Simplified Chinese', 'zh-CN'],
  spanish: ['西班牙语', 'Spanish', 'es'],
  swedish: ['瑞典语', 'Swedish', 'sv'],
  tchinese: ['繁体中文', 'Traditional Chinese', 'zh-TW'],
  thai: ['泰语', 'Thai', 'th'],
  turkish: ['土耳其语', 'Turkish', 'tr'],
  ukrainian: ['乌克兰语', 'Ukrainian', 'uk'],
  vietnamese: ['越南语', 'Vietnamese', 'vi'],
};

export const OTHER_LANGUAGE = '__other__';

export function isStandardLanguage(code) {
  return Object.hasOwn(languages, code);
}

export function languageName(code, locale) {
  return isStandardLanguage(code) ? languages[code][locale === 'zh' ? 0 : 1] : locale === 'zh' ? '其他' : 'Other';
}

export function languageTag(code) {
  return isStandardLanguage(code) ? languages[code][2] : undefined;
}

// Display unknown codes as one category without rewriting translation keys.
export function displayLanguages(codes, locale) {
  const standard = [...new Set(codes.filter(isStandardLanguage))];
  const labels = standard.map(code => languageName(code, locale));
  if (codes.some(code => !isStandardLanguage(code))) labels.push(languageName(OTHER_LANGUAGE, locale));
  return labels;
}
