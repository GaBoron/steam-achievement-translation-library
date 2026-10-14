# 网站维护

网站位于 [GitHub Pages](https://gaboron.github.io/steam-achievement-translation-library/)，源码在 `web/`。前端使用原生 JavaScript 模块，不需要 npm、框架或后端。资源使用相对路径，游戏详情通过 `#/game/<app_id>` 分享；指定译本时追加 `/<variant_id>`，界面语言使用 `?lang=zh` 或 `?lang=en`。

`web/tokens.css` 集中定义色彩角色、字号、形状、动效和状态层，`styles.css` 维护共用控件与应用外壳，`catalog.css`、`detail.css` 分别负责检索和详情布局。页面按 Modrinth 的检索页与项目页组织，使用灰色层级、绿色操作按钮、方形封面与 16px 圆角资源卡片。外框最大宽度为 1280px，左右留白 24px，检索侧栏宽度为 300px，栏间距为 12px。Inter 3.19 可变字体自托管于 `web/fonts/`，来源为 [Inter 官方发行版](https://github.com/rsms/inter/tree/v3.19)，同目录保留 SIL OFL 许可证。目录适配、列表、详情和预览分别维护在独立模块中；调整外观时保持浅深主题一致。交互沿用可见焦点、状态层与减弱动态效果支持。

`filter-group.js` 提供状态与语言的单选筛选，`select.js` 统一排序、主题、界面语言与预览选择菜单；`pagination.js` 供列表与预览共用，`languages.js` 将非标准语言代码归入“其他”。检索页左侧显示筛选，右侧显示搜索与资源条目；窄屏筛选折叠为弹出面板。详情页左侧展示资料，右侧通过 `detail-tabs.js` 切换下载与预览；`translation-files.js` 负责译本行、下载链接与展开的校验信息。窄屏将资料放在主内容之后。页面整体滚动，检索结果上下均提供页码；Ctrl K 在详情页返回检索并聚焦搜索。`motion.js` 统一内容过渡。

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

`web/tokens.css` defines color, type, shape, motion, and state roles. `styles.css` maintains shared controls and the application shell; `catalog.css` and `detail.css` own discovery and project layouts. The pages follow Modrinth's discovery and project layouts with layered gray surfaces, green actions, square covers, and resource cards with 16px corners. The outer frame is limited to 1280px with 24px side padding, a 300px discovery sidebar, and a 12px column gap. Inter 3.19 is self-hosted in `web/fonts/`, sourced from the [official Inter release](https://github.com/rsms/inter/tree/v3.19) with its SIL OFL license alongside the font. Catalog adaptation, lists, details, and previews live in separate modules. Keep light and dark themes aligned when changing appearance. Interactions retain visible focus, state layers, and reduced-motion support.

`filter-group.js` supplies single-choice status and language facets. `select.js` provides consistent menus for sorting, themes, interface languages, and previews. `pagination.js` is shared by lists and previews, and `languages.js` groups nonstandard language codes under “Other.” Discovery places filters on the left and search results on the right; narrow screens collapse filters into a floating panel. Project details place supporting information on the left and use `detail-tabs.js` to switch downloads and previews on the right. `translation-files.js` owns variant rows, download links, and expandable integrity details. Narrow screens put supporting information after the main content. The document scrolls as a whole, with pagination above and below search results. Ctrl K returns from a project to discovery and focuses search. `motion.js` coordinates content transitions.

`index-v2.json` is the only game catalog source. `workflow-scripts/build_website.py` calls the separate `website_build.py` module to validate local asset references, Catalog structure, and each BIN's size, SHA-256, languages, and achievement count. JSON is compared byte for byte against its BIN-derived content. JSON line endings expanded by Windows checkout are restored to canonical LF in the output, leaving source files unchanged. The build copies website assets, the original Catalog, and its referenced V2 BIN/JSON files, without modifying submissions, V1 data, or generated source files. `site-meta.json` records the build commit for pinned GitHub source links.

Run the commands above from the repository root, then open `http://localhost:8000/`. JavaScript modules require HTTP; opening the HTML file directly is unsupported. Git ignores `_site/`. Builds refuse nonempty output directories and never clear or delete files. Recycle the old directory before rebuilding, or select a fresh empty directory with `--output` and adjust the server's `--directory`.

For initial deployment, select **GitHub Actions** under **Settings → Pages → Build and deployment → Source**, then manually run **Translation library website** in Actions. If the `github-pages` environment restricts deployment branches, allow `main`. Keep the repository subpath; no separate repository, publishing branch, or custom domain is required. See [GitHub Pages configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

`.github/workflows/pages.yml` deploys on pushes to `main`, manual runs, and successful completion of **Translation library automation** or **Translation finalizer watchdog**. The `workflow_run` triggers cover Catalog publication when a `GITHUB_TOKEN` push does not trigger a normal `push` workflow. See [GitHub Actions trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Builds always check out current `main`, without executing the triggering PR's code or consuming its artifacts. Only successful runs from this repository qualify. New builds cancel older builds, deployments run in sequence, and failed builds leave the published site intact. Pages artifacts stay in Actions rather than main. CI checks JavaScript syntax with Node 24, without installing npm dependencies. Translation PRs retain their pending-submission validation; other PRs also run the full website build.
