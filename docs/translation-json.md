# 翻译 JSON 格式

[返回首页](../README.md) · [English](#english)

本格式提供按成就 API name 索引的多语言显示文本。格式 1 由真实 BIN 派生，格式 2 可以独立投稿；二者共用文本结构。Catalog、下载路径与文件校验见 [数据接入指南](integration.md)，投稿入口见 [贡献指南](CONTRIBUTING.md)。

## 文件结构

以下格式 2 示例只说明结构，不代表真实游戏数据：

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

| 字段 | 约定 |
| --- | --- |
| `version` | JSON 格式版本：`1` 或 `2`，与 Catalog 版本相互独立 |
| `app_id` | Steam App ID 的数字字符串，与文件名及 Catalog 一致 |
| `variant_id` | Catalog 版本 ID；默认版本的 ID 为 `default`，匹配 `[a-z0-9][a-z0-9-]{0,63}` |
| `languages` | 排序且不重复的 Steam 语言代码；格式 2 支持 1–64 种 |
| `achievements` | 以成就 API name 为唯一键的对象；每项只包含 `translations` |
| `translations` | 键恰好覆盖所有声明语言，每种语言都包含 `name` 和 `description` 字符串 |
| `source_sha256` | 仅格式 1 存在，标识源 BIN，而非 JSON 自身的哈希 |

格式 2 恰好包含示例中的五个顶层字段，不含 `source_sha256`、来源副本、目标语言列表或草稿状态。原文需要保留时，作为普通语言在 `translations` 中保存一次；来源链接、术语和测试说明写在投稿备注中。

发布文件使用 UTF-8、LF 和结尾换行，名称为 `UserGameStatsSchema_<app_id>.json`，存于 `files/<app_id>/<variant_id>/`。格式 1 随 BIN 自动生成，不应手改；格式 2 自身是源文件，由投稿自动化校验和规范化。两者统一收录在 Catalog 中。

## 校验与使用范围

独立格式 2 投稿的主要限制为：

- 包含 1–10000 项成就；API name 非空、不含控制字符，且不超过 512 字符。
- 每个文本字段不超过 65536 字符，不含 NUL；文件不超过 32 MiB。
- 不允许重复 JSON 键、额外结构字段、未声明语言、错误 ID 或未知版本。语言代码匹配 `[a-z][a-z0-9_]{1,31}`。
- 每项成就的名称和描述独立检查：每个字段必须在所有声明语言中都有内容，或在所有语言中均为空。可以有名称但无描述，反之亦可；不要为本来为空的字段编造内容。

自动化会规范化合法投稿，并在审核与发布时核对文件和元数据。结构合法不能证明译文准确或真实 Steam 显示有效。

JSON 只包含显示文本，没有解锁状态、进度、图标或完整 Binary KeyValues 节点，不能作为 BIN 安装或用于修改统计、解锁数据。独立格式 2 需要支持 JSON-only 条目的客户端；SATLI lite 0.2.0+ 支持格式 1 和 2。具体下载校验与旧客户端限制见 [接入指南](integration.md#应用前的检查)。

## 独立投稿已有文本

已有格式 1 JSON 可以另存为独立投稿文件：将 `version` 改为 `2`，移除 `source_sha256`，保留五个共享顶层字段，并核对 App ID、版本 ID、语言和译文。不要直接修改仓库中仍与 BIN 配套的格式 1 文件。

上传独立 JSON 不需要源 BIN 或 ZIP。多版本包以及 JSON-only 升级真实 BIN 时的限制，以 [贡献指南](CONTRIBUTING.md) 为准。文件格式转换不补全游戏 schema，也不验证译文来源；请在备注中提供实际使用的来源。

## 生成可翻译草稿

在仓库根目录运行，只使用 Python 标准库；将输出路径替换为自己的新文件位置：

```bash
python workflow-scripts/steam_public_achievements.py 440 --targets schinese --output /path/to/UserGameStatsSchema_440.json
```

`--targets` 接受逗号分隔的 Steam 语言代码，`--language` 选择原文语言，默认 `english`。目标语言必须与原文不同。输出路径必须不存在，以免覆盖已有译文。

该命令匿名读取 Steam 当前公开成就页面中的结构化数据，检查 App ID、语言和 API name。页面不是稳定官方 API；数据不可获取或页面结构改变时，命令报错而不生成候选文件。公开列表不代表完整 schema，不会补造隐藏或未公开成就。

候选文件采用同一格式 2 结构：获取到的原文保留一次，目标语言留空。填写并审核译文后按 [贡献指南](CONTRIBUTING.md) 上传；空白目标字段会被语言覆盖检查拒绝，不会自动把原文复制成译文。命令输出会记录来源页面、原文语言和获取时间，请随投稿保留来源说明。

无附件请愿采用相同获取流程，通过 `petition-json` 工作流附件提供候选文件，保留 30 天，下载需要登录 GitHub。请愿回复记录来源；获取失败时保留请愿并说明待补充来源。附件过期后可用本地命令重新尝试获取，结果取决于届时公开页面的可用数据。

## English

[Home](../README_EN.md)

This format supplies multilingual display text keyed by achievement API name. Format 1 is generated from a real BIN; format 2 can be submitted independently. Both share the text structure above. See [integration](integration.md#english) for catalog, paths, and download checks, and [Contributing](CONTRIBUTING_EN.md) for submission routes. The example is illustrative, not real game data.

### File structure

Both formats contain `version`, `app_id`, `variant_id`, `languages`, and `achievements`:

- `version` is JSON format `1` or `2`, independent of the catalog version.
- `app_id` is a numeric string matching the filename and catalog. `variant_id` is the catalog variant ID, normally `default`, matching `[a-z0-9][a-z0-9-]{0,63}`.
- `languages` is a sorted, unique list of Steam language codes; format 2 supports 1–64 languages.
- Each unique achievement API name maps to an object containing only `translations`. Its keys cover exactly the declared languages, each with string `name` and `description` fields.
- Format 1 additionally contains `source_sha256`, identifying the source BIN rather than the JSON's own hash.

Format 2 contains exactly the five shared top-level fields. It has no `source_sha256`, duplicate source snapshot, target-language list, or draft status. Retain originals once as ordinary translation languages; put sources, terminology, and test information in submission notes.

Published files use UTF-8, LF, and a final newline, named `UserGameStatsSchema_<app_id>.json` under `files/<app_id>/<variant_id>/`. Format 1 is generated alongside BIN and must not be hand-edited. Format 2 is itself source data, validated and canonicalized by submission automation. Both share the catalog.

### Validation and scope

Standalone format 2 submissions require:

- 1–10000 achievements; nonempty API names of at most 512 characters, without control characters.
- Text fields of at most 65536 characters, without NUL; at most 32 MiB per file.
- No duplicate JSON keys, extra structural fields, undeclared languages, mismatched IDs, or unknown versions. Language codes match `[a-z][a-z0-9_]{1,31}`.
- Independent coverage checks for each achievement's name and description: a field is populated in every declared language or empty in all. A name without a description, or the reverse, is valid; do not invent text for unused fields.

Automation canonicalizes valid submissions and checks files and metadata during review and publication. Structural validity does not prove translation accuracy or real Steam display compatibility.

JSON has display text, without unlock state, progress, icons, or complete Binary KeyValues nodes. It cannot be installed as BIN or used to change stats or unlock data. Standalone format 2 needs a client supporting JSON-only variants; SATLI lite 0.2.0+ supports formats 1 and 2. See [integration](integration.md#check-before-applying) for download checks and older-client limitations.

### Submit existing text independently

Save a separate copy of format 1 text, change `version` to `2`, remove `source_sha256`, retain the five shared fields, and check app and variant IDs, languages, and translations. Do not change a repository format 1 file that remains paired with a BIN.

Standalone JSON needs no source BIN or ZIP. Follow [Contributing](CONTRIBUTING_EN.md) for multi-variant packages and restrictions on upgrading JSON-only variants to real BIN. Conversion does not reconstruct a schema or verify translation provenance; include the sources actually used in the notes.

### Generate a candidate

Run the standard-library command above from the repository root, choosing a new output path. `--targets` takes comma-separated Steam language codes. `--language` selects the source language, defaulting to `english`; targets must differ from it. The output must not exist, preserving existing translations.

The tool anonymously reads structured data from Steam's current public achievement page and checks App ID, language, and API names. This is not a stable official API. Unavailable data or changed page structure causes an error without a candidate file. Visible data is not a complete schema, and hidden or unavailable achievements are not invented.

Candidates use the same format 2 structure, retain original text once, and leave targets blank. Complete and review the translation, then [submit it](CONTRIBUTING_EN.md). Coverage checks reject blank target fields; originals are never automatically copied as completed translations. CLI output records the source URL, source language, and retrieval time; retain that provenance in submission notes.

Attachment-free petitions use the same acquisition process and provide a `petition-json` workflow artifact retained for 30 days, requiring GitHub sign-in to download. The reply records provenance. Failed acquisition keeps the petition open awaiting source data. After artifact expiry, the local command can attempt a fresh acquisition using the public data available at that time.
