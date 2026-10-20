# 贡献指南

感谢你为 Steam 成就翻译库投稿。表单提交后，机器人会校验附件并创建审核 PR；通常不需要手工 fork 仓库。

## 🧰 1. 准备译本

推荐使用以下工具生成符合投稿格式的文件：

- 🖥️ [Steam 成就翻译管理器](https://github.com/GaBoron/SATLI)：适合本地可视化编辑，可直接导出标准 BIN 或投稿 ZIP。
- 🤖 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill)：适合研究、翻译和验证，成品位于项目的 `final/` 目录。

可以直接投稿[格式 2 的独立 JSON](translation-json.md#独立-json格式-2)，也可以继续使用 BIN ZIP。SATLI lite 等工具导出的格式 1 JSON 不能独立投稿，须先按格式 2 补齐原文来源与目标语言记录；不要只改版本号。现有 SATLI lite 只支持格式 1，格式 2 需要客户端同步支持。

也可以使用其他编辑器，但提交前必须满足：

| 检查项 | 要求 |
| --- | --- |
| Steam app ID | 与 JSON/BIN 内容及附件文件名中的数字一致；机器人会据此生成商店地址 |
| 独立 JSON | `UserGameStatsSchema_<app_id>.json`，格式 2，译文完整且非 `draft`；无需 BIN 或打包 |
| BIN 文件名 | `UserGameStatsSchema_<app_id>.bin` |
| ZIP 文件名 | `UserGameStatsSchema_<app_id>.zip` |
| 单版本 ZIP | 根目录只能包含一个同名 BIN 或格式 2 JSON |
| 语言 | 由机器人从 BIN 或 JSON 识别；每项成就的名称和描述分别检查，必须在所有识别出的语言中都有内容，或在所有识别出的语言中均为空 |
| 游戏名 | 使用 Steam 商店名称；需要时可在原名后补充中文译名 |

先在 [翻译库网站](https://gaboron.github.io/steam-achievement-translation-library/?lang=zh) 搜索 app ID，确认这是新游戏还是已有条目的更新。

## 🧭 2. 选择入口

| 情况 | 提交入口 |
| --- | --- |
| 💬 希望有人翻译，有无原始文件均可 | [翻译请愿](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_zh.yml) |
| ➕ 已完成翻译，索引中没有该 app ID | [提交新翻译](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_zh.yml) |
| 🔄 已完成翻译，索引中已有该 app ID | [更新已有翻译](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_zh.yml) |
| ⚠️ 译本可能过期或不生效，但没有新版文件 | [报告文件错误](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_zh.yml) |

翻译请愿只需 App ID、游戏名和目标语言，附件可选；原始 schema 不会直接进入翻译库。公开数据可获取时，机器人提供目标语言留空的 JSON 草稿；否则标记待补充来源数据并保留请愿。下载与本地生成见[格式说明](translation-json.md#生成可翻译草稿)。更新已有译本时，请在摘要中说明新增、删除或修改了哪些内容。

## 📤 3. 提交与修正

1. 填写对应 issue 表单，上传独立 JSON 或 ZIP。
2. 等待机器人检查文件结构、成就 API name、来源与语言覆盖；BIN 额外检查 Binary KeyValues roundtrip。
3. 检查通过后，机器人会创建 PR 并请求维护者审核。

检查失败时，直接按机器人评论修正。来源 issue 仍打开时可以编辑表单内容；PR 创建后，请在 PR 评论中使用命令：

| 命令 | 用途 |
| --- | --- |
| `/update doc` + JSON 或 ZIP 附件 | 替换提交文件或完整多版本包 |
| `/update doc <variant_id>` + JSON 或 ZIP 附件 | 只替换已有的指定版本 |
| `/update id`、`name` + 新值 | 修改 App ID 或游戏名；修改 App ID 时会同步生成新商店地址 |
| `/update summary <摘要>` | 修改更新已有译本的摘要 |
| `/force-refresh` | 内容正确但自动化状态异常时，重新同步主分支、刷新当前 schema 元数据与成就审核表，并重试检查 |

> [!IMPORTANT]
> 命令和附件必须放在同一条评论中。只有原投稿者、PR 中列出的贡献者或维护者可以修改投稿；具体错误和可用命令以机器人回复为准。

## 🗂️ 多版本游戏

同一 app ID 需要保存多个可独立使用的 schema 时，把完整版本集合放进一个 ZIP，并在根目录加入 `translation-variants.json`：

```text
UserGameStatsSchema_123456.zip
├── translation-variants.json
├── UserGameStatsSchema_123456.bin
└── branch-name/
    └── UserGameStatsSchema_123456.bin
```

```json
{
  "variants": {
    "default": {
      "label": {
        "zh": "正式分支",
        "en": "Stable branch"
      }
    },
    "branch-name": {
      "label": {
        "zh": "测试分支",
        "en": "Beta branch"
      },
      "description": {
        "zh": "适用于游戏的公开测试分支",
        "en": "For the game's public beta branch"
      }
    }
  }
}
```

- 支持 1–16 个版本，必须包含 `default`；对象 key 就是版本 ID，`default` 是默认选择。
- 其他版本 ID 只能包含小写字母、数字和连字符，并与子目录同名。文件路径由版本 ID 自动推导，不要在清单中填写。
- 每个版本都要填写简短的双语 `label`；只有确实需要进一步解释适用范围时才添加双语 `description`。
- 不要填写版本号、`primary`、文件路径、哈希、大小、成就数、语言、App ID、贡献者、时间或 Issue/PR；这些都由自动化推导。不同版本不能是相同文件。
- 完整更新必须重新提交整个版本集合。只替换一个已有版本时，在更新表单填写版本 ID 并上传独立 JSON 或普通单版本 ZIP。
- 每个版本可以使用 BIN 或格式 2 JSON，目录与示例相同，只将对应文件扩展名改为 `.json`；同一版本不能同时上传两者，BIN 的格式 1 JSON 由机器人生成。JSON 的 `variant_id` 必须与目录一致。
- 每个版本分别自动识别语言和成就数；它们可以因适用的游戏版本不同而不同。

## ✅ 自动检查

机器人根据 app ID 生成商店链接，检查附件安全与大小、来源记录、成就 ID 和语言覆盖；BIN 额外检查 Binary KeyValues 字节级 roundtrip。请只提交你有权分享的译本。

每个译本保存于 `files/<app_id>/<variant_id>/`：BIN 版本包含自动生成的同名格式 1 JSON，独立版本只有格式 2 JSON。格式 1 配套文件不可手工修改；格式 2 投稿会严格校验并规范化。机器人在每个版本目录生成 `achievements.md`，直接在 PR 的 **Files changed** 中审核。文本按成就与字段分组，各语言相邻、每个字段独占一行；更新只列有变化的成就，并显示修改前后值。合并入库时自动将审核文件移至回收站。已收录译本的文本在 [网站](https://gaboron.github.io/steam-achievement-translation-library/?lang=zh) 预览。

每个审核 PR 只修改该游戏目录，待入库元数据保存在自动生成的 `submission.json` 中。检查会严格核对元数据与实际 BIN/JSON。合并后，自动化汇总主分支上的待入库游戏，更新 `index-v2.json`、统计和网站，并将已发布的 `submission.json` 移至回收站。不同游戏可独立审核；同一游戏的内容冲突需要维护者处理。`/force-refresh` 通过合并主分支保留投稿历史；BIN App ID 修正仅适用于尚未入库的新游戏。独立 JSON 的 ID 与来源不可自动改写，ID 错误时请关闭错误投稿并以正确 JSON 重新投稿。

已有 JSON-only 版本可通过更新投稿或 `/update doc` 补充真实 BIN，保留版本 ID、贡献者和首次收录时间；BIN 必须保留已接受的目标语言文字，随后重新生成格式 1 JSON。已有 BIN 版本不能被独立 JSON 替换；需要并存时增加新版本。JSON 合法不等于 BIN 通过 Steam 客户端验证。

Windows 维护环境需要 `pywin32`，Linux 需要可用的 `gio trash`；回收站不可用时保留待清理文件并报告具体路径。

修改工作流、脚本、Catalog、派生数据或 `files/` 数据时，请在仓库根目录运行：

```bash
python -m compileall -q workflow-scripts
python workflow-scripts/check_repository.py
```

客户端接口见 [数据接入指南](integration.md)。网站构建、预览与 GitHub Pages 配置见 [网站维护](website.md)。

权利与贡献许可见 [LICENSE.md](../LICENSE.md)。
