# 翻译 JSON 接口

BIN 保留为 SATLI 本体使用的源文件，JSON 是新增的派生数据，源文件与投稿约定保持不变。运行 `python workflow-scripts/catalog_refresh.py` 会生成所有 V2 版本的 JSON，同步默认旧路径的 BIN/JSON，并更新 `index-v2.json` 中各版本的 `json` 元数据。文件使用 UTF-8、LF 和结尾换行，输出不含生成时间，重复刷新结果一致。

投稿、PR 文件更新、App ID 重命名和 `/force-refresh` 在 PR 阶段同步并提交上述文件及 V2 元数据。合并后继续生成 `index.json`、人类可读索引和统计；PR 检查允许这些派生索引暂时未刷新，但 BIN、JSON 与默认旧路径必须一致。

客户端下载 `index-v2.json` 后，按 App ID 与版本 ID 推导路径：

```text
files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.json
```

每个版本增加 `"json": {"version": 1, "size": 1234}`；`size` 为 JSON 的 UTF-8 字节数，不是 BIN 大小。现有 `sha256` 字段仍表示源 BIN。没有 `json` 元数据的旧 Catalog 不保证存在配套文件，客户端应说明需要更新数据源。

```json
{
  "version": 1,
  "app_id": "123456",
  "variant_id": "default",
  "source_sha256": "<源 BIN 的 sha256>",
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

成就键为 API name，客户端按 App ID 与 API name 替换名称和描述；空字段保留为空。下载后核对格式版本、App ID、版本 ID、字节数、语言列表、成就数和 `source_sha256`，以识别错配或刷新期间的数据变化。单文件上限 32 MiB。此接口仅提供显示文本，不包含解锁状态、进度、图标或用于写回 BIN 的完整节点。

贡献者自有译文及第三方内容的权利说明仍适用，见 [LICENSE.md](../LICENSE.md)。客户端展示游戏条目时应保留 Catalog 中的贡献者与翻译库来源链接。

更新 ZIP 移除旧版本时，自动化会将对应 BIN、JSON 和成就目录文件移到系统回收站。Windows 维护环境需有 `pywin32`，Linux 需有可用的 `gio trash`；回收站不可用时保留文件并报告具体路径。

## English

BIN remains the source file used by SATLI; JSON is an additional derivative, without changing submissions or the V1/V2 BIN contract. Run `python workflow-scripts/catalog_refresh.py` to regenerate all variant JSON sidecars, synchronize legacy-default BIN/JSON copies, and update V2 `json` metadata. Output uses UTF-8, LF, a final newline, and no generated timestamp, so repeated refreshes are deterministic.

Submissions, PR file updates, app ID renames, and `/force-refresh` synchronize and commit these files and V2 metadata in the PR. Post-merge refreshes regenerate `index.json`, human-readable indexes, and statistics. PR checks permit those derived indexes to lag, while BIN, JSON, and legacy-default copies must agree.

Derive `files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.json` from Catalog V2. Each variant's `json` object contains `version: 1` and the JSON's UTF-8 byte `size`. The existing variant `sha256` still identifies the source BIN. Older catalogs without `json` metadata do not promise JSON downloads.

The example above defines the format: `achievements` is keyed by API name; each entry contains every detected language's `name` and `description`, preserving empty fields. Match app ID and API name when replacing text. Verify the format, app and variant IDs, byte count, language list, achievement count, and source BIN identity after downloading. The limit is 32 MiB. This interface contains display text only, without unlock state, progress, icons, or the complete nodes needed to write a BIN.

The [rights notice](../LICENSE.md) continues to apply. Display the catalog's contributors and a source link alongside game entries.

Removing an obsolete variant sends its BIN, JSON, and achievement catalog to the system trash. Windows maintenance requires `pywin32`; Linux requires working `gio trash`. If recycling is unavailable, files remain in place and the operation reports the affected path.
