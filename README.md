# Steam 成就翻译库

简体中文 | [English](README_EN.md)

本仓库是从 `steam-achievement-localizer-skill` 拆分出来的独立 **Steam 成就翻译数据仓库**。这里不再维护 Codex skill 本体、安装包或运行时脚本，只维护社区投稿的 `UserGameStatsSchema_<app_id>.bin` 翻译文件、索引和投稿自动化。

## 快速入口

- 查找翻译：查看 [翻译库索引](#游戏列表)，可搜索 Steam app ID、游戏名、贡献者或语言代码。
- 投稿翻译：使用中文 issue 模板“提交 Steam 成就翻译”，上传 `UserGameStatsSchema_<app_id>.zip`。
- 贡献规范：优先阅读 [中文贡献指南](CONTRIBUTING.md)。英文版见 [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md)。

## 仓库结构

```text
.
├── files/                         # 社区提交的成就 schema 文件
├── index.json                     # 机器可读索引
├── README.md                      # 中文默认索引与项目说明
├── README_EN.md                   # 英文辅助说明
├── CONTRIBUTING.md                # 中文贡献指南
├── CONTRIBUTING_EN.md             # 英文辅助贡献指南
├── workflow-scripts/              # GitHub Actions 投稿维护脚本
└── .github/
    ├── ISSUE_TEMPLATE/            # 投稿 issue 模板（中文优先）
    └── workflows/                 # 翻译投稿自动化 workflow
```

> 路径已从原仓库的 `achievement-library/files/`、`achievement-library/index.json` 调整为独立仓库根目录下的 `files/`、`index.json`，避免出现 `achievement-library/achievement-library` 嵌套。

## 使用说明

下载所需游戏的 `UserGameStatsSchema_<app_id>.bin` 后，请使用你信任的本地工具应用到 Steam 本地成就 schema。替换本地 Steam 文件前请自行备份。

## 游戏列表

暂无已收录游戏。迁移时保留了独立仓库结构和索引格式；后续合并投稿后，自动化脚本会更新本节和 `index.json`。

## 迁移说明

本仓库只接收翻译库相关内容：索引、社区投稿数据目录、投稿模板、贡献指南以及 GitHub Actions 维护脚本。未迁移 `SKILL.md`、`VERSION`、`scripts/steam_bkv_tool.py`、skill 安装/打包说明和相关 workflow。

## 许可证

MIT。原始游戏内容、成就文本、Steam schema 内容及相关文件版权归对应游戏开发商、发行商及其他权利方所有；投稿翻译文本版权归对应贡献者所有，投稿即表示允许本仓库展示、索引并分发其提交的成就文件用于社区本地化。
