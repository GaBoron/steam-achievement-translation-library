# 贡献指南

[返回首页](../README.md) · [English](CONTRIBUTING_EN.md)

通过 issue 表单分享译本。机器人校验附件后创建审核 PR，由维护者审核；通常不需要手工 fork 仓库。只提交你有权分享的内容，贡献许可见 [LICENSE.md](../LICENSE.md)。

## 🧭 1. 选择入口

先在 [翻译库网站](https://gaboron.github.io/steam-achievement-translation-library/?lang=zh) 和 [待审核 PR](https://github.com/GaBoron/steam-achievement-translation-library/pulls) 中搜索 App ID，避免重复投稿。

| 情况 | 提交入口 |
| --- | --- |
| 希望有人翻译，有无原始文件均可 | [翻译请愿](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_zh.yml) |
| 已完成翻译，库中尚未收录该 App ID，且没有待审核投稿 | [提交新翻译](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_zh.yml) |
| 已完成翻译，库中已收录该 App ID | [更新已有翻译](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_zh.yml) |
| 译本可能过期或不生效，但没有新版文件 | [报告文件错误](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_zh.yml) |

翻译请愿填写 App ID、游戏名和目标 Steam 语言代码即可，原始 schema ZIP 可选。公开数据可获取时，机器人提供目标语言留空的 JSON 草稿；获取失败时保留请愿并标记待补充来源。草稿下载和本地生成见 [JSON 格式说明](translation-json.md#生成可翻译草稿)。请愿不是已完成的译本，不会直接入库。

## 🧰 2. 准备译本

推荐使用以下工具生成符合投稿格式的文件：

- 🖥️ [Steam 成就翻译管理器](https://github.com/GaBoron/SATLI)：适合本地可视化编辑，可直接导出标准 BIN 或投稿 ZIP。
- 🤖 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill)：适合研究、翻译和验证，成品位于项目的 `final/` 目录。

可以直接上传 [格式 2 的独立 JSON](translation-json.md)，也可以上传包含 BIN 或 JSON 的 ZIP。格式选择、格式 1 的独立投稿转换及文本限制以该格式说明为准。

也可以使用其他编辑器，但提交前必须满足：

| 检查项 | 要求 |
| --- | --- |
| Steam app ID | 与 JSON/BIN 内容及附件文件名中的数字一致；机器人会据此生成商店地址 |
| 独立 JSON | `UserGameStatsSchema_<app_id>.json`，格式 2，所有声明语言的文本符合覆盖要求；无需 BIN 或打包 |
| BIN 文件名 | `UserGameStatsSchema_<app_id>.bin` |
| ZIP 文件名 | `UserGameStatsSchema_<app_id>.zip` |
| 单版本 ZIP | 根目录只能包含一个同名 BIN 或格式 2 JSON |
| 大小 | 附件和单个 BIN/JSON 均不超过 32 MiB；多版本 ZIP 解压后的 schema 总量不超过 64 MiB |
| 语言 | 由机器人从 BIN 或 JSON 识别；每项成就的名称和描述分别检查，必须在所有识别出的语言中都有内容，或在所有识别出的语言中均为空 |
| 游戏名 | 使用 Steam 商店名称；需要时可在原名后补充中文译名 |

来源、术语说明和实际测试结果填写在备注中；更新投稿还需说明新增、删除或修改了哪些内容。不要将结构检查通过写成 Steam 内已验证有效。

## 📤 3. 提交与修正

1. 填写对应 issue 表单，上传独立 JSON 或 ZIP。
2. 等待机器人检查附件结构、成就 API name 与语言覆盖；BIN 额外检查 Binary KeyValues 字节级 roundtrip。格式 2 JSON 会规范化后保存。
3. 检查通过后，机器人创建 PR，并关闭、锁定来源 issue。维护者结合备注和成就对照表审核译文；合并后由自动化发布目录和网站。

检查失败时，按机器人回复修正。来源 issue 仍打开时可以编辑字段内容，保留 `###` 字段标题；PR 创建后，在该 PR 下评论：

| 命令 | 用途 |
| --- | --- |
| `/update doc` + JSON 或 ZIP 附件 | 替换提交文件或完整多版本包 |
| `/update doc <variant_id>` + JSON 或 ZIP 附件 | 只替换已有的指定版本 |
| `/update id <App ID>` | 修正尚未入库的新游戏 ID；已有游戏的更新不能改 ID |
| `/update name <游戏名>` | 修改游戏名 |
| `/update summary <摘要>` | 修改更新已有译本的摘要 |
| `/force-refresh` | 内容正确但自动化状态异常时，重新同步主分支、刷新当前 schema 元数据与成就审核表，并重试检查 |

> [!IMPORTANT]
> 命令和附件必须放在同一条评论中。只有原投稿者、PR 中列出的贡献者或维护者可以修改投稿；具体错误和可用命令以机器人回复为准。

在 PR 的 **Files changed** 中查看自动生成的 `achievements.md`：各语言按成就和字段相邻排列，更新投稿列出变化及前后值。合并发布后，该文件不再保留，已收录译文可在网站预览。文件校验不判断翻译质量，也不替代真实 Steam 验证。

## 🗂️ 多版本游戏

同一 App ID 需要保留适用于不同游戏分支或版本的译本时，将完整版本集合放进一个 ZIP，并在根目录加入 `translation-variants.json`。语言直接保存在每个译本中，不必为每种语言另建版本。

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
- 版本 ID 匹配 `[a-z0-9][a-z0-9-]{0,63}`；非默认版本与子目录同名。文件路径由版本 ID 自动推导，不要在清单中填写。
- 每个版本都要填写简短的双语 `label`；只有确实需要进一步解释适用范围时才添加双语 `description`。
- 不要填写版本号、`primary`、文件路径、哈希、大小、成就数、语言、App ID、贡献者、时间或 Issue/PR；这些都由自动化推导。不同版本不能是相同文件。
- 完整更新必须重新提交整个版本集合。只替换一个已有版本时，在更新表单填写版本 ID 并上传独立 JSON 或普通单版本 ZIP。
- 每个版本可以使用 BIN 或格式 2 JSON，目录与示例相同，只将对应文件扩展名改为 `.json`；同一版本不能同时上传两者，BIN 的格式 1 JSON 由机器人生成。JSON 的 `variant_id` 必须与目录一致。
- 每个版本分别自动识别语言和成就数；它们可以因适用的游戏版本不同而不同。

## 🔄 更新时的格式限制

已有 JSON-only 版本可通过更新投稿或 `/update doc` 补充真实 BIN，保留版本 ID、贡献者和首次收录时间。BIN 必须保留已接受的各语言文字，随后由自动化重新生成格式 1 JSON。已有 BIN 版本不能被独立 JSON 替换；需要并存时增加新版本。与已收录文件相同的投稿会被拒绝。

修改仓库脚本、工作流或维护发布流程时，参阅 [开发与维护](development.md)。客户端读取协议见 [数据接入指南](integration.md)。
