# 数据接入指南

[English](#english)

本指南面向读取社区译本的客户端开发者。公开数据由 `index-v2.json` 与 `files/` 组成；文本浏览和预览使用 [翻译库网站](https://gaboron.github.io/steam-achievement-translation-library/?lang=zh)。

## 临时调用

公开数据可以匿名读取，无需注册、申请密钥或 fork 仓库。临时脚本、单次查询可直接下载 `main` 上的文件，例如：

```bash
curl -fL https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/main/index-v2.json
curl -fL https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/main/files/10180/default/UserGameStatsSchema_10180.json
```

查其他游戏时，从 Catalog 选择 App ID、版本和语言。若查询期间 `main` 发生更新导致校验不匹配，重新获取 Catalog 与文件即可。

## 获取同一份数据快照

仓库为 `GaBoron/steam-achievement-translation-library`，发布分支为 `main`。需要一致缓存多个文件时，先通过 [GitHub Commit API](https://docs.github.com/en/rest/commits/commits#get-a-commit) 解析 `main` 的完整提交 SHA，再用该 SHA 下载 Catalog 与文件：

```text
https://api.github.com/repos/GaBoron/steam-achievement-translation-library/commits/main
https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/<commit_sha>/index-v2.json
https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/<commit_sha>/files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.bin
https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/<commit_sha>/files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.json
```

一次下载始终使用同一 SHA；使用 CDN 时也按该 SHA 固定版本。缓存完整快照，更新失败时继续使用已校验的缓存。检查更新可使用 GitHub API 的条件请求，避免每次启动重复下载全部文件。

## 读取 Catalog

顶层 `version` 为 `2`，`games` 以字符串 App ID 为键。按键查找游戏，不依赖对象排列顺序；允许未知字段，遇到不支持的格式版本应停止应用。

| 字段 | 含义 |
| --- | --- |
| `name` | 游戏名称 |
| `contributors` | 贡献者 GitHub 用户名数组 |
| `submitted_at` / `updated_at` | 首次收录与最近更新的 ISO 8601 时间 |
| `status` | `current`、`possibly_ineffective` 或 `outdated`；省略时为 `current` |
| `variants` | 以版本 ID 为键的对象，包含 `default`，共 1–16 个版本 |

每个版本独立选择与校验。`default` 是默认选择；其他版本的适用范围由双语 `label` 和可选 `description` 说明。版本 ID 匹配 `[a-z0-9][a-z0-9-]{0,63}`。不要把版本 ID 当作语言；每个版本的语言和成就数可以不同。

| 版本字段 | 含义 |
| --- | --- |
| `sha256` / `size` | BIN 的 SHA-256 与字节数 |
| `languages` | 该版本检测到的 Steam 语言代码，如 `english`、`schinese` |
| `achievements` | 成就数量 |
| `json.version` / `json.size` | 显示文本 JSON 的格式版本与 UTF-8 字节数；提供 JSON 的版本具有此字段 |
| `label` / `description` | 含 `zh`、`en` 的版本名称与适用说明 |

路径由 App ID 和版本 ID 推导。商店链接为 `https://store.steampowered.com/app/<app_id>/`。`submission.json` 是审核中的投稿元数据，客户端只读取 Catalog 中列出的已发布条目。

## 下载与校验

- **完整 schema：** 下载 BIN，核对 `size` 与 `sha256`。它是 Steam Binary KeyValues 数据，安装、备份和恢复由客户端负责。
- **显示文本：** 确认 `json.version == 1`，下载 JSON，核对 `json.size`、`version`、`app_id`、`variant_id`、`languages`、成就数以及 `source_sha256 == variant.sha256`。`source_sha256` 标识源 BIN，不是 JSON 自身的哈希。
- 单个 BIN 或 JSON 上限为 32 MiB。JSON 使用 UTF-8、LF 与结尾换行；字节数按收到的原始字节计算。
- 以 `(app_id, API name, language)` 匹配显示文本，保留空字段。JSON 不包含解锁状态、进度、图标或可写回 BIN 的完整节点，详见 [JSON 格式](translation-json.md)。
- 展示 `possibly_ineffective`、`outdated` 状态供用户判断；语言缺失、文件缺失、格式未知或校验失败时停止应用，保留可用缓存。

以下 Python 示例只依赖标准库，`APP_ID`、`VARIANT_ID` 和 `LANGUAGE` 由客户端选择：

```python
import json
from urllib.request import Request, urlopen

REPO = "GaBoron/steam-achievement-translation-library"
APP_ID, VARIANT_ID, LANGUAGE = "10180", "default", "schinese"
LIMIT = 32 * 1024 * 1024

def fetch(url):
    request = Request(url, headers={"User-Agent": "translation-library-client"})
    with urlopen(request, timeout=30) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Download exceeds size limit")
    return data

revision = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/main"))["sha"]
base = f"https://raw.githubusercontent.com/{REPO}/{revision}"
catalog = json.loads(fetch(f"{base}/index-v2.json"))
if catalog["version"] != 2:
    raise ValueError("Unsupported catalog format")
game = catalog["games"][APP_ID]
variant = game["variants"][VARIANT_ID]
if variant.get("json", {}).get("version") != 1 or LANGUAGE not in variant["languages"]:
    raise ValueError("Requested text format or language is unavailable")

file = f"files/{APP_ID}/{VARIANT_ID}/UserGameStatsSchema_{APP_ID}.json"
raw = fetch(f"{base}/{file}")
text = json.loads(raw)
valid = (
    len(raw) == variant["json"]["size"]
    and text["version"] == 1
    and text["app_id"] == APP_ID
    and text["variant_id"] == VARIANT_ID
    and text["source_sha256"] == variant["sha256"]
    and text["languages"] == variant["languages"]
    and len(text["achievements"]) == variant["achievements"]
)
if not valid:
    raise ValueError("Translation does not match catalog")
for api_name, achievement in text["achievements"].items():
    fields = achievement["translations"][LANGUAGE]
    print(api_name, fields["name"], fields["description"])
```

下载只是接入的读取部分，生产客户端还需处理超时、限流、缓存和界面转义。贡献者译文遵循 CC BY 4.0，原始游戏内容与 Steam schema 的权利归对应权利方；展示游戏条目时保留贡献者和翻译库来源链接，详见 [许可证与权利](../LICENSE.md)。

## English

This guide is for developers consuming community translations. Read `index-v2.json` and `files/`; use the [website](https://gaboron.github.io/steam-achievement-translation-library/?lang=en) to browse and preview text.

Public data supports anonymous, temporary access without registration, an API key, or a fork. One-off scripts may fetch directly from `main` using the curl examples above. Choose app, variant, and language from the catalog; if a concurrent update causes a mismatch, fetch both files again.

For a consistent multi-file cache, resolve `main` to a full commit SHA with the [GitHub Commit API](https://docs.github.com/en/rest/commits/commits#get-a-commit), then fetch the catalog and downloads using that same SHA in the URLs above, including when using a CDN. Cache complete validated snapshots, retain the working cache on update failure, and use conditional API requests for update checks.

The catalog has `version: 2` and a `games` object keyed by string app IDs. Look up keys rather than relying on object order. Accept unknown fields; stop applying unsupported format versions. A game contains `name`, GitHub usernames in `contributors`, ISO 8601 `submitted_at` / `updated_at`, and `variants`. Its optional `status` is `current`, `possibly_ineffective`, or `outdated`, defaulting to `current`.

There are 1–16 variants, including the default choice `default`. Variant IDs match `[a-z0-9][a-z0-9-]{0,63}`. Each variant has its own `languages` and `achievements`, BIN `sha256` and byte `size`, and optional `json` metadata declaring text format `version` and UTF-8 byte `size`. Bilingual `label` and optional `description` identify the intended game version; they are required as appropriate for multi-variant entries. A variant ID is not a language.

Derive file paths from app and variant IDs using the URLs above. Store links use `https://store.steampowered.com/app/<app_id>/`. Consume only published games listed in the catalog; `submission.json` is pending review metadata.

For BIN downloads, verify byte size and SHA-256. BIN is complete Steam Binary KeyValues data; clients handle installation, backups, and restoration. For JSON, require `json.version == 1` and verify byte size, format version, app and variant IDs, language list, achievement count, and `source_sha256 == variant.sha256`. This identifies the source BIN, rather than hashing the JSON. Each BIN or JSON is limited to 32 MiB. JSON uses UTF-8, LF, and a final newline; measure the received bytes before decoding.

Match display text by `(app_id, API name, language)` and preserve empty fields. JSON contains no unlock state, progress, icons, or complete nodes for writing a BIN; see the [JSON format](translation-json.md#english). Display catalog status to the user. Missing languages or files, unknown formats, and failed integrity checks must stop application while preserving a working cache.

The standard-library Python example above resolves a snapshot and validates text for a selected app, variant, and language. Production clients also need timeout, rate-limit, cache, and UI-escaping handling. Contributor-owned translations use CC BY 4.0; original game content and Steam schema rights belong to their respective holders. Preserve contributor attribution and a library source link; see [license and rights](../LICENSE.md).
