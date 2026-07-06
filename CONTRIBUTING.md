# 贡献指南

感谢你为 Steam 成就翻译库投稿。为了让文件能被自动检查并进入索引，请尽量按下面的格式准备 issue 和附件。

## 投稿前检查

| 检查项 | 要求 |
| --- | --- |
| Steam app ID | 在 [INDEX.md](INDEX.md) 或 `index.json` 搜索数字 ID，确认应使用“新投稿”还是“更新已有文件” |
| 文件名 | 必须是 `UserGameStatsSchema_<app_id>.bin` |
| 压缩包 | 上传 `UserGameStatsSchema_<app_id>.zip`，ZIP 内只放一个同名 `.bin` 文件 |
| 语言字段 | 勾选或填写文件中已经完整包含“成就名称”和“成就描述”的 Steam 语言代码 |
| 游戏名 | 按 Steam 商店显示填写；如果 Steam 显示名不是中文，可以写成“Steam 原名 中文译名” |

## 新投稿

适用于库里还没有该 Steam app ID 的游戏。

1. 打开 issue 模板“提交 Steam 成就翻译”。
2. 填写游戏名、Steam app ID、Steam 商店地址和语言代码。
3. 上传 `UserGameStatsSchema_<app_id>.zip`。
4. 自动化会检查 app ID、商店链接、ZIP 结构、schema 可解析性、成就 ID 唯一性和语言覆盖。
5. 检查通过后会创建 PR，并自动请求维护者审查。

如果库里已经有该 app ID，新投稿会被拒绝；请改用“更新已有 Steam 成就翻译”模板。

初审通过后，来源 issue 会被关闭并锁定。此后不要编辑 issue 正文；如果 PR 需要改内容，请在 PR 下评论 `/update` 命令。

## 更新已有文件

适用于库里已经合并过该 Steam app ID，但游戏更新或翻译修正后需要替换文件。

1. 打开 issue 模板“更新已有 Steam 成就翻译”。
2. 填写同一个 Steam app ID。自动化只检查 `index.json` 中已合并的条目，正在打开的 PR 不算已收录。
3. 在“更新内容摘要”中说明变化：新增成就、删除成就、修改翻译、补充语言字段或修正错误。
4. 上传新版 `UserGameStatsSchema_<app_id>.zip`。
5. 自动化会先和库里的当前文件做字节级比较；如果完全相同，会拒绝创建 PR。
6. 如果文件不同，PR 描述会列出新增、删除和修改的成就 ID，方便维护者审核。

## PR 中的 `/update` 命令

PR 创建后，PR 标题和描述由机器人维护。需要修改时，在 PR 评论区使用下面的命令；机器人会更新文件、索引和 PR 描述。处理成功后，机器人会发表评论确认，并用固定格式列出每个更新项的原内容和更新后内容。

| 命令 | 作用 |
| --- | --- |
| `/update doc` + 附件 | 替换当前 PR 中的 `UserGameStatsSchema_<app_id>.bin` 文件；同一条评论必须附加 `UserGameStatsSchema_<app_id>.zip` |
| `/update` + 附件 | 等同于 `/update doc`，用于只上传替换文件的情况 |
| `/update id <Steam app ID>` | 修改 Steam app ID，并在普通投稿/更新 PR 中同步重命名文件路径 |
| `/update name <游戏名>` | 修改游戏名；如果 Steam 显示名不是中文，可以写“Steam 原名 中文译名” |
| `/update store <Steam 商店地址>` | 修改 Steam 商店地址，地址中的 app ID 必须和当前 app ID 一致 |
| `/update languages <语言代码>` | 修改语言代码列表，多个代码可用逗号或空格分隔 |
| `/update summary <摘要>` | 修改更新 PR 中的“更新内容摘要” |
| `/update reason <说明>` | 修改报告过期 PR 的过期说明 |
| `/update reference <来源>` | 修改报告过期 PR 的参考来源 |

当维护者请求修改时，PR 会自动加上 `等待更新` label。之后有人在 PR 下评论，机器人会自动移除这个 label；如果评论是 `/update` 命令，机器人还会尝试同步更新 PR。

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
| ZIP 安全 | ZIP 内不能有目录穿越、绝对路径或多个文件 |
| 文件大小 | 上传文件和 schema 文件都有 32 MiB 上限 |
| 二进制解析 | schema 必须能被 Binary KeyValues 解析器读取并字节级 roundtrip |
| 成就结构 | 必须能找到成就名称、描述和非空唯一的 API name |
| 语言覆盖 | 勾选的每个语言字段都必须为每个成就提供名称和描述 |
| 更新差异 | 更新 issue 必须和库中现有文件不同，并在 PR 中展示新增、删除、修改 |

## 版权与来源

请只提交你有权分享的翻译成果。原始游戏内容、成就文本、Steam schema 内容及相关文件仍归对应权利方所有；你提交的自有翻译部分会按 [LICENSE.md](LICENSE.md) 中的贡献许可供社区使用。
