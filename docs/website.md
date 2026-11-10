# 网站维护

[返回首页](../README.md) · [English](#english)

[翻译库网站](https://gaboron.github.io/steam-achievement-translation-library/) 的源码位于 `web/`，使用原生 JavaScript 模块，无需 npm、框架或后端。网站消费已发布 Catalog 和译本；投稿处理与 Catalog 发布见 [开发与维护](development.md)。

## 本地构建与预览

在仓库根目录运行：

```bash
python workflow-scripts/build_website.py
python -m http.server 8000 --directory _site
```

打开 `http://localhost:8000/`。模块需要通过 HTTP 加载，不能直接打开 HTML 文件。构建输出默认是已被 Git 忽略的 `_site/`，不修改源文件。

构建要求输出目录不存在或为空，不会清空已有文件。再次构建时，将旧输出移至系统回收站，或选择新的空目录：

```bash
python workflow-scripts/build_website.py --output _site/preview
python -m http.server 8000 --directory _site/preview
```

仓库内的自定义输出必须位于 `_site/` 下，也可使用仓库外的新目录；服务器的 `--directory` 与构建路径保持一致。`--refresh-covers` 会联网刷新输出中的 Steam 封面地址，失败时保留快照；默认构建无需联网。

## 前端职责与约束

| 模块 | 职责 |
| --- | --- |
| `app.js`、`preferences.js`、`i18n.js` | 路由与页面组合、界面偏好、中英文文案 |
| `catalog.js`、`translation-integrity.js` | Catalog 适配、检索、预览读取与格式对应的完整性校验 |
| `list.js`、`detail.js`、`detail-tabs.js`、`preview.js` | 检索列表、游戏详情、下载与预览标签页、语言文本预览 |
| `translation-files.js`、`compatibility.js` | 文件下载项、校验信息、已发布客户端的格式兼容性 |
| `controls.js`、`filter-group.js`、`select.js`、`pagination.js` | 筛选、选择菜单与共用分页 |
| `tokens.css`、`styles.css`、`catalog.css`、`detail.css` | 设计变量、共用控件与页面布局 |
| `game-covers.js`、`steam-covers.json` | 列表和详情共用的封面加载与地址快照 |

资源使用相对路径，保证仓库子路径部署正常。分享链接采用 `#/game/<app_id>`，指定版本时追加 `/<variant_id>`；界面语言使用 `?lang=zh` 或 `?lang=en`。

修改界面时保留浅深主题、窄屏布局、可见焦点和减弱动态效果支持。可选菜单、分页和过渡复用现有模块；尺寸与样式以 CSS 为准，避免在文档中维护另一份样式规格。Inter 字体自托管，字体来源与完整许可见 [LICENSE.md](../LICENSE.md#bundled-fonts)。

`compatibility.js` 是下载项客户端兼容性说明的来源。它按文件类型显示真实最低发布版本，未适配客户端省略，没有适配客户端时显示“暂无适配”。只在兼容客户端正式发布后更新登记；格式定义与旧客户端限制见 [接入指南](integration.md)。

## 构建的数据边界

`build_website.py` 调用 `website_build.py`，先检查资源引用和 Catalog，再打包网站及其引用的译本：

- BIN 校验大小、SHA-256、语言与成就数；格式 1 JSON 与 BIN 派生内容逐字节比较。
- 独立格式 2 JSON 按 Catalog 中的 JSON 大小、哈希、语言和成就数校验，不要求不存在的 BIN。
- Windows checkout 扩展的 JSON 换行在输出中恢复为标准 LF，源文件不变。
- 输出仅含网站资源、Catalog、引用的 BIN/JSON 和构建元数据。`site-meta.json` 记录构建提交，用于固定 GitHub 源文件链接；构建不处理投稿或更新源 Catalog。

运行 [开发文档中的仓库检查](development.md#环境与验证入口) 可先定位数据错误。成功构建和 JavaScript 语法检查不替代实际页面验收；界面修改需在本地检查检索、筛选、详情、两类 JSON 预览与下载，兼顾中英文、浅深主题和窄屏。

## GitHub Pages 部署

维护者首次配置时，在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**，再在 Actions 手动运行 **Translation library website**。`github-pages` 环境如有部署分支限制，应允许 `main`。继续使用仓库子路径，无需额外发布分支或自定义域名；参阅 [GitHub Pages 配置说明](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。

[pages.yml](../.github/workflows/pages.yml) 在以下事件构建部署：

- `main` 推送或在 `main` 上手动运行。
- 本仓库 **Translation library automation** 或 **Translation finalizer watchdog** 成功完成。

后者使用 `workflow_run`，确保 Catalog 发布可触发网站更新，覆盖 `GITHUB_TOKEN` 推送不会触发普通 `push` 工作流的情形；参阅 [GitHub Actions 触发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。

构建总是检出最新 `main`，不执行触发工作流的 PR 代码或读取其构件。构建与部署共用串行队列，重复触发不取消已有运行。Pages 构件保存在 Actions，不提交到主分支；失败构建不覆盖已发布网站。该静态构建无需 `configure-pages` 步骤，Pages 仍须按上述方式启用。

## 常见维护问题

- **输出目录非空：** 选择新的输出路径或回收旧输出，不要清理源目录来重试。
- **本地预览无法加载：** 确认使用 HTTP，服务器指向实际构建目录；查看开发者工具中的具体资源或 Catalog 错误。
- **译本合并后网站没有更新：** 先按 [发布故障定位](development.md#维护与故障定位) 检查 Catalog 终结流程，再检查 Pages 运行和部署环境。
- **封面或头像加载失败：** 检查远程图片可达性。封面有旧地址与占位图回退，头像失败时保留用户图标；这不等同于译本下载失败。

## English

[Home](../README_EN.md)

The [library website](https://gaboron.github.io/steam-achievement-translation-library/) lives in `web/` and uses native JavaScript modules, without npm, a framework, or a backend. It consumes published catalog and translation data. See [development and maintenance](development.md#english) for submissions and catalog publication.

### Local build and preview

Run the first build and HTTP-server commands above from the repository root, then open `http://localhost:8000/`. Modules require HTTP; do not open the HTML directly. The default output `_site/` is Git-ignored, and source files stay unchanged.

Builds require a missing or empty output directory and never clear existing content. Before rebuilding, recycle the old output or use a new empty location such as `_site/preview`, as shown above. Custom output inside the repository must be under `_site/`; a new directory outside it is also supported. Point the HTTP server at the matching output directory. Default builds are offline; `--refresh-covers` refreshes Steam cover URLs in the output and retains the snapshot on failure.

### Frontend responsibilities

The module map above separates routing and preferences (`app.js`, `preferences.js`, `i18n.js`), catalog and integrity (`catalog.js`, `translation-integrity.js`), list/detail/preview views, file downloads and compatibility, shared controls, CSS, and cover data.

Use relative asset paths for repository-subpath deployment. Routes use `#/game/<app_id>`, with `/<variant_id>` for a particular variant; `?lang=zh` or `?lang=en` selects the interface language.

Preserve light and dark themes, narrow-screen layouts, visible focus, and reduced-motion support. Reuse existing menus, pagination, and transitions. CSS owns dimensions and styling; avoid maintaining a second style specification in documentation. Inter is self-hosted; see [font attribution and licenses](../LICENSE.md#bundled-fonts).

`compatibility.js` owns download-row client support. It shows actual minimum released versions per artifact type, omits unsupported clients, and shows “No compatible client yet” if none are adapted. Register support only after the compatible client release is published. See [integration](integration.md#english) for formats and older-client limitations.

### Build boundaries

`build_website.py` delegates to `website_build.py`, validating assets and catalog before packaging:

- BIN size, SHA-256, languages, and achievement counts are checked. Format 1 JSON is compared byte for byte with BIN-derived content.
- Standalone format 2 JSON is checked against catalog JSON size, hash, languages, and counts, without requiring a nonexistent BIN.
- JSON line endings expanded by Windows checkout are restored to canonical LF in output, leaving sources untouched.
- Output contains website assets, catalog, referenced BIN/JSON, and build metadata. `site-meta.json` records the source commit for pinned GitHub links. Builds do not process submissions or update the source catalog.

Use the [repository checks](development.md#environment-and-validation) to locate data errors. A build and syntax checks do not establish real page behavior. For interface changes, check search, filters, details, both JSON preview types, and downloads locally, covering both languages, themes, and narrow screens.

### Pages deployment

For initial setup, a maintainer selects **GitHub Actions** under **Settings → Pages → Build and deployment → Source**, then manually runs **Translation library website** in Actions. Allow `main` if the `github-pages` environment restricts branches. Keep the repository subpath; no extra publishing branch or custom domain is needed. See [GitHub Pages configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

[pages.yml](../.github/workflows/pages.yml) deploys on pushes or manual runs on `main`, and successful runs of this repository's **Translation library automation** or **Translation finalizer watchdog**. The `workflow_run` triggers cover catalog publication when a `GITHUB_TOKEN` push does not trigger a normal `push` workflow; see [GitHub Actions trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Builds always check out current `main`, without running triggering PR code or consuming its artifacts. Build and deployment share a serial queue, and duplicate triggers do not cancel queued runs. Pages artifacts stay in Actions rather than main; failed builds leave the published site intact. The static build needs no `configure-pages` step, but Pages must still be enabled as described above.

### Maintenance problems

- **Nonempty output:** Choose a fresh location or recycle the old output; do not clear source directories to retry.
- **Preview fails to load:** Use HTTP and point the server at the actual output. Inspect concrete resource or catalog errors in developer tools.
- **Merged translation missing:** Check [publication diagnosis](development.md#maintenance-and-diagnosis) before checking Pages runs and deployment restrictions.
- **Cover or avatar fails:** Check remote image availability. Covers fall back to legacy URLs and placeholders; avatars retain a user icon. An image failure does not establish a translation-download failure.
