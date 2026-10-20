# 翻译 JSON 格式

本接口提供按成就 API name 索引的多语言显示文本。Catalog 字段、下载地址、快照与校验示例见 [数据接入指南](integration.md)。

```json
{
  "version": 1,
  "app_id": "123456",
  "variant_id": "default",
  "source_sha256": "<源 BIN 的 SHA-256>",
  "languages": ["english", "schinese"],
  "achievements": {
    "ACH_FIRST": {
      "translations": {
        "english": {"name": "First step", "description": "Complete the tutorial."},
        "schinese": {"name": "第一步", "description": "完成教程。"}
      }
    }
  }
}
```

| 字段 | 约定 |
| --- | --- |
| `version` | 显示文本格式版本，值为 `1`，独立于 Catalog 的版本 |
| `app_id` / `variant_id` | 对应 Catalog 的游戏与版本 ID |
| `source_sha256` | 生成此 JSON 的源 BIN 哈希 |
| `languages` | Steam 语言代码，按字母序排列 |
| `achievements` | 以 API name 为键；每项的 `translations` 包含各语言的 `name` 和 `description` |

文件由对应 BIN 自动生成，使用 UTF-8、LF 和结尾换行，最大 32 MiB。每项成就的名称、描述独立保留空值。该格式只包含显示文本，不包含解锁状态、进度、图标或完整 Binary KeyValues 节点。

Catalog 版本记录的 `json.size` 是 JSON 的 UTF-8 字节数；`variant.sha256` 与 `source_sha256` 都指源 BIN。消费数据时核对版本、ID、字节数、语言、成就数和源 BIN 哈希。

## 独立 JSON：格式 2

没有 BIN 时使用格式 `2`，文件名仍为 `UserGameStatsSchema_<app_id>.json`。格式 1 及其 BIN 哈希语义保持不变；不能只修改 `version` 将格式 1 当作独立 JSON 投稿。

```json
{
  "version": 2,
  "app_id": "123456",
  "variant_id": "default",
  "languages": ["english", "schinese"],
  "target_languages": ["schinese"],
  "source": {
    "kind": "steam-public",
    "url": "https://steamcommunity.com/stats/123456/achievements/?l=english",
    "retrieved_at": "2026-10-20T00:00:00Z",
    "language": "english",
    "achievements": {
      "ACH_FIRST": {"name": "First step", "description": "Complete the tutorial."}
    }
  },
  "achievements": {
    "ACH_FIRST": {
      "translations": {
        "english": {"name": "First step", "description": "Complete the tutorial."},
        "schinese": {"name": "第一步", "description": "完成教程。"}
      }
    }
  }
}
```

示例仅说明结构，不代表真实游戏数据。格式 2 不含 `source_sha256`。Catalog 的 `json.sha256` 校验规范化 JSON 自身的 UTF-8/LF 字节（含结尾换行）；独立版本没有 BIN `sha256` / `size`，通过 `format: "json"` 识别。Catalog 的兼容扩展见 [接入指南](integration.md#json-only-兼容扩展)。

`source` 保存原文快照、语言、HTTPS 来源地址及带时区的获取时间。`kind` 为 `steam-public`（该 App ID 的 Steam 成就页面）或 `contributor-json`（贡献者提供并注明出处的数据）。这是可供审核的来源记录，不是自动认证；不会据此声称完整 schema 或 Steam 客户端兼容。原文和译文 API name 集合必须一致且唯一，原文语言必须逐字段匹配快照。

`languages` 与 `target_languages` 均排序且不重复，后者必须是前者的子集并与原文语言分开。每项成就的名称和描述独立要求所有声明语言都有内容或全部为空；目标语言不能整份照抄原文冒充翻译。投稿必须包含 1–10000 项成就，每个文本字段不超过 65536 字符，API name 不超过 512 字符。拒绝重复 JSON 键、NUL、未声明语言、错误 ID、未知版本和超过 32 MiB 的文件。机器人将合法附件规范化为 UTF-8/LF；审核和发布重新核对文件内容、哈希、大小、语言及成就数。

### 生成可翻译草稿

在仓库根目录运行（只使用 Python 标准库）：

```bash
python workflow-scripts/steam_public_achievements.py 440 --targets schinese --output /path/to/UserGameStatsSchema_440.json
```

需要其他原文语言时使用 `--language`。该命令匿名读取 Steam 当前公开成就页面中的结构化数据，核对 App ID、语言和 API name；不是稳定的官方 API，页面改版或数据不可获取时会报错，不生成文件。输出路径必须不存在，以免覆盖已有译文。不会把可见列表标为完整 schema，也不会补造隐藏或未公开成就。

生成结果带 `draft: true`，只保留获取到的原文，目标语言为空。完成并审核译文后移除 `draft` 或设为 `false`，再按[贡献指南](CONTRIBUTING.md)上传 JSON。无附件请愿会尝试同样的获取流程，并在工作流的 `petition-json` 附件中提供草稿（保留 30 天，下载需登录 GitHub）；获取失败时保留请愿并说明待补充来源。上述命令可在本地重新生成，不依赖工作流附件。

格式 2 仅供支持该格式的文字显示客户端使用，不能用于 BIN 覆盖、统计或解锁数据。旧版 SATLI lite 只支持格式 1；本仓库支持格式 2 不代表客户端已经支持。

## English

This interface provides multilingual display text keyed by achievement API name. See the [data integration guide](integration.md#english) for catalog fields, download URLs, snapshots, and validation examples.

The example above defines the format. `version: 1` is the text format version, independent of the Catalog version. `app_id` and `variant_id` match the catalog entry; `source_sha256` identifies the source BIN. `languages` is an alphabetically sorted list of Steam language codes. `achievements` is keyed by API name, with each entry's `translations` holding language-specific `name` and `description`.

Each file is generated from its BIN, uses UTF-8, LF, and a final newline, and is limited to 32 MiB. Names and descriptions independently preserve empty fields. It contains display text only, without unlock state, progress, icons, or complete Binary KeyValues nodes.

Catalog `json.size` measures JSON bytes; `variant.sha256` and `source_sha256` identify the BIN. Verify versions, IDs, byte size, languages, achievement count, and source BIN hash when consuming data.

### Standalone JSON: format 2

Use format `2` without a BIN, with the same `UserGameStatsSchema_<app_id>.json` filename. The second example above describes its structure; it is illustrative, not real game data. Format 1 remains BIN-derived with unchanged semantics and cannot be submitted standalone by changing its version alone.

Format 2 has no `source_sha256`. Catalog `json.sha256` hashes the canonical JSON's own UTF-8/LF bytes, including the final newline. A standalone variant uses `format: "json"` and omits BIN `sha256` and `size`. See the [catalog compatibility extension](integration.md#json-only-compatibility-extension).

`source` records the original achievement text, its language, an HTTPS source URL and an ISO 8601 retrieval time with timezone. Its `kind` is `steam-public` (this app's Steam achievement page) or `contributor-json` (contributor-provided data with a reference). These records are reviewable claims, not automatic certification of completeness or Steam client compatibility. Original and translated API-name sets must match exactly; the original language must match the snapshot field by field.

Sorted, unique `target_languages` must be a subset of `languages`, separate from the original language. Names and descriptions are checked independently: each field is populated in every declared language or empty in all of them. An entire target language copied from the original is rejected. Submissions contain 1–10000 achievements, at most 65536 characters per text field and 512 per API name. Duplicate JSON keys, NUL, undeclared languages, mismatched IDs, unknown versions and files over 32 MiB are rejected. Automation canonicalizes valid uploads and rechecks bytes, hash, size, languages and counts at review and publication.

Run the Python standard-library command above from the repository root; use `--language` for a different original language. It anonymously reads structured data from Steam's current public achievement page and checks app ID, language and API names. This is not a stable official API: unavailable or changed pages produce an error without a file. The output must not exist, to preserve existing translations. Visible data is not certified as a complete schema, and hidden or unavailable achievements are never invented.

Generated candidates have `draft: true`, retain original text and leave target fields blank. Complete and review the translation, then remove `draft` or set it to `false` before [submitting JSON](CONTRIBUTING_EN.md). Attachment-free petitions attempt the same acquisition and provide a `petition-json` workflow artifact retained for 30 days (GitHub sign-in required to download). Failed acquisition keeps the petition open awaiting source data. The local command can regenerate a candidate without a workflow artifact.

Format 2 is display text only, not a BIN replacement, stats or unlock data. Older SATLI lite versions support format 1 only; library support does not establish client support.
