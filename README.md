# Steam 成就翻译库

简体中文 | [English](README_EN.md)

本项目是 **Steam 成就翻译数据仓库**，用于集中收录社区提交的 `UserGameStatsSchema_<app_id>.bin` 翻译文件，并维护可搜索索引、投稿模板和自动化初审流程。

> - 使用 AI skill 自动进行本地化操作请前往 [GaBoron/steam-achievement-localizer-skill](https://github.com/GaBoron/steam-achievement-localizer-skill) **(推荐)**  
> - 使用本地软件手动进行本地化操作请前往 [PanVena/SteamAchievementLocalizer](https://github.com/PanVena/SteamAchievementLocalizer)  
> 本仓库只保存翻译数据和数据投稿流程。

## 快速入口

| 你想做什么 | 入口 |
| --- | --- |
| 查找翻译 | 打开 [翻译库索引](INDEX.md)，可搜索 Steam app ID、游戏名、贡献者或语言代码 |
| 提交新游戏 | 使用 issue 模板 [“提交 Steam 成就翻译”](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_zh.yml) |
| 更新已收录文件 | 使用 issue 模板 [“更新已有 Steam 成就翻译”](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_zh.yml) |
| 报告文件过期 | 使用 issue 模板 [“报告成就文件过期”](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_zh.yml) |
| 查看填写规范 | 阅读 [贡献指南](CONTRIBUTING.md) |
| 新功能请愿 | 使用 issue 模板 [“新功能请愿”](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=feature_petition_zh.yml) |

## 使用流程

### 1. 找到游戏

优先使用 Steam app ID。打开游戏的 Steam 商店页，网址里 `/app/` 后面的数字就是 app ID，例如 `https://store.steampowered.com/app/250900/...` 对应 `250900`。

打开 [翻译库索引](INDEX.md) 后，用浏览器或 GitHub 页面搜索：

| 搜索内容 | 适合场景 |
| --- | --- |
| Steam app ID | 最准确，推荐优先使用 |
| 游戏名 | 不确定 app ID 时使用；部分条目会同时写原名和中文名 |
| 语言代码 | 例如 `schinese`、`tchinese`、`japanese` |
| 贡献者 | 想查某位贡献者提交过哪些文件 |

找到条目后，先看“状态”和“最近更新”。如果状态是“可能过期”，说明已有用户报告 Steam schema 可能变化；除非你明确知道仍然适用，否则建议等待更新 PR 合并后再下载。

同一个游戏可能提供多个版本。此时“文件”列会显示多个链接及中文版本说明；请选择与你的游戏分支或用途匹配的文件，不能只凭文件名区分。

### 2. 下载文件

优先在索引表格的“文件”列点击 `UserGameStatsSchema_<app_id>.bin`。索引中的主下载入口使用 jsDelivr，并指向当前 `main` 分支的对应文件。

下载后确认三件事：

| 检查项 | 说明 |
| --- | --- |
| 文件名 | 应保持 `UserGameStatsSchema_<app_id>.bin`，不要保存成 `.txt`、`.html` 或带额外后缀 |
| app ID | 文件名里的数字必须和你要替换的游戏一致 |
| 文件大小 | 应和索引“文件”列标注的大小一致；大小明显不对时不要替换本地文件 |

如果索引里的下载链接无法使用，可以进入仓库的 `files/<app_id>/` 目录，根据游戏 app ID 找到对应 `UserGameStatsSchema_<app_id>.bin` 并自行下载。

### 3. 找到 Steam 本地文件

Steam 本地 schema 通常在 Steam 安装目录下：

```text
<Steam 安装目录>/appcache/stats/UserGameStatsSchema_<app_id>.bin
```

Windows 常见位置：

```text
C:/Program Files (x86)/Steam/appcache/stats/UserGameStatsSchema_<app_id>.bin
C:/Program Files/Steam/appcache/stats/UserGameStatsSchema_<app_id>.bin
```

注意：这个文件通常不在游戏安装目录，也不在 `steamapps/common/<游戏名>` 下面。自定义 Steam 游戏库位置一般不会改变 `appcache/stats` 的位置。

如果找不到文件：

1. 启动 Steam。
2. 启动对应游戏并进入一次成就或主菜单流程，让 Steam 生成/刷新 schema 缓存。
3. 关闭游戏和 Steam。
4. 在 Steam 安装目录下搜索 `UserGameStatsSchema_<app_id>.bin`。

也可以使用 [steam-achievement-localizer-skill](https://github.com/GaBoron/steam-achievement-localizer-skill) 里的工具定位：

```bash
python scripts/steam_bkv_tool.py find-schema --game-id <app_id>
```

### 4. 替换并使用

替换前请先关闭 Steam 和游戏，并备份原文件，例如复制成：

```text
UserGameStatsSchema_<app_id>.bin.bak
```

然后把从本仓库下载的 `UserGameStatsSchema_<app_id>.bin` 放到本地 `appcache/stats` 目录，覆盖同名文件。确认文件名完全一致后重新启动 Steam 和游戏。

如果游戏更新、Steam 刷新缓存或成就数量变化，Steam 可能重新生成该文件。遇到翻译失效、成就缺失或索引状态过旧时，请使用“报告成就文件过期”模板；如果你已经有新版文件，请使用“更新已有 Steam 成就翻译”模板。

## 许可证与权利

本仓库采用混合权利说明，详见 [LICENSE.md](LICENSE.md)。简要来说：workflow 脚本按 MIT 许可提供；贡献者提交的自有翻译部分按 CC BY 4.0 授权给社区使用；原始游戏内容、成就文本、Steam schema 内容及相关文件仍归对应权利方所有。
