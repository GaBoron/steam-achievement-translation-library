const messages = {
  zh: {
    title: 'Steam 成就翻译库', skip: '跳到主要内容', github: 'GitHub 仓库',
    language: '界面语言', theme: '主题', auto: '跟随系统', light: '浅色', dark: '深色',
    games: '游戏', discover: '发现', resources: '资源', community: '社区', reportIssue: '问题反馈',
    search: '搜索游戏名称、Steam App ID 或贡献者', clearSearch: '清除搜索',
    filters: '筛选', clear: '清除', by: '由', moreContributors: '等 {count} 人',
    status: '文件状态', allStatuses: '全部状态', current: '可用', outdated: '可能过期',
    possibly_ineffective: '可能不生效', unknownStatus: '未知状态', languages: '支持语言',
    allLanguages: '全部语言', sort: '排序', updated: '最近更新', name: '游戏名称', achievementsSort: '成就数量',
    results: '{count} 个游戏', pagination: '游戏列表分页', previewPagination: '成就预览分页',
    previousPage: '上一页', nextPage: '下一页', goToPage: '第 {page} 页', pageSummary: '第 {page} / {total} 页',
    achievements: '{count} 个成就', variants: '{count} 个译本', unknown: '暂无数据',
    loading: '正在加载目录…', loadError: '目录暂时无法加载', loadErrorNote: '请检查网络后重试。',
    retry: '重试', noResults: '没有找到符合条件的游戏', noResultsNote: '尝试其他关键词，或清除筛选。',
    resetFilters: '清除筛选', invalidEntries: '目录中有 {count} 条数据不完整或无法读取，已忽略异常部分。',
    back: '返回游戏列表', notFound: '未找到这个游戏', notFoundNote: '该链接可能已失效，或游戏尚未收录。',
    steam: 'Steam 商店', source: 'GitHub 源文件', contributors: '贡献者', updatedAt: '最近更新',
    gameDetails: '游戏信息', achievementCount: '成就数量', availableVariants: '可用译本',
    translation: '译本', downloads: '译本下载', viewDownloads: '查看译本', links: '相关链接', translationCount: '译本数量',
    defaultVariant: '默认译本', variantId: '译本 ID', binDownload: '下载 BIN', jsonDownload: '下载 JSON',
    fileDetails: '文件信息与校验', binSize: 'BIN 大小', jsonSize: 'JSON 大小', jsonVersion: 'JSON 格式版本',
    missingFile: '暂无可下载文件', noVariants: '暂无可用译本', noLanguages: '暂无语言信息',
    preview: '成就预览', previewNote: '按需加载成就文本，内容可能包含剧透。',
    previewVariant: '预览译本', previewLanguage: '预览语言', loadPreview: '加载成就预览',
    previewLoading: '正在加载成就…', previewError: '成就预览暂时无法加载',
    previewMismatch: '预览文件与目录不一致，请稍后重试。', previewEmpty: '此译本没有成就数据。',
    previewUnavailable: '此译本暂无 JSON 预览文件。', emptyName: '名称为空', emptyDescription: '描述为空',
    translationUnavailable: '此语言没有对应的成就文本。', previewResults: '{count} 个成就',
    outdatedWarning: '此游戏的文件已标记为可能过期，可能缺少新增成就或与当前游戏版本不匹配。请确认译本说明后下载。',
    ineffectiveWarning: '此游戏的文件已标记为可能不生效，安装后可能无法显示译文。请查看仓库中的相关反馈。',
    unknownWarning: '此游戏的文件状态尚无法确认，请查看源文件与仓库反馈后下载。',
    compatibility: '兼容性',
    jsonOnlyNote: '仅显示文本（JSON 格式 2）；需要支持 JSON-only 的客户端，旧版 SATLI lite 不支持，不能安装为 BIN。',
    usageNote: 'BIN 可通过 SATLI 安装；JSON 需要支持其格式版本的文字显示客户端。',
    usageGuide: '查看使用说明', contribute: '贡献翻译', footer: '社区维护的 Steam 成就译本',
    footerCreditPrefix: '鸣谢 ', footerCreditSuffix: ' 为网站样式提供参考',
    share: '复制链接', copied: '链接已复制', copyFailed: '无法自动复制，请从地址栏复制链接。',
  },
  en: {
    title: 'Steam Achievement Translation Library', skip: 'Skip to content', github: 'GitHub repository',
    language: 'Interface language', theme: 'Theme', auto: 'System', light: 'Light', dark: 'Dark',
    games: 'Games', discover: 'Discover', resources: 'Resources', community: 'Community', reportIssue: 'Report an issue',
    search: 'Search by game, Steam App ID, or contributor', clearSearch: 'Clear search',
    filters: 'Filters', clear: 'Clear', by: 'by', moreContributors: 'and {count} more',
    status: 'File status', allStatuses: 'All statuses', current: 'Current', outdated: 'Possibly outdated',
    possibly_ineffective: 'May not work', unknownStatus: 'Unknown status', languages: 'Languages',
    allLanguages: 'All languages', sort: 'Sort by', updated: 'Recently updated', name: 'Game name', achievementsSort: 'Achievement count',
    results: '{count} games', pagination: 'Game list pagination', previewPagination: 'Achievement preview pagination',
    previousPage: 'Previous', nextPage: 'Next', goToPage: 'Page {page}', pageSummary: 'Page {page} of {total}',
    achievements: '{count} achievements', variants: '{count} variants', unknown: 'Not available',
    loading: 'Loading the catalog…', loadError: 'The catalog could not be loaded', loadErrorNote: 'Check your connection and try again.',
    retry: 'Retry', noResults: 'No games match your search', noResultsNote: 'Try another search or clear the filters.',
    resetFilters: 'Clear filters', invalidEntries: '{count} catalog entries are incomplete or unreadable. Invalid portions were skipped.',
    back: 'Back to games', notFound: 'Game not found', notFoundNote: 'This link may be out of date, or the game is not in the library yet.',
    steam: 'Steam store', source: 'GitHub source', contributors: 'Contributors', updatedAt: 'Last updated',
    gameDetails: 'Game details', achievementCount: 'Achievement count', availableVariants: 'Available translations',
    translation: 'Translation', downloads: 'Downloads', viewDownloads: 'View translations', links: 'Links', translationCount: 'Translation variants',
    defaultVariant: 'Default variant', variantId: 'Variant ID', binDownload: 'Download BIN', jsonDownload: 'Download JSON',
    fileDetails: 'File details and verification', binSize: 'BIN size', jsonSize: 'JSON size', jsonVersion: 'JSON format version',
    missingFile: 'No download available', noVariants: 'No translation variants available', noLanguages: 'No language information available',
    preview: 'Achievement preview', previewNote: 'Achievement text loads on request and may contain spoilers.',
    previewVariant: 'Preview variant', previewLanguage: 'Preview language', loadPreview: 'Load achievement preview',
    previewLoading: 'Loading achievements…', previewError: 'The achievement preview could not be loaded',
    previewMismatch: 'The preview does not match the catalog. Please try again later.', previewEmpty: 'This variant has no achievement data.',
    previewUnavailable: 'This variant has no JSON preview file.', emptyName: 'Empty name', emptyDescription: 'Empty description',
    translationUnavailable: 'This language has no text for this achievement.', previewResults: '{count} achievements',
    outdatedWarning: 'Files for this game are marked as possibly outdated. They may be missing new achievements or may not match the current game version. Check the variant notes before downloading.',
    ineffectiveWarning: 'Files for this game are marked as possibly ineffective. Translated text may not appear after installation. Check the repository for related reports.',
    unknownWarning: 'The file status for this game is unknown. Check the source files and repository reports before downloading.',
    compatibility: 'Compatibility',
    jsonOnlyNote: 'Display text only (JSON format 2). Requires a JSON-only-aware client; older SATLI lite is unsupported. Cannot install as BIN.',
    usageNote: 'Install BIN files with SATLI. JSON requires a text client supporting its format version.',
    usageGuide: 'Read the installation guide', contribute: 'Contribute a translation', footer: 'Community-maintained Steam achievement translations',
    footerCreditPrefix: 'Thanks to ', footerCreditSuffix: ' for the site style reference',
    share: 'Copy link', copied: 'Link copied', copyFailed: 'Copying is unavailable. Copy the link from your address bar.',
  },
};

export function t(locale, key, values = {}) {
  return (messages[locale]?.[key] ?? messages.en[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
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
