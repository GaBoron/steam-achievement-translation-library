# 开发与维护

[返回首页](../README.md) · [English](#english)

本指南面向修改脚本、前端和投稿自动化的开发者与维护者。分享译本使用 [贡献指南](CONTRIBUTING.md)；客户端读取数据使用 [接入指南](integration.md)；网站预览与部署见 [网站维护](website.md)。

## 环境与验证入口

CI 使用 Python 3.13 和 Node.js 24。数据校验与静态网站构建使用 Python 标准库，不需要 npm 依赖。仅在本地执行会清理旧仓库文件的维护操作时，Windows 需要 `pywin32`，Linux 需要可用的 `gio trash`；无法回收时应保留文件，并根据错误中的具体路径处理。

在仓库根目录运行：

```bash
python -m compileall -q workflow-scripts
python workflow-scripts/check_repository.py
```

仓库检查覆盖 Catalog、实际 BIN/JSON、语言与成就元数据、派生 JSON 和统计图的一致性。默认检查可能对既有 BIN 的不完整语言字段报告警告；新投稿和发生修改的游戏仍有严格覆盖检查，不应通过放宽检查绕过错误。

非翻译投稿 PR 的 CI 还会检查所有 JavaScript 模块语法并完整构建网站。翻译投稿 PR 则以待入库元数据覆盖 Catalog 后检查，避免要求它们提前修改共享目录。涉及授权、`/update` 或 `/force-refresh` 的修改，需验证对应事件路径；编译和文件校验不证明真实 GitHub 事件或 Steam 显示行为正确。

## 代码与数据职责

| 位置 | 职责与修改入口 |
| --- | --- |
| [catalog_v2.py](../workflow-scripts/catalog_v2.py) | 公开 Catalog V2 的结构、路径与规范化序列化 |
| [steam_schema.py](../workflow-scripts/steam_schema.py)、[standalone_translation.py](../workflow-scripts/standalone_translation.py)、[translation_json.py](../workflow-scripts/translation_json.py) | 无损 BIN 解析、独立格式 2 JSON 校验、从真实 BIN 派生格式 1 JSON |
| [submission_inputs.py](../workflow-scripts/submission_inputs.py)、[submission_validation.py](../workflow-scripts/submission_validation.py)、[schema_package.py](../workflow-scripts/schema_package.py) | 表单与附件读取、投稿校验、多版本包解析及文件保存 |
| [library_submission_bot.py](../workflow-scripts/library_submission_bot.py)、[translation_pr_maintenance.py](../workflow-scripts/translation_pr_maintenance.py) | issue 和 PR 事件入口；评论命令由相应 issue/PR 处理模块执行 |
| [pr_submission_data.py](../workflow-scripts/pr_submission_data.py)、[catalog_refresh.py](../workflow-scripts/catalog_refresh.py)、[catalog_finalization.py](../workflow-scripts/catalog_finalization.py) | 待入库元数据、派生数据刷新、合并后的 Catalog 发布 |
| [repository_validation.py](../workflow-scripts/repository_validation.py)、[translation_pr_validation.py](../workflow-scripts/translation_pr_validation.py) | 已发布仓库与投稿 PR 的不同验证边界 |
| [web/](../web/)、[website_build.py](../workflow-scripts/website_build.py) | 网站界面与静态资源打包，具体模块见 [网站维护](website.md) |

`index-v2.json` 是唯一公开 Catalog。正式文件位于 `files/<app_id>/<variant_id>/`，包括 BIN 与派生格式 1 JSON，或独立格式 2 JSON。客户端只读取 Catalog 列出的已发布版本。

修改相关处理时，保留这些数据约束：

- BIN 解析和序列化必须字节级 roundtrip，保留节点顺序、重复键、数值字节及非目标内容。
- 每项成就的名称与描述独立检查：每个字段在所有检测到的语言中都有内容，或在所有语言中均为空。
- App ID、商店链接、语言、成就数和文件元数据从可靠的文件或包数据推导。格式 1 JSON 来自 BIN；格式 2 JSON 自身是源数据。
- 版本 ID 和公开路径保持稳定。不要恢复 V1 `index.json`、游戏根目录 BIN 副本或逐游戏 `manifest.json`。
- 修改中文与英文公开文档时保持语义一致；保留 [许可证及第三方声明](../LICENSE.md)。

## 投稿如何进入公开目录

1. `.github/ISSUE_TEMPLATE/` 收集投稿、更新、请愿和错误报告。`translation-contribution.yml` 分派校验、评论修正、审核和合并事件；请愿由独立的 `translation_petition_bot.py` 处理。
2. 投稿校验后生成只涉及 `files/<app_id>/` 的审核 PR。`submission.json` 保存该游戏的待入库 Catalog 提案；每个版本的 `achievements.md` 提供审核对照。两者都由自动化维护，不是客户端接口。
3. 投稿 PR 检查在内存中叠加待入库提案，并核对实际文件。审核期间的文件可能与正式 Catalog 不同，因此不能用修改正式索引的方式规避检查。
4. 合并后的发布流程读取最新 `main` 上的所有待入库提案，刷新 Catalog、派生 JSON 和统计图，再清理已发布的临时审核元数据。网站由 Pages 工作流另行构建部署。

不同游戏可以独立审核。发布遇到推送竞争时，从最新 `main` 重新生成共享数据；不要把旧 PR 正文覆盖回已发布的条目。同一游戏的真实内容冲突需要维护者处理，`/force-refresh` 不保证解决此类冲突。

`/update` 与 `/force-refresh` 有投稿归属、用户权限和打开状态检查。保留这些边界；PR 刷新通过合并主分支保留历史。App ID 修正仅适用于尚未入库的新游戏，并须同步独立 JSON 内的 ID。JSON-only 升级 BIN 的文本保留约束见 [贡献指南](CONTRIBUTING.md#-更新时的格式限制)。

## 维护与故障定位

需要更新已提交的派生数据时，在修改源文件后运行：

```bash
python workflow-scripts/catalog_refresh.py
python workflow-scripts/check_repository.py
```

刷新命令会写入 Catalog、JSON 和统计图，应检查完整差异。不要手改 BIN 派生格式 1 JSON 或统计 SVG。单独修改说明文档无需重新生成这些数据。

- **投稿检查失败：** 从 issue/PR 的具体错误定位附件、表单或对应校验模块；提交者的修正入口见 [贡献指南](CONTRIBUTING.md)。
- **PR 已合并但网站未出现译本：** 先检查 **Translation library automation** 与 **Translation finalizer watchdog** 是否完成 Catalog 发布，再检查 **Translation library website**。区分尚未入库与网站尚未部署。
- **发布终结流程未完成：** 维护者可在 Actions 手动运行 **Translation finalizer watchdog**，指定已合并的 PR 编号 `pr_number` 或投稿分支 `head_branch`。该操作会更新远程仓库，只用于确认目标后的发布恢复。
- **网站构建失败：** 按 [网站维护](website.md) 的本地构建方式复现，检查 Catalog、文件校验与资源路径；不要直接修改生成的网站目录来修复源数据。

GitHub 事件处理脚本会修改 issue、PR 或仓库，不应当作普通本地检查直接运行。工作流触发条件与权限以 [.github/workflows/](../.github/workflows/) 为准。

## English

This guide is for developers and maintainers changing scripts, the frontend, or submission automation. Use [Contributing](CONTRIBUTING_EN.md) to share translations, [integration](integration.md#english) to consume data, and [website maintenance](website.md#english) for previews and deployment.

### Environment and validation

CI uses Python 3.13 and Node.js 24. Data checks and static builds use the Python standard library, without npm dependencies. Local maintenance that recycles obsolete repository files needs `pywin32` on Windows or working `gio trash` on Linux. If recycling fails, retain the file and use the exact path in the error to resolve it.

Run the compile and repository-check commands above from the repository root. They check the catalog, actual BIN/JSON files, language and achievement metadata, derived JSON, and statistics. The default check can warn about incomplete languages in existing BINs; new submissions and changed games receive strict coverage checks. Do not loosen validation to bypass errors.

CI also checks every JavaScript module's syntax and builds the whole website for non-translation PRs. Translation PRs instead validate an in-memory catalog overlaid with pending metadata, without changing the shared catalog early. Changes to authorization, `/update`, or `/force-refresh` need checks of the affected event path. Compilation and file validation do not establish real GitHub-event or Steam-display behavior.

### Code and data responsibilities

The code map above identifies the owning modules:

- `catalog_v2.py` owns public catalog validation, paths, and serialization.
- `steam_schema.py`, `standalone_translation.py`, and `translation_json.py` own lossless BIN handling, independent format 2 validation, and format 1 generation from real BINs.
- Submission input, validation, and package modules read forms and attachments and validate and store variants. `library_submission_bot.py` and `translation_pr_maintenance.py` dispatch issue and PR events to their handlers.
- `pr_submission_data.py`, `catalog_refresh.py`, and `catalog_finalization.py` own pending proposals, generated data, and post-merge publication. Repository and translation-PR validation have separate boundaries.
- `web/` and `website_build.py` own the interface and static packaging; see [website maintenance](website.md#english).

`index-v2.json` is the only public catalog. Published files live under `files/<app_id>/<variant_id>/`: a BIN with derived format 1 JSON, or standalone format 2 JSON. Clients read only published variants listed in the catalog.

Preserve these constraints when changing the relevant processing:

- BIN parsing and serialization require byte-identical roundtrips, preserving node order, repeated keys, numeric bytes, and non-target content.
- Check names and descriptions independently for each achievement: a field is populated in every detected language or empty in all of them.
- Derive App IDs, store links, languages, counts, and artifact metadata from reliable file/package data. Format 1 JSON is derived from BIN; format 2 JSON is itself source data.
- Keep variant IDs and public paths stable. Do not restore V1 `index.json`, game-root BIN copies, or per-game `manifest.json`.
- Keep Chinese and English public documentation semantically aligned and retain [licenses and third-party notices](../LICENSE.md).

### From submission to public catalog

1. Issue templates collect submissions, updates, petitions, and reports. `translation-contribution.yml` dispatches validation, comment corrections, review, and merge events; `translation_petition_bot.py` handles petitions separately.
2. A validated submission creates a review PR limited to `files/<app_id>/`. Generated `submission.json` holds the game's pending catalog proposal; per-variant `achievements.md` files support review. These are automation-owned, not client interfaces.
3. PR checks overlay proposals in memory and compare them with the actual files. Pending files can differ from the published catalog; changing the shared index early is not a way to fix this.
4. Post-merge publication consumes all pending proposals on current `main`, refreshes the catalog, derived JSON, and statistics, and removes published temporary review metadata. Pages builds and deploys the website separately.

Different games can be reviewed independently. Push races regenerate shared data from current `main`; do not replay old PR bodies over published entries. Real conflicts within one game need maintainer resolution; `/force-refresh` does not guarantee a resolution.

Preserve submission ownership, user authorization, and open-state checks on `/update` and `/force-refresh`. PR refresh merges main while preserving history. App ID corrections apply only to new, unpublished games and also update standalone JSON IDs. See [Contributing](CONTRIBUTING_EN.md#-format-restrictions-on-updates) for text-preservation requirements when upgrading JSON-only variants to BIN.

### Maintenance and diagnosis

After changing source data, use `catalog_refresh.py` and then `check_repository.py` as shown above when generated data needs updating. Refresh writes the catalog, JSON, and statistics; inspect the complete diff. Do not hand-edit BIN-derived format 1 JSON or the statistics SVG. Documentation-only changes do not need regeneration.

- **Submission check fails:** Follow its concrete issue/PR error to the attachment, form, or validation module. Contributor correction steps are in [Contributing](CONTRIBUTING_EN.md).
- **Merged translation is missing from the site:** Check catalog publication in **Translation library automation** and **Translation finalizer watchdog**, then **Translation library website**. Distinguish unpublished catalog data from a pending website deployment.
- **Finalization did not complete:** A maintainer can manually run **Translation finalizer watchdog** with a merged `pr_number` or submission `head_branch`. This updates the remote repository and is for publication recovery after confirming the target.
- **Website build fails:** Reproduce with the [local build](website.md#english), checking catalog data, artifact validation, and resource paths. Editing generated output does not repair source data.

GitHub event handlers modify issues, PRs, or the repository; do not run them as ordinary local checks. [.github/workflows/](../.github/workflows/) is authoritative for event triggers and permissions.
