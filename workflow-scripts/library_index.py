"""Library index persistence, variant metadata, and Markdown rendering."""
from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.json"
HUMAN_INDEX_PATH = REPO_ROOT / "INDEX.md"
HUMAN_INDEX_EN_PATH = REPO_ROOT / "INDEX_EN.md"
FILES_ROOT = REPO_ROOT / "files"
PENDING_REPORTS_DIR = Path(".github") / "translation-reports"
STATE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REPORT_STATE_ALIASES = {
    "文件可能过期": "outdated",
    "file may be outdated": "outdated",
    "outdated": "outdated",
    "可能过期": "outdated",
    "文件可能不生效": "possibly_ineffective",
    "file may not work": "possibly_ineffective",
    "possibly_ineffective": "possibly_ineffective",
    "可能不生效": "possibly_ineffective",
}


def clean_variant_note(value: Any, field_name: str) -> str:
    note = str(value or "").strip()
    if not note:
        raise ValueError(f"多版本清单中的 {field_name} 不能为空")
    if len(note) > 120:
        raise ValueError(f"多版本清单中的 {field_name} 不能超过 120 个字符")
    if any(ord(character) < 32 for character in note):
        raise ValueError(f"多版本清单中的 {field_name} 必须是单行文本")
    return note


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        return {"version": 1, "description": "Community-submitted Steam achievement schema translations.", "entries": []}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def pinyin_sort_key(value: str) -> tuple[bytes, str]:
    normalized = value.strip().casefold()
    return normalized.encode("gb18030", errors="ignore"), normalized


def entry_sort_key(entry: dict[str, Any]) -> tuple[bytes, str, int]:
    game_id = str(entry.get("game_id") or "0")
    try:
        numeric_id = int(game_id)
    except ValueError:
        numeric_id = 0
    return (*pinyin_sort_key(str(entry.get("game_name") or "")), numeric_id)


def sort_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=entry_sort_key)


def normalized_schema_file(schema_file: str) -> str:
    return schema_file.replace("\\", "/").lstrip("/")


def repository_path(relative_path: str) -> Path:
    """Resolve a repository-relative path without allowing path traversal."""
    raw = relative_path.strip().replace("\\", "/")
    pure_path = PurePosixPath(raw)
    if (
        not raw
        or pure_path.is_absolute()
        or any(part in {"", ".", ".."} for part in pure_path.parts)
        or re.match(r"^[A-Za-z]:", raw)
    ):
        raise ValueError(f"不安全的仓库相对路径：{relative_path or '<empty>'}")
    path = (REPO_ROOT / Path(*pure_path.parts)).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"路径超出仓库范围：{relative_path}") from exc
    return path


def schema_file_size_bytes(schema_file: str) -> int:
    normalized = normalized_schema_file(schema_file)
    path = repository_path(schema_file)
    if not path.is_file():
        raise FileNotFoundError(f"schema file is missing: {normalized}")
    return path.stat().st_size


def schema_file_size_label(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    return f"{math.floor((size_bytes / 1024) + 0.5)} KB"


def schema_variant_relative_path(game_id: str, variant_id: str, primary: bool) -> str:
    filename = f"UserGameStatsSchema_{game_id}.bin"
    return f"files/{game_id}/{filename}" if primary else f"files/{game_id}/{variant_id}/{filename}"


def entry_schema_variants(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized variant records while accepting the legacy schema_files shape."""
    primary_file = str(entry.get("schema_file") or "").strip()
    raw_variants = entry.get("schema_files")
    variants = raw_variants if isinstance(raw_variants, list) and raw_variants else [{"schema_file": primary_file}]
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            continue
        schema_file = str(raw_variant.get("schema_file") or raw_variant.get("path") or "").strip().replace("\\", "/")
        if not schema_file:
            continue
        primary = schema_file == primary_file or raw_variant.get("primary") is True
        inferred_id = "default" if primary else PurePosixPath(schema_file).parent.name
        variant_id = str(raw_variant.get("variant_id") or inferred_id).strip().lower()
        if not VARIANT_ID_RE.fullmatch(variant_id) or variant_id in seen_ids:
            continue
        seen_ids.add(variant_id)
        record = dict(raw_variant)
        record.update({
            "variant_id": variant_id,
            "primary": primary,
            "schema_file": schema_file,
        })
        if primary:
            record.setdefault("file_size_bytes", entry.get("file_size_bytes"))
            record.setdefault("sha256", entry.get("sha256"))
            record.setdefault("achievement_count", entry.get("achievement_count"))
        normalized.append(record)
    normalized.sort(key=lambda variant: (not bool(variant.get("primary")), str(variant.get("variant_id"))))
    return normalized


def validated_entry_schema_variants(
    entry: dict[str, Any],
    *,
    require_metadata: bool = False,
) -> list[dict[str, Any]]:
    records = entry_schema_variants(entry)
    raw_variants = entry.get("schema_files")
    if isinstance(raw_variants, list) and len(records) != len(raw_variants):
        raise ValueError("schema_files 包含无效或重复的版本记录")
    if not records:
        raise ValueError("没有可用的 schema 版本记录")
    primary_records = [record for record in records if record.get("primary")]
    if len(primary_records) != 1 or str(primary_records[0].get("variant_id")) != "default":
        raise ValueError("版本记录必须且只能包含一个 variant_id=default 的主版本")
    game_id = str(entry.get("game_id") or PurePosixPath(str(entry.get("schema_file") or "")).parent.name)
    explicit_variants = isinstance(raw_variants, list)
    for record in records:
        variant_id = str(record.get("variant_id") or "")
        expected_path = schema_variant_relative_path(game_id, variant_id, bool(record.get("primary")))
        if str(record.get("schema_file") or "") != expected_path:
            raise ValueError(f"版本 {variant_id} 的路径必须是 {expected_path}")
        if explicit_variants:
            clean_variant_note(record.get("note_zh"), f"版本 {variant_id} 的 note_zh")
            clean_variant_note(record.get("note_en"), f"版本 {variant_id} 的 note_en")
        if require_metadata:
            file_size = record.get("file_size_bytes")
            count = record.get("achievement_count")
            digest = str(record.get("sha256") or "")
            if not isinstance(file_size, int) or isinstance(file_size, bool) or file_size < 0:
                raise ValueError(f"版本 {variant_id} 的 file_size_bytes 无效")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(f"版本 {variant_id} 的 achievement_count 无效")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"版本 {variant_id} 的 sha256 无效")
    return records


def refresh_index_file_sizes(index: dict[str, Any]) -> None:
    for entry in index.get("entries", []):
        if not isinstance(entry, dict):
            continue
        variants = entry.get("schema_files")
        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, dict):
                    continue
                schema_file = str(variant.get("schema_file") or variant.get("path") or "").strip()
                if schema_file:
                    variant["file_size_bytes"] = schema_file_size_bytes(schema_file)
        schema_file = str(entry.get("schema_file") or "").strip()
        if schema_file:
            entry["file_size_bytes"] = schema_file_size_bytes(schema_file)


def write_index(index: dict[str, Any]) -> None:
    index.setdefault("version", 1)
    index.setdefault("description", "Community-submitted Steam achievement schema translations.")
    refresh_index_file_sizes(index)
    index["entries"] = sort_entries(index.get("entries", []))
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def existing_entry(index: dict[str, Any], game_id: str) -> dict[str, Any] | None:
    for entry in index.get("entries", []):
        if str(entry.get("game_id")) == game_id:
            return entry
    return None


def upsert_index_entry(entry: dict[str, Any]) -> None:
    index = load_index()
    game_id = str(entry.get("game_id") or "")
    existing = existing_entry(index, game_id)
    if existing and "schema_files" in existing and "schema_files" not in entry:
        entry = dict(entry)
        entry["schema_files"] = existing["schema_files"]
    index["entries"] = [item for item in index.get("entries", []) if str(item.get("game_id")) != game_id] + [entry]
    write_index(index)
    write_human_index(index)


def pending_report_relative_path(issue_number: int) -> Path:
    if issue_number < 1:
        raise ValueError("source issue number must be positive")
    return PENDING_REPORTS_DIR / f"{issue_number}.json"


def write_pending_report(entry: dict[str, Any], issue_number: int) -> str:
    """Write the review artifact without changing the live library index."""
    relative_path = pending_report_relative_path(issue_number)
    path = REPO_ROOT / relative_path
    report = entry_problem_report(entry)
    payload = {
        "format_version": "1.0.0",
        "game_id": str(entry.get("game_id") or ""),
        "game_name": str(entry.get("game_name") or ""),
        "store_url": str(entry.get("store_url") or ""),
        "report": report,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return relative_path.as_posix()


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def schema_download_url(schema_file: str, repository: str | None = None) -> str:
    normalized = normalized_schema_file(schema_file)
    encoded_path = urllib.parse.quote(normalized, safe="/")
    repo = repository or os.environ.get("GITHUB_REPOSITORY", "GaBoron/steam-achievement-translation-library")
    return f"https://cdn.jsdelivr.net/gh/{repo}@main/{encoded_path}"


def variant_file_size_bytes(entry: dict[str, Any], variant: dict[str, Any], schema_file: str) -> int:
    raw_size = variant.get("file_size_bytes")
    if isinstance(raw_size, int):
        return raw_size
    if isinstance(raw_size, str) and raw_size.isdigit():
        return int(raw_size)
    if schema_file == str(entry.get("schema_file") or "").strip():
        entry_size = entry.get("file_size_bytes")
        if isinstance(entry_size, int):
            return entry_size
        if isinstance(entry_size, str) and entry_size.isdigit():
            return int(entry_size)
    return schema_file_size_bytes(schema_file)


def entry_file_size_bytes(entry: dict[str, Any], schema_file: str) -> int:
    raw_size = entry.get("file_size_bytes")
    if isinstance(raw_size, int):
        return raw_size
    if isinstance(raw_size, str) and raw_size.isdigit():
        return int(raw_size)
    return schema_file_size_bytes(schema_file)


def note_text(value: str, language: str) -> str:
    note = value.strip()
    if not note:
        return ""
    if language == "zh":
        return note.removeprefix("（").removesuffix("）")
    return note.removeprefix("(").removesuffix(")")


def file_link_with_details(schema_file: str, size_bytes: int, language: str, note: str = "") -> str:
    schema_name = PurePosixPath(schema_file).name
    link = f"[{escape_table(schema_name)}]({schema_download_url(schema_file)})"
    size = schema_file_size_label(size_bytes)
    clean_note = note_text(note, language)
    if clean_note:
        if language == "zh":
            return f"{link}（{escape_table(clean_note)}，{size}）"
        return f"{link} ({escape_table(clean_note)}, {size})"
    if language == "zh":
        return f"{link}（{size}）"
    return f"{link} ({size})"


def entry_file_size_label(entry: dict[str, Any]) -> str:
    schema_file = str(entry.get("schema_file") or "").strip()
    if not schema_file:
        return ""
    return schema_file_size_label(entry_file_size_bytes(entry, schema_file))


def schema_file_links(entry: dict[str, Any], language: str) -> str:
    variants = entry.get("schema_files")
    links: list[str] = []
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            schema_file = str(variant.get("schema_file") or variant.get("path") or "").strip()
            if not schema_file:
                continue
            note = str(
                variant.get(f"note_{language}")
                or variant.get("note")
                or variant.get(f"description_{language}")
                or variant.get("description")
                or ""
            ).strip()
            size_bytes = variant_file_size_bytes(entry, variant, schema_file)
            links.append(file_link_with_details(schema_file, size_bytes, language, note))
    if links:
        return "<br>".join(links)

    schema_file = str(entry.get("schema_file", "")).strip()
    if not schema_file:
        return ""
    size_bytes = entry_file_size_bytes(entry, schema_file)
    return file_link_with_details(schema_file, size_bytes, language)


def github_link(url: str, label: str) -> str:
    return f"[{label}]({url})" if url else ""


def pull_request_label(url: str) -> str:
    match = re.search(r"/pull/(\d+)(?:[#?].*)?$", url)
    return f"#{match.group(1)}" if match else "PR"


def github_item_label(url: str, fallback: str) -> str:
    match = re.search(r"/(?:pull|issues)/(\d+)(?:[#?].*)?$", url)
    return f"#{match.group(1)}" if match else fallback


def contributor_markdown(contributors: list[str]) -> str:
    links: list[str] = []
    for contributor in contributors:
        clean = contributor.strip()
        if not clean:
            continue
        links.append(f"[@{escape_table(clean)}](https://github.com/{urllib.parse.quote(clean, safe='')})")
    return ", ".join(links)


def entry_contributors(entry: dict[str, Any]) -> list[str]:
    contributors = [str(item).strip() for item in entry.get("contributors", []) if str(item).strip()]
    legacy = str(entry.get("contributor_id") or "").strip()
    if legacy:
        contributors.append(legacy)
    return sorted(set(contributors), key=str.casefold)


def report_state(value: str) -> str:
    clean = value.strip().casefold()
    if not clean:
        return "outdated"  # Legacy reports did not include an issue type.
    state = REPORT_STATE_ALIASES.get(clean)
    if state is None:
        raise ValueError("错误类型必须选择“文件可能过期”或“文件可能不生效”。")
    return state


def entry_problem_report(entry: dict[str, Any]) -> dict[str, Any]:
    report = entry.get("report")
    if isinstance(report, dict):
        return dict(report)
    outdated = entry.get("outdated")
    if isinstance(outdated, dict):
        legacy = dict(outdated)
        legacy.setdefault("type", "outdated")
        return legacy
    return {}


def index_states(index: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw_states = index.get("states")
    if not isinstance(raw_states, dict) or not raw_states:
        raise ValueError("index.json states must be a non-empty object")
    states: dict[str, dict[str, str]] = {}
    for state_id, raw_labels in raw_states.items():
        if not isinstance(state_id, str) or not STATE_RE.fullmatch(state_id):
            raise ValueError(f"invalid index state ID: {state_id!r}")
        if not isinstance(raw_labels, dict):
            raise ValueError(f"index state {state_id!r} must contain label_zh and label_en")
        labels = {
            "zh": str(raw_labels.get("label_zh") or "").strip(),
            "en": str(raw_labels.get("label_en") or "").strip(),
        }
        if not all(labels.values()):
            raise ValueError(f"index state {state_id!r} must contain non-empty label_zh and label_en")
        states[state_id] = labels
    for required_state in ("current", "possibly_ineffective", "outdated"):
        if required_state not in states:
            raise ValueError(f"index.json states is missing required state {required_state!r}")
    return states


def status_text(entry: dict[str, Any], language: str, states: dict[str, dict[str, str]]) -> str:
    state_id = "outdated" if entry.get("outdated") and not entry.get("report") else str(entry.get("status") or "current")
    if state_id not in states:
        raise ValueError(f"unknown index state {state_id!r} for Steam app ID {entry.get('game_id', '')}")
    return states[state_id][language]


def render_human_index(index: dict[str, Any]) -> tuple[str, str]:
    entries = sort_entries(index.get("entries", []))
    states = index_states(index)
    entry_count = len(entries)
    current_zh = states["current"]["zh"]
    ineffective_zh = states["possibly_ineffective"]["zh"]
    outdated_zh = states["outdated"]["zh"]
    current_en = states["current"]["en"]
    ineffective_en = states["possibly_ineffective"]["en"]
    outdated_en = states["outdated"]["en"]
    zh_lines = [
        "# Steam 成就翻译库索引",
        "",
        "简体中文 | [English](INDEX_EN.md) | [项目说明](README.md)",
        "",
        f"> 下载后请核对索引标注的文件大小；如果文件大小明显不对，请不要替换本地文件。标记为“{ineffective_zh}”或“{outdated_zh}”的文件请谨慎使用。",
        "",
        f"当前收录：**{entry_count}** 个游戏。",
        "",
        f"状态说明：{current_zh}；{ineffective_zh}（文件通过仓库校验，但受游戏或平台机制影响，替换后可能不起作用）；{outdated_zh}（游戏更新后，文件内容可能已经失效）。",
        "",
        "## 使用这个索引",
        "",
        "1. 用浏览器或 GitHub 搜索 Steam app ID、游戏名、贡献者或语言代码。",
        f"2. 在目标行确认“状态”和“最近更新”。状态为“{ineffective_zh}”或“{outdated_zh}”时，请谨慎使用。",
        "3. 点击“文件”列里的文件名下载，并在下载后核对索引标注的文件大小。",
        "4. 文件大小明显不对时不要替换本地文件；确认无误后再放到 Steam 本地 `<Steam 安装目录>/appcache/stats/` 中的同名位置。",
        "",
        "更完整的查找、下载和替换流程见 [README.md](README.md)。",
        "",
        "## 游戏列表",
        "",
    ]
    en_lines = [
        "# Steam Achievement Translation Index",
        "",
        "[简体中文](INDEX.md) | English | [Project README](README_EN.md)",
        "",
        f"> After downloading, compare the file size with the index. If the size is clearly wrong, do not replace your local file. Use files marked as “{ineffective_en}” or “{outdated_en}” with extra care.",
        "",
        f"Accepted games: **{entry_count}**.",
        "",
        f"Status guide: {current_en}; {ineffective_en} (the file passes repository checks, but game or platform behavior may prevent it from taking effect); {outdated_en} (a game update may have invalidated the file).",
        "",
        "## Using This Index",
        "",
        "1. Search with your browser or GitHub page search by Steam app ID, game name, contributor, or language code.",
        f"2. Check Status and Last updated in the matching row. Use files marked as {ineffective_en} or {outdated_en} carefully.",
        "3. Click the filename in the File column to download it, then compare the downloaded size with the index.",
        "4. If the size is clearly wrong, do not replace your local file. After confirming it, place it under the matching local Steam file path in `<Steam install directory>/appcache/stats/`.",
        "",
        "See [README_EN.md](README_EN.md) for the full find, download, and replacement flow.",
        "",
        "## Games",
        "",
    ]
    if entries:
        zh_lines.extend([
            "| Steam app ID | 游戏 | 状态 | 最近更新 | 贡献者 | 语言 | 成就数 | 文件 | 原 PR | 错误报告 | 商店 |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ])
        en_lines.extend([
            "| Steam app ID | Game | Status | Last updated | Contributors | Languages | Achievements | File | Source PR | Issue report | Store |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ])
        for entry in entries:
            game_id = str(entry.get("game_id", ""))
            schema_links_zh = schema_file_links(entry, "zh")
            schema_links_en = schema_file_links(entry, "en")
            report = entry_problem_report(entry)
            source_pr = str(entry.get("source_pr") or "")
            report_link = str(report.get("source_pr") or report.get("source_issue") or "")
            row = (
                f"| `{game_id}` | {escape_table(str(entry.get('game_name', '')))} | {status_text(entry, 'zh', states)} | "
                f"{escape_table(str(entry.get('updated_at') or entry.get('submitted_at') or ''))} | {contributor_markdown(entry_contributors(entry))} | "
                f"{escape_table(', '.join(entry.get('languages', [])))} | {entry.get('achievement_count', '')} | "
                f"{schema_links_zh} | {github_link(source_pr, pull_request_label(source_pr)) if source_pr else ''} | "
                f"{github_link(report_link, github_item_label(report_link, '报告')) if report_link else ''} | [Steam]({entry.get('store_url', '')}) |"
            )
            zh_lines.append(row)
            en_lines.append(
                f"| `{game_id}` | {escape_table(str(entry.get('game_name', '')))} | {status_text(entry, 'en', states)} | "
                f"{escape_table(str(entry.get('updated_at') or entry.get('submitted_at') or ''))} | {contributor_markdown(entry_contributors(entry))} | "
                f"{escape_table(', '.join(entry.get('languages', [])))} | {entry.get('achievement_count', '')} | "
                f"{schema_links_en} | {github_link(source_pr, pull_request_label(source_pr)) if source_pr else ''} | "
                f"{github_link(report_link, github_item_label(report_link, 'Report')) if report_link else ''} | [Steam]({entry.get('store_url', '')}) |"
            )
    else:
        zh_lines.append("暂无已收录游戏。")
        en_lines.append("No accepted games yet.")
    return "\n".join(zh_lines) + "\n", "\n".join(en_lines) + "\n"


def write_human_index(index: dict[str, Any]) -> None:
    zh_index, en_index = render_human_index(index)
    HUMAN_INDEX_PATH.write_text(zh_index, encoding="utf-8")
    HUMAN_INDEX_EN_PATH.write_text(en_index, encoding="utf-8")
