# 数据接入指南

[返回首页](../README.md) · [English](#english)

本指南面向读取社区译本的客户端开发者。公开接口是 `index-v2.json` 与其引用的 `files/` 文件，可匿名读取，无需密钥或 fork。文本结构见 [翻译 JSON 格式](translation-json.md)，浏览译本使用 [网站](https://gaboron.github.io/steam-achievement-translation-library/?lang=zh)。

## 选择游戏、版本与文件

顶层 `version` 为 `2`，`games` 以字符串 App ID 为键，每个游戏的 `variants` 以版本 ID 为键。按键查找，不依赖对象排列顺序。客户端可容忍额外元数据，但遇到不支持的版本、文件类型或缺失的必要字段应停止应用。

| 游戏字段 | 含义 |
| --- | --- |
| `name` | 游戏名称 |
| `contributors` | 贡献者 GitHub 用户名数组 |
| `submitted_at` / `updated_at` | 首次收录与最近更新的 ISO 8601 时间 |
| `status` | `current`、`possibly_ineffective` 或 `outdated`；省略时为 `current` |
| `variants` | 1–16 个版本，必须包含默认选择 `default` |

版本 ID 匹配 `[a-z0-9][a-z0-9-]{0,63}`。版本不是语言：同一版本可包含多种 Steam 语言，各版本的语言与成就数可以不同。多版本游戏使用双语 `label` 和可选 `description` 说明适用范围；单版本条目的 `label` 可以省略。

| 通用版本字段 | 含义 |
| --- | --- |
| `format` | 省略或为 `bin` 表示 BIN 版本；`json` 表示独立 JSON 版本 |
| `languages` | 已检测到的 Steam 语言代码，排序且不重复，如 `english`、`schinese` |
| `achievements` | 该版本的成就数量 |
| `label` / `description` | 包含 `zh`、`en` 的版本名称与适用说明 |

文件类型决定可下载的内容与校验位置：

| 类型 | 文件与元数据 | 校验方式 |
| --- | --- | --- |
| BIN | `.bin`；版本顶层的 `size`、`sha256` | 比较 BIN 原始字节数与哈希 |
| BIN 派生 JSON | `.json`；`json.version == 1`、`json.size` | 比较 JSON 字节数与文本元数据，核对 `source_sha256 == variant.sha256` |
| 独立 JSON | `format: "json"`；`json.version == 2`、`json.size`、`json.sha256` | 比较 JSON 自身原始字节数与哈希，再检查文本元数据 |

BIN 版本可提供格式 1 JSON；独立 JSON 版本没有 BIN，不声明顶层 `sha256` 或 `size`。格式 1 的 `source_sha256` 标识源 BIN，并不是 JSON 自身的哈希。不要给 JSON-only 版本补造 BIN 元数据，或把 JSON 安装为 BIN。

## 获取一致的数据快照

临时查询可直接读取 `main`：

```bash
curl -fL https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/main/index-v2.json
curl -fL https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/main/files/10180/default/UserGameStatsSchema_10180.json
```

需要一致缓存或下载多个文件时，先通过 [GitHub Commit API](https://docs.github.com/en/rest/commits/commits#get-a-commit) 将 `main` 解析为完整提交 SHA，再让 Catalog 与文件共用该 SHA：

```text
https://api.github.com/repos/GaBoron/steam-achievement-translation-library/commits/main
https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/<commit_sha>/index-v2.json
https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/<commit_sha>/files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.bin
https://raw.githubusercontent.com/GaBoron/steam-achievement-translation-library/<commit_sha>/files/<app_id>/<variant_id>/UserGameStatsSchema_<app_id>.json
```

仅下载 Catalog 中声明存在的文件。使用 CDN 时也固定同一 SHA；缓存应在整组校验通过后再替换。更新失败时保留已验证缓存，检查更新可使用条件请求。直接读取 `main` 时若遇到更新期间的校验不一致，应重新获取 Catalog 和文件。

商店链接由 App ID 推导为 `https://store.steampowered.com/app/<app_id>/`。`submission.json` 是审核中的待入库数据，不能当作公开 Catalog 使用。

## 应用前的检查

- 单个 BIN 或 JSON 不超过 32 MiB。发布的 JSON 使用 UTF-8、LF 和结尾换行；字节数与哈希按收到的原始字节计算，不能先重新序列化。
- JSON 的格式版本、`app_id`、`variant_id`、完整语言列表和成就数必须与所选 Catalog 版本一致，再按上表执行格式对应的关联或哈希校验。
- 以 `(app_id, API name, language)` 匹配文本，保留空字段。完整字段结构与限制以 [JSON 格式](translation-json.md) 为准。
- 向用户展示 `possibly_ineffective`、`outdated` 状态；`current` 表示库中的当前状态，不承诺所有 Steam 环境均有效。
- 语言或文件缺失、未知格式、超时或校验失败时停止应用本次下载，并保留可用缓存。显示 JSON 不包含解锁状态、进度、图标或可写回 BIN 的完整节点。

> [!IMPORTANT]
> 独立格式 2 JSON 需要支持 JSON-only Catalog 条目的客户端。SATLI lite 0.2.0+ 支持格式 1 和 2；0.1.x 只支持格式 1，且可能拒绝包含 JSON-only 条目的整份目录，应先升级。其他客户端以其已发布支持范围为准。

## Python 读取示例

以下示例只使用标准库，演示固定快照、按格式校验和读取所选语言。`APP_ID`、`VARIANT_ID` 和 `LANGUAGE` 由客户端选择；这是读取示例，不包含安装、完整格式校验器或缓存实现。

```python
import hashlib
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
variant = catalog["games"][APP_ID]["variants"][VARIANT_ID]
artifact_format = variant.get("format", "bin")
if artifact_format not in {"bin", "json"}:
    raise ValueError("Unsupported artifact format")
expected_version = 2 if artifact_format == "json" else 1
metadata = variant.get("json", {})
if metadata.get("version") != expected_version or LANGUAGE not in variant["languages"]:
    raise ValueError("Requested text format or language is unavailable")

path = f"files/{APP_ID}/{VARIANT_ID}/UserGameStatsSchema_{APP_ID}.json"
raw = fetch(f"{base}/{path}")
if len(raw) != metadata["size"]:
    raise ValueError("Translation size does not match catalog")
if artifact_format == "json":
    if "sha256" in variant or "size" in variant:
        raise ValueError("JSON-only variant declares BIN metadata")
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("Translation hash does not match catalog")

text = json.loads(raw)
if (
    text["version"] != expected_version
    or text["app_id"] != APP_ID
    or text["variant_id"] != VARIANT_ID
    or text["languages"] != variant["languages"]
    or len(text["achievements"]) != variant["achievements"]
):
    raise ValueError("Translation metadata does not match catalog")
if artifact_format == "json":
    if set(text) != {"version", "app_id", "variant_id", "languages", "achievements"}:
        raise ValueError("Unsupported standalone JSON fields")
elif text["source_sha256"] != variant["sha256"]:
    raise ValueError("Translation does not identify the catalog BIN")

for api_name, achievement in text["achievements"].items():
    fields = achievement["translations"][LANGUAGE]
    print(api_name, fields["name"], fields["description"])
```

生产客户端还需处理限流、重试、完整格式验证、缓存与界面转义。展示时保留贡献者和翻译库来源链接，遵守 [LICENSE.md](../LICENSE.md) 中适用于译文和第三方内容的条款；修改译文时也应保留相应说明。

## English

[Home](../README_EN.md)

This guide is for client developers consuming community translations. The public interface is `index-v2.json` and its referenced `files/` data, available anonymously without a key or fork. See the [JSON format](translation-json.md#english) for text structure and the [website](https://gaboron.github.io/steam-achievement-translation-library/?lang=en) for browsing.

### Select a game, variant, and artifact

Catalog `version` is `2`. `games` is keyed by string App ID, with each game's `variants` keyed by variant ID. Use keys, not object order. Clients may tolerate additional metadata but must stop applying unsupported versions, unknown artifact types, or entries missing required fields.

Game fields are `name`, GitHub usernames in `contributors`, ISO 8601 `submitted_at` and `updated_at`, and `variants`. Optional `status` is `current`, `possibly_ineffective`, or `outdated`, defaulting to `current`.

There are 1–16 variants, including `default`. IDs match `[a-z0-9][a-z0-9-]{0,63}`. A variant is not a language: each has its own sorted, unique Steam `languages` and `achievements` count. Multi-variant entries have bilingual `label` and optional `description` fields identifying their scope; a single variant may omit its label.

| Artifact | Metadata and validation |
| --- | --- |
| BIN (`format` omitted or `bin`) | Download `.bin`; verify its raw byte count and hash against top-level `size` and `sha256` |
| BIN-derived JSON | Download `.json` if declared; require `json.version == 1`, verify `json.size` and text metadata, and match `source_sha256` to the BIN's `variant.sha256` |
| Standalone JSON (`format: "json"`) | No BIN or top-level BIN `size`/`sha256`; require `json.version == 2` and verify the JSON's own bytes against `json.size` and `json.sha256`, then its text metadata |

Format 1 `source_sha256` identifies the BIN, not the JSON's own hash. Do not invent BIN metadata for JSON-only variants or install JSON as BIN.

### Fetch one consistent snapshot

The curl examples above support one-off reads from `main`. For consistent multi-file downloads or caching, resolve `main` to a full commit SHA using the [GitHub Commit API](https://docs.github.com/en/rest/commits/commits#get-a-commit), then use that SHA for the catalog and every downloaded file, including CDN requests. Download only files declared in the catalog.

Replace a cached group only after all files pass validation. Retain validated caches on failure and use conditional requests for update checks. If a direct `main` read races with publication, fetch the catalog and files again. Derive store links from the App ID. Pending `submission.json` proposals are not a public client interface.

### Check before applying

Each BIN or JSON is limited to 32 MiB. Published JSON uses UTF-8, LF, and a final newline. Measure received bytes before decoding or reserializing. JSON format version, app and variant IDs, the full language list, and achievement count must match the selected catalog variant, followed by the artifact-specific checks above.

Match text by `(app_id, API name, language)` and preserve empty fields. Apply the full [JSON contract](translation-json.md#english). Display `possibly_ineffective` and `outdated` status; `current` is a library status, not guaranteed compatibility in every Steam environment. Missing files or languages, unknown formats, timeouts, and failed checks stop application of the download while retaining a working cache. Display JSON has no unlock state, progress, icons, or complete nodes for writing a BIN.

> [!IMPORTANT]
> Standalone format 2 requires support for JSON-only catalog entries. SATLI lite 0.2.0+ supports formats 1 and 2. Versions 0.1.x support only format 1 and may reject an entire catalog containing JSON-only entries; upgrade first. Other clients must be checked against their released support.

The standard-library Python example above demonstrates a pinned snapshot, artifact-specific checks, and selected-language text access. It does not implement installation, a complete schema validator, or caching. Production clients also need rate-limit, retry, validation, cache, and UI-escaping handling. Retain contributor attribution and a library source link, follow the applicable translation and third-party terms in [LICENSE.md](../LICENSE.md), and keep notices of changes when modifying translations.
