# 贡献指南

感谢你为 Steam 成就翻译库投稿。本仓库面向中文用户，中文说明和中文 issue 模板是默认入口；英文内容仅作为辅助。

## 投稿前检查

1. 在 `README.md` 和 `index.json` 中搜索 Steam app ID，确认没有重复投稿。
2. 确认文件名为 `UserGameStatsSchema_<app_id>.bin`。
3. 将该文件压缩为只包含一个文件的 `UserGameStatsSchema_<app_id>.zip`。
4. 确认上传文件包含你在 issue 中勾选或填写的 Steam 语言字段，例如 `schinese`、`tchinese`、`english`。

## 投稿流程

1. 新建 issue，选择“提交 Steam 成就翻译（中文）”。
2. 填写游戏名、Steam app ID、Steam 商店地址、语言代码，并上传 ZIP。
3. GitHub Actions 会运行 `.github/workflows/translation-contribution.yml`。
4. 初审通过后，机器人会在投稿分支中加入 `files/<app_id>/UserGameStatsSchema_<app_id>.bin`，并更新 `index.json`、`README.md`、`README_EN.md`。
5. 维护者审核后合并 PR。

## 路径约定

独立仓库使用扁平化路径：

- 成就文件：`files/<app_id>/UserGameStatsSchema_<app_id>.bin`
- 机器索引：`index.json`
- 中文索引：`README.md`
- 英文辅助索引：`README_EN.md`

请不要再使用原 skill 仓库中的 `achievement-library/` 前缀。

## 不属于本仓库的内容

不要向本仓库提交 `SKILL.md`、`VERSION`、`scripts/steam_bkv_tool.py`、Codex skill 安装说明、skill 打包脚本或 release workflow。这些内容应继续留在原 skill 仓库或由原项目引用本仓库数据。
