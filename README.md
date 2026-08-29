# Steam 成就翻译库

简体中文 | [English](README_EN.md)

社区维护的 Steam 成就翻译数据仓库，收录 `UserGameStatsSchema_<app_id>.bin` 文件并生成可搜索索引。

## 🚀 从这里开始

<p align="center">
  <a href="INDEX.md"><img alt="浏览翻译库" src="https://img.shields.io/badge/%E6%B5%8F%E8%A7%88%E7%BF%BB%E8%AF%91%E5%BA%93-%E6%89%93%E5%BC%80%E7%B4%A2%E5%BC%95-1f6feb?style=for-the-badge&amp;logo=steam&amp;logoColor=white"></a>
  <a href="https://github.com/GaBoron/steam-achievement-translation-installer"><img alt="下载翻译管理器" src="https://img.shields.io/badge/%E7%BF%BB%E8%AF%91%E7%AE%A1%E7%90%86%E5%99%A8-Windows-0078D4?style=for-the-badge&amp;logo=windows11&amp;logoColor=white"></a>
  <a href="https://github.com/GaBoron/steam-achievement-localizer-skill"><img alt="使用 Codex Skill 制作翻译" src="https://img.shields.io/badge/Codex%20Skill-%E5%88%B6%E4%BD%9C%E7%BF%BB%E8%AF%91-412991?style=for-the-badge&amp;logo=openai&amp;logoColor=white"></a>
  <a href="CONTRIBUTING.md"><img alt="阅读投稿指南" src="https://img.shields.io/badge/%E8%B4%A1%E7%8C%AE%E7%BF%BB%E8%AF%91-%E6%8A%95%E7%A8%BF%E6%8C%87%E5%8D%97-2DA44E?style=for-the-badge&amp;logo=github&amp;logoColor=white"></a>
</p>

> [!TIP]
> 普通用户建议直接使用 **Steam 成就翻译管理器**：它可以查找、安装、编辑、备份和恢复译本。本仓库主要面向数据浏览与投稿。

## 📚 翻译库操作

- **找译本：** 在 [INDEX.md](INDEX.md) 中搜索 Steam app ID；这是最准确的检索方式。多版本游戏请按版本说明选择文件，并留意“可能过期”或“可能不生效”状态。
- **没有译本：** 提交 [翻译请愿](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_zh.yml)，并附上 Steam 生成的原始 schema ZIP。
- **贡献译本：** 按照 [贡献指南](CONTRIBUTING.md) 提交 [新游戏](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_zh.yml)或 [更新已有文件](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_zh.yml)。
- **发现问题：** 使用 [文件错误报告](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_zh.yml)标记过期或不生效的译本；有新版文件时请直接提交更新。

直接下载文件时，请确认文件名和 app ID 一致。安装、备份与恢复建议交给 [Steam 成就翻译管理器](https://github.com/GaBoron/steam-achievement-translation-installer)，避免手工覆盖错误文件。

## 🧭 V2 迁移状态

仓库端 Catalog V2 已上线，目前处于 V1/V2 并行迁移阶段：

- 每个游戏目录中的 `files/<app_id>/manifest.json` 是完整元数据的权威来源；各版本文件使用 `files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.bin` 固定路径。
- `index-v2.json` 是面向客户端的精简 V2 运行时索引。
- V1 `index.json` 和 `files/<app_id>/UserGameStatsSchema_<app_id>.bin` 默认文件旧路径继续生成，供仅支持 V1 的 SATLI 版本使用。
- 迁移期间，新投稿和更新只需提交一次；自动化会同时生成 V2 权威数据与 V1 兼容数据。

> [!IMPORTANT]
> **迁移截止时间为 2026 年 12 月 31 日 23:59（UTC+8）。** 自 2027 年 1 月 1 日起，本仓库不再保证继续提供 V1 `index.json` 和默认文件旧路径；仍使用 V1 的客户端须在截止前升级。客户端适配进度见 [SATLI #14](https://github.com/GaBoron/SATLI/issues/14)。

## 🔄 项目协作

| 项目 | 职责 |
| --- | --- |
| **本仓库** | 保存社区译本、索引和投稿记录 |
| [Steam 成就翻译管理器](https://github.com/GaBoron/steam-achievement-translation-installer) | 使用本仓库数据完成扫描、预览、安装、编辑、备份与恢复，并可导出投稿 ZIP |
| [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill) | 查询本仓库参考译本，通过 Codex 研究和制作翻译，输出可由管理器导入或向本仓库投稿的 BIN/ZIP |

偏好独立的本地可视化编辑器时，也可以使用 [PanVena/SteamAchievementLocalizer](https://github.com/PanVena/SteamAchievementLocalizer)。

## 📈 收录统计

![收录游戏数量趋势与贡献者贡献量排行](docs/statistics/library-statistics.svg)

## 💬 联系支持

需要帮助时，请发送邮件至 [SATLI.support@proton.me](mailto:SATLI.support@proton.me)。

## ⚖️ 许可证与权利

详见 [LICENSE.md](LICENSE.md)。工作流脚本采用 MIT；贡献者自有翻译部分采用 CC BY 4.0；原始游戏内容、成就文本和 Steam schema 仍归对应权利方所有。
