# 翻译 JSON 格式

本接口提供按成就 API name 索引的多语言显示文本。格式 1 和格式 2 共用相同的文本结构；格式 1 额外关联源 BIN，格式 2 可以独立投稿。Catalog 与下载校验见[数据接入指南](integration.md)。

```json
{
  "version": 2,
  "app_id": "123456",
  "variant_id": "default",
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

示例仅说明结构，不代表真实游戏数据。

| 字段 | 约定 |
| --- | --- |
| `version` | 显示文本格式版本，`1` 或 `2`，独立于 Catalog 版本 |
| `app_id` / `variant_id` | 对应 Catalog 中的游戏与版本 ID |
| `languages` | Steam 语言代码，按字母序排列且不重复 |
| `achievements` | 以 API name 为唯一键；每项 `translations` 包含所有声明语言的 `name` 和 `description` |
| `source_sha256` | 仅格式 1 存在，表示生成该文件的源 BIN 哈希；格式 2 不含此字段 |

格式 2 只有示例中的五个顶层字段，不保存来源副本、目标语言列表或草稿状态。原文需要保留时，作为普通语言放在 `translations` 中一次。来源链接和说明写入投稿备注；公开数据获取工具在命令输出或请愿回复中记录页面地址、原文语言及获取时间。

两种格式均使用 UTF-8、LF 与结尾换行，文件名为 `UserGameStatsSchema_<app_id>.json`，位于同一个 `files/<app_id>/<variant_id>/` 目录，统一列入 `index-v2.json` 的 `games/variants`。格式 1 由真实 BIN 自动生成；格式 2 可以在没有 BIN 时独立存在，无需额外目录或索引分区。不要手工改动仍与 BIN 配套的格式 1 文件。

格式 1 的 `source_sha256` 和 Catalog 的 `variant.sha256` 都指源 BIN。格式 2 通过 `variant.format: "json"` 识别，不声明 BIN `sha256` / `size`，Catalog 的 `json.sha256` 校验 JSON 自身的规范化字节（含结尾换行），`json.size` 是对应字节数。已有格式 1 JSON 独立投稿时，可将 `version` 改为 `2` 并移除 `source_sha256`，再核对 ID、语言及译文。

## 校验与使用范围

投稿必须包含 1–10000 项成就，每个 API name 非空且不超过 512 字符，每个文本字段不超过 65536 字符，文件不超过 32 MiB。拒绝重复 JSON 键、NUL、未声明语言、错误 ID 和未知版本。每项成就的名称与描述分别检查：每个字段必须在所有声明语言中有内容，或在所有语言中全部为空。机器人规范化合法附件，并在审核与发布时核对文件内容、哈希、大小、语言及成就数。

JSON 只包含显示文本，没有解锁状态、进度、图标或完整 Binary KeyValues 节点。格式 2 不能用于 BIN 覆盖、统计或解锁数据。客户端必须识别 JSON-only Catalog 版本和格式 2 才能使用；仅支持格式 1 的旧版 SATLI lite 需要更新，详见[接入指南](integration.md#json-only-版本)。

## 生成可翻译草稿

在仓库根目录运行（只使用 Python 标准库）：

```bash
python workflow-scripts/steam_public_achievements.py 440 --targets schinese --output /path/to/UserGameStatsSchema_440.json
```

需要其他原文语言时使用 `--language`。该命令匿名读取 Steam 当前公开成就页面的结构化数据，并核对 App ID、语言和 API name。页面不是稳定的官方 API；改版或数据不可获取时会报错，不生成文件。输出路径必须不存在，避免覆盖已有译文。可见列表不代表完整 schema，也不会补造隐藏或未公开成就。

候选 JSON 使用相同的格式 2 结构：获取到的原文保留一次，目标语言为空，没有额外状态字段。填写并审核译文后直接按[贡献指南](CONTRIBUTING.md)上传。目标语言未填时会被语言覆盖检查拒绝；内容是否为正确翻译仍由审核者判断，不会自动把原文复制到目标语言。

无附件请愿采用同样的获取流程，在工作流的 `petition-json` 附件中提供候选文件（保留 30 天，下载需登录 GitHub），并在回复中记录来源。获取失败时保留请愿并说明待补充来源。上述命令可在本地重新生成，不依赖工作流附件。

## English

This interface provides multilingual display text keyed by achievement API name. Formats 1 and 2 share the text structure shown above. Format 1 additionally identifies its source BIN; format 2 can be submitted independently. See the [data integration guide](integration.md#english) for catalog fields and download validation. The example is illustrative, not real game data.

### Shared structure and version differences

Both formats contain `version`, `app_id`, `variant_id`, `languages` and `achievements`. IDs match the catalog. `languages` is a sorted, unique list of Steam language codes. Each unique achievement API name maps to `translations`, with `name` and `description` for every declared language. Format 1 additionally requires `source_sha256`, the source BIN hash. Format 2 omits it and contains exactly the five shared top-level fields.

Format 2 stores no duplicate source snapshot, target-language list or draft status. Retained original text appears once as a normal language in `translations`. Put source links and explanations in submission notes. The public-data tool records its page URL, source language and retrieval time in CLI output or the petition reply.

Both formats use UTF-8, LF and a final newline, with the same `UserGameStatsSchema_<app_id>.json` filename under `files/<app_id>/<variant_id>/`. All variants are listed together in Catalog `games/variants`. Format 1 is generated from a real BIN; format 2 can exist without a BIN and needs no separate directory or catalog partition. Do not edit a generated format 1 sidecar manually.

Format 1 `source_sha256` and catalog `variant.sha256` identify the BIN. Standalone format 2 uses `variant.format: "json"`, omits BIN `sha256` and `size`, and is checked against `json.sha256` and `json.size` using its own canonical bytes, including the final newline. To submit existing format 1 text independently, set `version` to `2`, remove `source_sha256`, and check the IDs, languages and translation.

### Validation and scope

Submissions contain 1–10000 achievements, at most 512 characters per nonempty API name, 65536 per text field and 32 MiB per file. Duplicate JSON keys, NUL, undeclared languages, mismatched IDs and unknown versions are rejected. Names and descriptions are checked independently: each field is populated in every declared language or empty in all of them. Automation canonicalizes uploads and rechecks content, hash, size, languages and counts at review and publication.

JSON contains display text, without unlock state, progress, icons or complete Binary KeyValues nodes. Format 2 is not a BIN replacement, stats or unlock data. Clients must support JSON-only catalog variants and format 2; older SATLI lite versions supporting format 1 only require an update. See [integration](integration.md#json-only-variants).

### Generate a candidate

Run the standard-library command above from the repository root; use `--language` for a different original language. It anonymously reads structured data from Steam's current public achievement page and checks app ID, language and API names. This is not a stable official API: unavailable or changed pages produce an error without a file. The output must not exist, to preserve existing translations. Visible data is not certified as a complete schema, and hidden or unavailable achievements are never invented.

Candidates use the same format 2 structure, retain original text once and leave target fields blank, without extra state fields. Complete and review the translation, then [submit the JSON](CONTRIBUTING_EN.md). Language coverage rejects unfinished target fields; translation correctness still requires review. The tool never copies originals into targets as completed translations.

Attachment-free petitions attempt the same acquisition and provide a `petition-json` workflow artifact retained for 30 days (GitHub sign-in required). The reply records provenance. Failed acquisition keeps the petition open awaiting source data. The local command can regenerate a candidate without a workflow artifact.
