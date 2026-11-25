# Steam 成就翻译库

简体中文 | [English](README_EN.md)

社区维护的 Steam 成就译本库，提供游戏检索、多语言文本预览和文件下载。你可以选择已有译本，也可以请愿或贡献翻译。

<p align="center">
  <a href="https://gaboron.github.io/steam-achievement-translation-library/?lang=zh"><img alt="浏览翻译库" src="https://img.shields.io/badge/%E6%B5%8F%E8%A7%88%E7%BF%BB%E8%AF%91%E5%BA%93-%E6%89%93%E5%BC%80%E7%BD%91%E7%AB%99-1f6feb?style=for-the-badge&amp;logo=steam&amp;logoColor=white"></a>
  <a href="https://github.com/GaBoron/SATLI"><img alt="查看翻译管理器" src="https://img.shields.io/badge/%E7%BF%BB%E8%AF%91%E7%AE%A1%E7%90%86%E5%99%A8-Windows-0078D4?style=for-the-badge&amp;logo=windows11&amp;logoColor=white"></a>
  <a href="https://github.com/GaBoron/steam-achievement-localizer-skill"><img alt="使用翻译 Skill 制作翻译" src="https://img.shields.io/badge/Translation%20Skill-%E5%88%B6%E4%BD%9C%E7%BF%BB%E8%AF%91-412991?style=for-the-badge&amp;logo=openai&amp;logoColor=white"></a>
  <a href="docs/CONTRIBUTING.md"><img alt="阅读投稿指南" src="https://img.shields.io/badge/%E8%B4%A1%E7%8C%AE%E7%BF%BB%E8%AF%91-%E6%8A%95%E7%A8%BF%E6%8C%87%E5%8D%97-2DA44E?style=for-the-badge&amp;logo=github&amp;logoColor=white"></a>
</p>

## 🚀 查找与使用译本

1. 在 [翻译库网站](https://gaboron.github.io/steam-achievement-translation-library/?lang=zh) 搜索游戏名、Steam App ID 或贡献者，也可以按状态和语言筛选。
2. 打开游戏详情，按版本说明选择适用的译本，预览目标语言，并检查“可能过期”或“可能不生效”状态。
3. 按文件类型选择兼容客户端。网站的下载项会标出已适配客户端及其最低版本。

| 你的需求 | 使用工具 |
| --- | --- |
| 在 Steam 界面内下载和显示 JSON 译文 | [SATLI lite](https://github.com/GaBoron/SATLI-lite)，需要 Millennium 3.5.0+，可独立于 SATLI 本体使用 |
| 在 Windows 管理本机 BIN、编辑、安装、备份恢复或导出投稿 ZIP | [Steam 成就翻译管理器（SATLI）](https://github.com/GaBoron/SATLI) |

独立格式 2 JSON 需要 SATLI lite 0.2.0+。JSON 只提供显示文本，不能当作 BIN 安装，修改扩展名也不能转换格式。使用 BIN 前确认 App ID，并通过管理器备份原文件；实际效果取决于游戏、Steam 和客户端支持情况。

## 🤝 请愿、投稿与反馈

- **没有所需译本：** 发起 [翻译请愿](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_zh.yml)，填写 App ID、游戏名和目标 Steam 语言代码；原始 schema ZIP 可选。公开数据可获取时，机器人提供待翻译 JSON 草稿。
- **已有译本可分享或更新：** 按 [贡献指南](docs/CONTRIBUTING.md) 准备独立 JSON 或 BIN ZIP，并选择新投稿或更新入口。通常不需要手工 fork 仓库。
- **译本可能过期或不生效：** 提交 [文件错误报告](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_zh.yml)；已有修正版时直接提交更新。

制作译本可以使用 SATLI 或 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill)；后者提供研究、翻译和验证流程。

偏好独立的本地可视化编辑器时，也可以使用 [PanVena/SteamAchievementLocalizer](https://github.com/PanVena/SteamAchievementLocalizer)。

## 🧩 接入与开发

公开接口由 `index-v2.json` 和它引用的 BIN/JSON 文件组成，可匿名读取。

- [数据接入指南](docs/integration.md)：Catalog 字段、固定快照、下载校验和客户端示例。
- [翻译 JSON 格式](docs/translation-json.md)：格式约定、独立投稿和草稿生成。
- [开发与维护](docs/development.md)：代码职责、投稿自动化和验证入口。
- [网站维护](docs/website.md)：本地预览、前端模块和 Pages 部署。

## 📈 收录统计

![收录游戏数量趋势与贡献者贡献量排行](docs/statistics/library-statistics.svg)

## 💬 联系支持

需要帮助时，请发送邮件至 [SATLI.support@proton.me](mailto:SATLI.support@proton.me)。

## ⚖️ 许可证与权利

详见 [LICENSE.md](LICENSE.md)。网站与工作流脚本采用 MIT；贡献者自有翻译部分采用 CC BY 4.0；原始游戏内容、成就文本和 Steam schema 仍归对应权利方所有。
