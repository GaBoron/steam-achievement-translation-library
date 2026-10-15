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

## English

This interface provides multilingual display text keyed by achievement API name. See the [data integration guide](integration.md#english) for catalog fields, download URLs, snapshots, and validation examples.

The example above defines the format. `version: 1` is the text format version, independent of the Catalog version. `app_id` and `variant_id` match the catalog entry; `source_sha256` identifies the source BIN. `languages` is an alphabetically sorted list of Steam language codes. `achievements` is keyed by API name, with each entry's `translations` holding language-specific `name` and `description`.

Each file is generated from its BIN, uses UTF-8, LF, and a final newline, and is limited to 32 MiB. Names and descriptions independently preserve empty fields. It contains display text only, without unlock state, progress, icons, or complete Binary KeyValues nodes.

Catalog `json.size` measures JSON bytes; `variant.sha256` and `source_sha256` identify the BIN. Verify versions, IDs, byte size, languages, achievement count, and source BIN hash when consuming data.
