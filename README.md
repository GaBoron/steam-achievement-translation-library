# Steam 成就翻译库

简体中文 | [English](README_EN.md)

本项目是 **Steam 成就翻译数据仓库**，用于集中收录社区提交的 `UserGameStatsSchema_<app_id>.bin` 翻译文件，并维护可搜索索引、投稿模板和自动化初审流程。

> 翻译脚本、Codex skill、安装和本地应用流程在 [GaBoron/steam-achievement-localizer-skill](https://github.com/GaBoron/steam-achievement-localizer-skill) 维护；本仓库只保存翻译数据和数据投稿流程。

## 快速入口

| 你想做什么 | 入口 |
| --- | --- |
| 查找翻译 | 打开 [翻译库索引](INDEX.md)，可搜索 Steam app ID、游戏名、贡献者或语言代码 |
| 提交新游戏 | 使用 issue 模板“提交 Steam 成就翻译” |
| 更新已收录文件 | 使用 issue 模板“更新已有 Steam 成就翻译” |
| 报告文件过期 | 使用 issue 模板“报告成就文件过期” |
| 查看填写规范 | 阅读 [贡献指南](CONTRIBUTING.md) |

## 使用提示

下载文件前请查看索引里的“状态”和“最近更新”。如果某个游戏被标记为“可能过期”，说明已有用户报告 Steam schema 可能变化，建议等待更新 PR 合并后再使用。

下载 `UserGameStatsSchema_<app_id>.bin` 后，请使用你信任的本地工具应用到 Steam 本地成就 schema。替换本地 Steam 文件前请自行备份。

## 许可证与权利

本仓库采用混合权利说明，详见 [LICENSE.md](LICENSE.md)。简要来说：workflow 脚本按 MIT 许可提供；贡献者提交的自有翻译部分按 CC BY 4.0 授权给社区使用；原始游戏内容、成就文本、Steam schema 内容及相关文件仍归对应权利方所有。
