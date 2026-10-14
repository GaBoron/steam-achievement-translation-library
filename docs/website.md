# 网站维护

网站位于 [GitHub Pages](https://gaboron.github.io/steam-achievement-translation-library/)，源码在 `web/`。前端使用原生 JavaScript 模块，不需要 npm、框架或后端。资源使用相对路径，游戏详情通过 `#/game/<app_id>` 分享；指定译本时追加 `/<variant_id>`，界面语言使用 `?lang=zh` 或 `?lang=en`。

`web/tokens.css` 集中定义 MD3 色彩角色、字号、形状、动效和状态层，`styles.css` 将它们应用于控件与布局。使用克制的青蓝强调色与冷灰 Surface，内容最大宽度为 1120px；宽屏搜索与筛选并排，列表采用连续行，详情以下载为主区、更新与贡献者为辅助栏。窄屏将筛选放到搜索下方，详情按下载、辅助信息、预览的顺序展示。目录适配、列表、详情和预览分别维护在独立模块中；调整外观时优先修改对应 token，保持浅深主题一致。参照 [Material 色彩角色](https://material-web.dev/theming/color/)与 [Typography](https://material-web.dev/theming/typography/)。

`select.js` 统一选择菜单，`pagination.js` 供列表与预览共用，`languages.js` 将非标准语言代码归入“其他”。顶栏、搜索筛选和底栏常驻，内容独立滚动；`motion.js` 统一内容过渡，并遵循系统的减弱动态效果设置。

`index-v2.json` 是唯一游戏目录来源。`workflow-scripts/build_website.py` 调用独立的 `website_build.py`，校验本地资源引用、Catalog 结构及各版本 BIN 的大小、SHA-256、语言和成就数，并将 JSON 与 BIN 派生内容逐字节比较。Windows checkout 产生的 JSON 换行会在构建输出中恢复为标准 LF，源文件不变。构建只复制网页资源、原始 Catalog 和其引用的 V2 BIN/JSON，不修改投稿、V1 数据或生成源文件。`site-meta.json` 记录构建提交，用于固定 GitHub 源文件链接。

## 本地预览

在仓库根目录运行：

```bash
python workflow-scripts/build_website.py
python -m http.server 8000 --directory _site
```

打开 `http://localhost:8000/`。JavaScript 模块需要 HTTP，不能直接打开 HTML 文件。`_site/` 已被 Git 忽略；构建拒绝非空输出目录，不会清空或删除文件。再次构建前将旧目录移至系统回收站，或用 `--output` 指定新的空目录，并相应调整服务器的 `--directory`。

## 部署

首次启用时，在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**，然后在 Actions 中手动运行 **Translation library website**。`github-pages` 环境如有部署分支限制，应允许 `main`。部署地址保持仓库子路径，无需新仓库、发布分支或自定义域名。[GitHub Pages 配置说明](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

`.github/workflows/pages.yml` 在 `main` 推送、手动运行，以及 **Translation library automation** 或 **Translation finalizer watchdog** 成功完成后部署。后两者通过 `workflow_run` 补足机器人以 `GITHUB_TOKEN` 推送时不会触发普通 `push` 工作流的限制。[GitHub Actions 触发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)

构建始终检出最新 `main`，不执行触发工作流的 PR 代码，也不读取其构件。只接受本仓库成功运行；新构建取消旧构建，部署按顺序执行，失败构建不会覆盖已发布网站。Pages 构件只存于 Actions，不提交到主分支。CI 使用 Node 24 检查 JavaScript 语法，不安装 npm 依赖。翻译 PR 使用现有待入库校验；其他 PR 还会执行完整网站构建。

## English

The [GitHub Pages website](https://gaboron.github.io/steam-achievement-translation-library/) is maintained in `web/`. It uses native JavaScript modules, without npm, a framework, or a backend. Assets use relative paths. Share a game through `#/game/<app_id>`, append `/<variant_id>` for a specific variant, and select the interface language with `?lang=zh` or `?lang=en`.

`web/tokens.css` defines the MD3 color, type, shape, motion, and state roles; `styles.css` applies them to controls and layout. A restrained blue accent and cool neutral surfaces frame a maximum content width of 1120px. Wide screens place search and filters together, use continuous list rows, and give downloads the main detail column with updates and contributors alongside. Narrow screens place filters below search and arrange details as downloads, supporting information, then preview. Catalog adaptation, lists, details, and previews live in separate modules. Change the relevant tokens first when adjusting appearance, keeping light and dark themes aligned. See [Material color roles](https://material-web.dev/theming/color/) and [Typography](https://material-web.dev/theming/typography/).

`select.js` provides consistent selection menus, `pagination.js` is shared by lists and previews, and `languages.js` groups nonstandard language codes under “Other.” The header, search, filters, and footer stay visible while content scrolls independently. `motion.js` coordinates content transitions and respects the system's reduced-motion preference.

`index-v2.json` is the only game catalog source. `workflow-scripts/build_website.py` calls the separate `website_build.py` module to validate local asset references, Catalog structure, and each BIN's size, SHA-256, languages, and achievement count. JSON is compared byte for byte against its BIN-derived content. JSON line endings expanded by Windows checkout are restored to canonical LF in the output, leaving source files unchanged. The build copies website assets, the original Catalog, and its referenced V2 BIN/JSON files, without modifying submissions, V1 data, or generated source files. `site-meta.json` records the build commit for pinned GitHub source links.

Run the commands above from the repository root, then open `http://localhost:8000/`. JavaScript modules require HTTP; opening the HTML file directly is unsupported. Git ignores `_site/`. Builds refuse nonempty output directories and never clear or delete files. Recycle the old directory before rebuilding, or select a fresh empty directory with `--output` and adjust the server's `--directory`.

For initial deployment, select **GitHub Actions** under **Settings → Pages → Build and deployment → Source**, then manually run **Translation library website** in Actions. If the `github-pages` environment restricts deployment branches, allow `main`. Keep the repository subpath; no separate repository, publishing branch, or custom domain is required. See [GitHub Pages configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

`.github/workflows/pages.yml` deploys on pushes to `main`, manual runs, and successful completion of **Translation library automation** or **Translation finalizer watchdog**. The `workflow_run` triggers cover Catalog publication when a `GITHUB_TOKEN` push does not trigger a normal `push` workflow. See [GitHub Actions trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Builds always check out current `main`, without executing the triggering PR's code or consuming its artifacts. Only successful runs from this repository qualify. New builds cancel older builds, deployments run in sequence, and failed builds leave the published site intact. Pages artifacts stay in Actions rather than main. CI checks JavaScript syntax with Node 24, without installing npm dependencies. Translation PRs retain their pending-submission validation; other PRs also run the full website build.
