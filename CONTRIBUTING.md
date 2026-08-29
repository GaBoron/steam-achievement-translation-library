# 贡献指南

感谢你为 Steam 成就翻译库投稿。表单提交后，机器人会校验附件并创建审核 PR；通常不需要手工 fork 仓库。

## 🧰 1. 准备译本

推荐使用以下工具生成符合投稿格式的文件：

- 🖥️ [Steam 成就翻译管理器](https://github.com/GaBoron/steam-achievement-translation-installer)：适合本地可视化编辑，可直接导出标准 BIN 或投稿 ZIP。
- 🤖 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill)：适合使用 Codex 研究、翻译和验证，成品位于项目的 `final/` 目录。

也可以使用其他编辑器，但提交前必须满足：

| 检查项 | 要求 |
| --- | --- |
| Steam app ID | 与 BIN 文件名和 ZIP 文件名中的数字一致；机器人会据此生成商店地址 |
| BIN 文件名 | `UserGameStatsSchema_<app_id>.bin` |
| ZIP 文件名 | `UserGameStatsSchema_<app_id>.zip` |
| 单版本 ZIP | 根目录只能包含一个同名 BIN |
| 语言 | 由机器人从 schema 自动识别；每项成就的名称和描述分别检查，必须在所有识别出的语言中都有内容，或在所有识别出的语言中均为空 |
| 游戏名 | 使用 Steam 商店名称；需要时可在原名后补充中文译名 |

先在 [INDEX.md](INDEX.md) 搜索 app ID，确认这是新游戏还是已有条目的更新。

> [!NOTE]
> 仓库目前处于 V1/V2 并行迁移阶段。投稿者仍只需上传一份 ZIP；自动化会同时生成 V2 权威数据和 V1 兼容数据。迁移截止时间与旧格式移除安排见 [README 的 V2 迁移状态](README.md#-v2-迁移状态)。

## 🧭 2. 选择入口

| 情况 | 提交入口 |
| --- | --- |
| 💬 只有 Steam 原始 schema，希望有人翻译 | [翻译请愿](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_zh.yml) |
| ➕ 已完成翻译，索引中没有该 app ID | [提交新翻译](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_zh.yml) |
| 🔄 已完成翻译，索引中已有该 app ID | [更新已有翻译](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_zh.yml) |
| ⚠️ 译本可能过期或不生效，但没有新版文件 | [报告文件错误](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_zh.yml) |

翻译请愿只记录需求，原始 schema 不会直接进入翻译库。更新已有译本时，请在摘要中说明新增、删除或修改了哪些内容。

## 📤 3. 提交与修正

1. 填写对应 issue 表单并上传 ZIP。
2. 等待机器人检查文件结构、Binary KeyValues roundtrip、成就 ID 和语言覆盖。
3. 检查通过后，机器人会创建 PR 并请求维护者审核。

检查失败时，直接按机器人评论修正。来源 issue 仍打开时可以编辑表单内容；PR 创建后，请在 PR 评论中使用命令：

| 命令 | 用途 |
| --- | --- |
| `/update doc` + ZIP 附件 | 替换提交文件或完整多版本包 |
| `/update doc <variant_id>` + ZIP 附件 | 只替换已有的指定版本 |
| `/update id`、`name` + 新值 | 修改 App ID 或游戏名；修改 App ID 时会同步生成新商店地址 |
| `/update summary <摘要>` | 修改更新已有译本的摘要 |
| `/force-refresh` | 内容正确但自动化状态异常时，完整重试检查 |

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
- 完整更新必须重新提交整个版本集合。只替换一个已有版本时，在更新表单填写版本 ID 并上传普通单版本 ZIP。
- 每个版本分别自动识别语言和成就数；它们可以因适用的游戏版本不同而不同。

## ✅ 自动检查

机器人会根据 app ID 生成商店链接，并检查 ZIP 安全与大小、Binary KeyValues 解析及字节级 roundtrip、成就 ID 唯一性、自动识别的语言覆盖和更新差异。请只提交你有权分享的翻译成果。

修改工作流、脚本、manifest、派生索引或 `files/` 数据时，请在仓库根目录运行：

```bash
python -m compileall -q workflow-scripts
python workflow-scripts/check_repository.py
```

权利与贡献许可见 [LICENSE.md](LICENSE.md)。
