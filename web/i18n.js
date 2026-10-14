const messages = {
  zh: {
    title: 'Steam 成就翻译库', skip: '跳到主要内容', github: 'GitHub 仓库',
    language: '界面语言', theme: '主题', auto: '跟随系统', light: '浅色', dark: '深色',
    games: '游戏', search: '搜索游戏名称、Steam App ID 或贡献者', clearSearch: '清除搜索',
    status: '文件状态', allStatuses: '全部状态', current: '可用', outdated: '可能过期',
    possibly_ineffective: '可能不生效', unknownStatus: '未知状态', languages: '支持语言',
    allLanguages: '全部语言', sort: '排序', updated: '最近更新', name: '游戏名称', achievementsSort: '成就数量',
    results: '{count} 个游戏', showing: '已显示 {shown} / {total}', showMore: '显示更多',
    achievements: '{count} 个成就', variants: '{count} 个译本', unknown: '暂无数据',
    loading: '正在加载目录…', loadError: '目录暂时无法加载', loadErrorNote: '请检查网络后重试。',
    retry: '重试', noResults: '没有找到符合条件的游戏', noResultsNote: '尝试其他关键词，或清除筛选。',
    resetFilters: '清除筛选', invalidEntries: '目录中有 {count} 条数据不完整或无法读取，已忽略异常部分。',
    back: '返回游戏列表', notFound: '未找到这个游戏', notFoundNote: '该链接可能已失效，或游戏尚未收录。',
    steam: 'Steam 商店', source: 'GitHub 源文件', contributors: '贡献者', updatedAt: '最近更新',
    submittedAt: '首次收录', achievementCount: '成就数量', availableVariants: '可用译本',
    defaultVariant: '默认译本', variantId: '译本 ID', binDownload: '下载 BIN', jsonDownload: '下载 JSON',
    fileDetails: '文件信息与校验', binSize: 'BIN 大小', jsonSize: 'JSON 大小', jsonVersion: 'JSON 格式版本',
    missingFile: '暂无可下载文件', noVariants: '暂无可用译本', noLanguages: '暂无语言信息',
    preview: '成就预览', previewNote: '预览内容可能包含剧透，加载后可切换译本与语言。',
    previewVariant: '预览译本', previewLanguage: '预览语言', loadPreview: '加载成就预览',
    previewLoading: '正在加载成就…', previewError: '成就预览暂时无法加载',
    previewMismatch: '预览文件与目录不一致，请稍后重试。', previewEmpty: '此译本没有成就数据。',
    previewUnavailable: '此译本暂无 JSON 预览文件。', emptyName: '名称为空', emptyDescription: '描述为空',
    translationUnavailable: '此语言没有对应的成就文本。', previewResults: '{count} 个成就',
    outdatedWarning: '此游戏的文件已标记为可能过期，可能缺少新增成就或与当前游戏版本不匹配。请确认译本说明后下载。',
    ineffectiveWarning: '此游戏的文件已标记为可能不生效，安装后可能无法显示译文。请查看仓库中的相关反馈。',
    unknownWarning: '此游戏的文件状态尚无法确认，请查看源文件与仓库反馈后下载。',
    usageTitle: '使用方式', usageNote: 'BIN 可通过 SATLI 安装；JSON 可供 SATLI lite 等兼容工具使用。选择适合游戏版本的译本。',
    usageGuide: '查看使用说明', contribute: '贡献翻译', footer: '社区维护的 Steam 成就译本',
    share: '复制链接', copied: '链接已复制', copyFailed: '无法自动复制，请从地址栏复制链接。',
  },
  en: {
    title: 'Steam Achievement Translation Library', skip: 'Skip to content', github: 'GitHub repository',
    language: 'Interface language', theme: 'Theme', auto: 'System', light: 'Light', dark: 'Dark',
    games: 'Games', search: 'Search by game, Steam App ID, or contributor', clearSearch: 'Clear search',
    status: 'File status', allStatuses: 'All statuses', current: 'Current', outdated: 'Possibly outdated',
    possibly_ineffective: 'May not work', unknownStatus: 'Unknown status', languages: 'Languages',
    allLanguages: 'All languages', sort: 'Sort by', updated: 'Recently updated', name: 'Game name', achievementsSort: 'Achievement count',
    results: '{count} games', showing: 'Showing {shown} of {total}', showMore: 'Show more',
    achievements: '{count} achievements', variants: '{count} variants', unknown: 'Not available',
    loading: 'Loading the catalog…', loadError: 'The catalog could not be loaded', loadErrorNote: 'Check your connection and try again.',
    retry: 'Retry', noResults: 'No games match your search', noResultsNote: 'Try another search or clear the filters.',
    resetFilters: 'Clear filters', invalidEntries: '{count} catalog entries are incomplete or unreadable. Invalid portions were skipped.',
    back: 'Back to games', notFound: 'Game not found', notFoundNote: 'This link may be out of date, or the game is not in the library yet.',
    steam: 'Steam store', source: 'GitHub source', contributors: 'Contributors', updatedAt: 'Last updated',
    submittedAt: 'First added', achievementCount: 'Achievement count', availableVariants: 'Translation variants',
    defaultVariant: 'Default variant', variantId: 'Variant ID', binDownload: 'Download BIN', jsonDownload: 'Download JSON',
    fileDetails: 'File details and verification', binSize: 'BIN size', jsonSize: 'JSON size', jsonVersion: 'JSON format version',
    missingFile: 'No download available', noVariants: 'No translation variants available', noLanguages: 'No language information available',
    preview: 'Achievement preview', previewNote: 'Previews may contain spoilers. Load them to switch variants and languages.',
    previewVariant: 'Preview variant', previewLanguage: 'Preview language', loadPreview: 'Load achievement preview',
    previewLoading: 'Loading achievements…', previewError: 'The achievement preview could not be loaded',
    previewMismatch: 'The preview does not match the catalog. Please try again later.', previewEmpty: 'This variant has no achievement data.',
    previewUnavailable: 'This variant has no JSON preview file.', emptyName: 'Empty name', emptyDescription: 'Empty description',
    translationUnavailable: 'This language has no text for this achievement.', previewResults: '{count} achievements',
    outdatedWarning: 'Files for this game are marked as possibly outdated. They may be missing new achievements or may not match the current game version. Check the variant notes before downloading.',
    ineffectiveWarning: 'Files for this game are marked as possibly ineffective. Translated text may not appear after installation. Check the repository for related reports.',
    unknownWarning: 'The file status for this game is unknown. Check the source files and repository reports before downloading.',
    usageTitle: 'Using these files', usageNote: 'Install BIN files with SATLI. JSON files work with compatible tools such as SATLI lite. Choose the variant for your game version.',
    usageGuide: 'Read the installation guide', contribute: 'Contribute a translation', footer: 'Community-maintained Steam achievement translations',
    share: 'Copy link', copied: 'Link copied', copyFailed: 'Copying is unavailable. Copy the link from your address bar.',
  },
};

const languageNames = {
  arabic: ['阿拉伯语', 'Arabic'], brazilian: ['巴西葡萄牙语', 'Portuguese (Brazil)'],
  bulgarian: ['保加利亚语', 'Bulgarian'], czech: ['捷克语', 'Czech'], danish: ['丹麦语', 'Danish'],
  dutch: ['荷兰语', 'Dutch'], english: ['英语', 'English'], finnish: ['芬兰语', 'Finnish'],
  french: ['法语', 'French'], german: ['德语', 'German'], greek: ['希腊语', 'Greek'],
  hungarian: ['匈牙利语', 'Hungarian'], indonesian: ['印度尼西亚语', 'Indonesian'],
  italian: ['意大利语', 'Italian'], japanese: ['日语', 'Japanese'], koreana: ['韩语', 'Korean'],
  latam: ['拉丁美洲西班牙语', 'Spanish (Latin America)'], norwegian: ['挪威语', 'Norwegian'],
  polish: ['波兰语', 'Polish'], portuguese: ['葡萄牙语', 'Portuguese'], romanian: ['罗马尼亚语', 'Romanian'],
  russian: ['俄语', 'Russian'], schinese: ['简体中文', 'Simplified Chinese'],
  spanish: ['西班牙语', 'Spanish'], swedish: ['瑞典语', 'Swedish'], tchinese: ['繁体中文', 'Traditional Chinese'],
  thai: ['泰语', 'Thai'], turkish: ['土耳其语', 'Turkish'], ukrainian: ['乌克兰语', 'Ukrainian'],
  vietnamese: ['越南语', 'Vietnamese'], sc_schinese: ['简体中文（sc_schinese）', 'Simplified Chinese (sc_schinese)'],
  schiese: ['未标准化语言代码：schiese', 'Nonstandard language code: schiese'],
  chinese: ['未标准化语言代码：chinese', 'Nonstandard language code: chinese'],
};

const languageTags = {
  arabic: 'ar', brazilian: 'pt-BR', bulgarian: 'bg', czech: 'cs', danish: 'da', dutch: 'nl',
  english: 'en', finnish: 'fi', french: 'fr', german: 'de', greek: 'el', hungarian: 'hu',
  indonesian: 'id', italian: 'it', japanese: 'ja', koreana: 'ko', latam: 'es-419', norwegian: 'nb',
  polish: 'pl', portuguese: 'pt-PT', romanian: 'ro', russian: 'ru', schinese: 'zh-CN',
  spanish: 'es', swedish: 'sv', tchinese: 'zh-TW', thai: 'th', turkish: 'tr', ukrainian: 'uk', vietnamese: 'vi',
};

export function languageTag(code) { return languageTags[code]; }

export function t(locale, key, values = {}) {
  return (messages[locale]?.[key] ?? messages.en[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
}

export function languageName(code, locale) {
  return languageNames[code]?.[locale === 'zh' ? 0 : 1] ?? code;
}

export function formatDate(value, locale) {
  if (!value || !Number.isFinite(Date.parse(value))) return t(locale, 'unknown');
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en', {
    year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  }).format(new Date(value));
}

export function formatSize(value, locale) {
  if (!Number.isFinite(value)) return t(locale, 'unknown');
  if (value < 1024) return `${value} B`;
  const unit = value < 1024 * 1024 ? 'KiB' : 'MiB';
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / (unit === 'KiB' ? 1024 : 1024 * 1024))} ${unit}`;
}

export function statusLabel(status, locale) {
  return ['current', 'outdated', 'possibly_ineffective'].includes(status) ? t(locale, status)
    : `${t(locale, 'unknownStatus')} (${status})`;
}

export function variantLabel(variant, locale) {
  return variant.label?.[locale] || (variant.id === 'default' ? t(locale, 'defaultVariant') : variant.id);
}

export function gameCount(game, locale) {
  if (game.achievementCount === null) return t(locale, 'unknown');
  return game.achievementMin !== null && game.achievementMin !== game.achievementCount
    ? `${game.achievementMin}–${game.achievementCount}` : String(game.achievementCount);
}
