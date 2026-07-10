# 贡献指南

感谢你为 Steam 成就翻译库投稿。为了让文件能被自动检查并进入索引，请尽量按下面的格式准备 issue 和附件。

## 投稿前检查

| 检查项 | 要求 |
| --- | --- |
| Steam app ID | 在 [INDEX.md](INDEX.md) 或 `index.json` 搜索数字 ID，确认应使用“新投稿”还是“更新已有文件” |
| 文件名 | 必须是 `UserGameStatsSchema_<app_id>.bin` |
| 压缩包 | 上传文件必须是 `UserGameStatsSchema_<app_id>.zip` 。单版本 ZIP 只放一个同名 `.bin` ；多版本 ZIP 使用 `translation-variants.json` 声明全部版本 |
| 语言字段 | 写出文件中已经完整包含“成就名称”和“成就描述”的全部 Steam 语言代码；多个代码必须用半角逗号分隔 |
| 游戏名 | 按 Steam 商店显示填写；如果 Steam 显示名不是中文，可以写成“Steam 原名 中文译名” |

## 新投稿

适用于库里还没有该 Steam app ID 的游戏。

1. 打开 issue 模板“提交 Steam 成就翻译”。
2. 填写游戏名、Steam app ID、Steam 商店地址和语言代码。
3. 上传 `UserGameStatsSchema_<app_id>.zip`。
4. 自动化会检查 app ID、商店链接、ZIP 结构、schema 可解析性、成就 ID 唯一性和语言覆盖。
5. 检查通过后会创建 PR，并自动请求维护者审查。

如果库里已经有该 app ID，新投稿会被拒绝；请改用“更新已有 Steam 成就翻译”模板。

如果自动检查未通过且 issue 仍然 open，可以直接编辑 issue 描述修正字段内容，也可以在评论区使用 `/update <类型> <参数>`；编辑描述时不要改 `###` 字段标题。初审通过后，来源 issue 会被关闭并锁定。此后如果 PR 需要改内容，请在 PR 下评论 `/update <类型> <参数>` 命令。

## 更新已有文件

适用于库里已经合并过该 Steam app ID，但游戏更新或翻译修正后需要替换文件。

1. 打开 issue 模板“更新已有 Steam 成就翻译”。
2. 填写同一个 Steam app ID。自动化只检查 `index.json` 中已合并的条目，正在打开的 PR 不算已收录。
3. 在“更新内容摘要”中说明变化：新增成就、删除成就、修改翻译、补充语言字段或修正错误。
4. 上传新版 `UserGameStatsSchema_<app_id>.zip`。
5. 自动化会先和库里的当前文件做字节级比较；如果完全相同，会拒绝创建 PR。
6. 如果文件不同，PR 描述会列出新增、删除和修改的成就 ID，方便维护者审核。

## 一个游戏包含多个版本

如果同一个 Steam app ID 需要保存多个可独立使用的 schema（例如原版、带解锁条件版或不同发行分支），请把全部版本放进同一个 `UserGameStatsSchema_<app_id>.zip`，并在 ZIP 根目录加入 `translation-variants.json`：

```text
UserGameStatsSchema_123456.zip
├── translation-variants.json
├── UserGameStatsSchema_123456.bin
└── version-description/
    └── UserGameStatsSchema_123456.bin
```

清单格式：

```json
{
  "version": 1,
  "variants": [
    {
      "variant_id": "default",
      "primary": true,
      "file": "UserGameStatsSchema_123456.bin",
      "note_zh": "原版",
      "note_en": "Original"
    },
    {
      "variant_id": "version-description",
      "primary": false,
      "file": "version-description/UserGameStatsSchema_123456.bin",
      "note_zh": "版本描述",
      "note_en": "version description"
    }
  ]
}
```

- 清单支持 1–16 个版本，必须且只能有一个 `primary: true` 的主版本；主版本 ID 固定为 `default`。通常只有多版本投稿需要清单，但把多版本集合缩减为单版本时也应提交只含主版本的清单。
- 其他 `variant_id` 只能使用小写字母、数字和连字符，文件必须放在同名子目录中。
- `note_zh` 和 `note_en` 必须填写简短的单行版本说明；索引会用它们帮助用户选择文件。
- 表单中的语言列表适用于包内所有版本。机器人会逐个检查 roundtrip、唯一成就 ID、语言覆盖、SHA-256 和成就数。
- Steam 原始 `english` 字段允许官方有意留空描述，但英文名称仍不能为空；其他声明语言仍要求名称和描述都完整。
- 不同 `variant_id` 不能提交字节级完全相同的文件；没有实际差异的重复版本不会进入索引。
- 多版本游戏的整包更新必须再次提交完整清单，新增、删除和替换会作为一个版本集合处理。只替换一个现有版本时，在更新模板填写“要更新的版本 ID”，并上传普通单版本 ZIP；此时不能修改全局语言列表。

## PR 中的 `/update` 命令

PR 创建后，PR 标题和描述由机器人维护。需要修改时，在 PR 评论区使用下面的命令；机器人会更新文件、索引和 PR 描述。

> [!IMPORTANT]
> `/update` 后面必须写明类型。单独评论 `/update` 不会更新文件；机器人会回复具体错误。除 `doc` 外，其他类型还必须在同一行写参数。

| 命令 | 作用 |
| --- | --- |
| `/update doc` + 附件 | 替换单版本文件，或用带清单的多版本包原子替换完整版本集合 |
| `/update doc <variant_id>` + 附件 | 只替换多版本 PR 中指定的现有版本；新增版本必须提交完整多版本包 |
| `/update id <Steam app ID>` | 修改普通投稿/更新 PR 的 Steam app ID，并同步重命名文件路径；报告过期 PR 不支持此命令 |
| `/update name <游戏名>` | 修改游戏名；如果 Steam 显示名不是中文，可以写“Steam 原名 中文译名” |
| `/update store <Steam 商店地址>` | 修改 Steam 商店地址，地址中的 app ID 必须和当前 app ID 一致 |
| `/update languages <语言代码>` | 替换语言代码列表；必须写出文件中实际存在的全部语言，多个代码用半角逗号分隔 |
| `/update summary <摘要>` | 修改更新 PR 中的“更新内容摘要” |
| `/update reason <说明>` | 修改报告过期 PR 的过期说明 |
| `/update reference <来源>` | 修改报告过期 PR 的参考来源 |

替换文件时，请把命令和附件放在同一条 PR 评论里，例如：

```markdown
/update doc
[UserGameStatsSchema_123456.zip](https://github.com/user-attachments/files/.../UserGameStatsSchema_123456.zip)
```

如果命令类型写错、漏写参数、`/update doc` 没有附加 ZIP，机器人会评论说明错误位置，PR 不会被修改。

在来源 issue 仍然打开时，可使用 `/update variant <variant_id>` 修改“要更新的版本 ID”，使用 `/update variant clear` 清空它；也可以直接使用 `/update doc <variant_id>` 并附加 ZIP，同时更新附件和版本 ID。

为防止第三方篡改投稿，issue 中的 `/update` 仅允许原 issue 投稿者或仓库维护者执行；PR 中的 `/update` 仅允许 PR 描述列出的贡献者、报告过期 PR 的报告者或仓库维护者执行。不同 PR 类型只接受与其内容相关的命令：新投稿不接受 `summary`，报告过期 PR 只接受 `name`、`store`、`reason` 和 `reference`。

语言更新不是增删模式。评论 `/update languages schinese, english` 表示文件只包含 `schinese` 和 `english`；没写的语言会视为不存在。

当维护者请求修改时，PR 会自动加上 `等待更新` label。之后由该投稿的贡献者、过期报告者或仓库维护者在 PR 下评论，机器人会自动移除这个 label；如果评论是 `/update` 命令，机器人还会尝试同步更新 PR。无关用户的评论不会改变标签或投稿内容。

来源 issue 关闭后会锁定；PR 合并后也会锁定。除非是重新提交一个“更新已有 Steam 成就翻译”issue，否则不要再修改已关闭的讨论。

## 报告文件过期

适用于你发现某个已收录游戏可能已经过期，但暂时没有新版文件。

1. 打开 issue 模板“报告成就文件过期”。
2. 填写已收录的 Steam app ID、商店地址和过期说明。
3. 说明证据，例如游戏更新日期、成就数量变化、本地 schema 修改时间、缺少新成就或官方公告链接。
4. 自动化会创建 PR，把索引中的该游戏标记为“可能过期”。

如果你已经准备好新版文件，请直接使用更新模板，不需要先开过期报告。

## 自动化会检查什么

| 检查 | 说明 |
| --- | --- |
| ID 与链接 | Steam 商店地址中的 app ID 必须和表单填写一致 |
| ZIP 安全 | ZIP 内不能有目录穿越、绝对路径、重复路径或清单未声明的文件；多版本解压后总大小不超过 64 MiB |
| 文件大小 | 上传文件和 schema 文件都有 32 MiB 上限 |
| 二进制解析 | schema 必须能被 Binary KeyValues 解析器读取并字节级 roundtrip |
| 成就结构 | 必须能找到成就名称、描述和非空唯一的 API name |
| 语言覆盖 | 勾选的每个语言字段都必须在每个版本中为每个成就提供名称和描述 |
| 更新差异 | 更新 issue 必须和库中现有文件不同，并在 PR 中展示新增、删除、修改 |

## 仓库维护与本地检查

本仓库的 workflow 脚本只使用 Python 标准库，自动化固定使用 Python 3.13。提交脚本、工作流、索引或 `files/` 数据修改前，请在仓库根目录运行：

```bash
python -m compileall -q workflow-scripts tests
python -m unittest discover -s tests -v
python workflow-scripts/check_repository.py
```

最后一条命令会检查 `index.json` 结构与排序、所有索引文件路径和大小、SHA-256、Binary KeyValues 字节级 roundtrip、成就 ID/数量、语言覆盖，以及 `INDEX.md` / `INDEX_EN.md` 是否与 JSON 同步。历史数据中的不完整语言字段默认报告为警告，以免破坏已有兼容性；清理完历史数据后可用 `--strict-language-coverage` 将其升级为错误。GitHub Actions 会在 `main` 的 push 和 pull request 上运行同一组检查。

## 版权与来源

请只提交你有权分享的翻译成果。原始游戏内容、成就文本、Steam schema 内容及相关文件仍归对应权利方所有；你提交的自有翻译部分会按 [LICENSE.md](LICENSE.md) 中的贡献许可供社区使用。
