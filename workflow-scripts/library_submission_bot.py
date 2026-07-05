#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.json"
HUMAN_INDEX_PATH = REPO_ROOT / "INDEX.md"
HUMAN_INDEX_EN_PATH = REPO_ROOT / "INDEX_EN.md"
FILES_ROOT = REPO_ROOT / "files"

MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
ATTACHMENT_RE = re.compile(
    r"\[([^\]]+)\]\((https://github\.com/user-attachments/[^\s)]+)\)|(?<!\()(?P<url>https://github\.com/user-attachments/[^\s)]+)"
)
TYPE_NAMES = {0: "BEGIN", 1: "STRING", 2: "INT32", 3: "FLOAT32", 4: "POINTER", 5: "WIDESTRING", 6: "COLOR", 7: "UINT64", 8: "END"}


@dataclass
class Attachment:
    filename: str
    url: str
    filename_from_url: bool = False


@dataclass
class Node:
    type_id: int
    name: str
    children: list["Node"] = field(default_factory=list)
    value: str | None = None
    raw_value: bytes = b""


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def u8(self) -> int:
        if self.pos >= len(self.data):
            raise EOFError("unexpected EOF reading node type")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def bytes(self, size: int) -> bytes:
        if self.pos + size > len(self.data):
            raise EOFError("unexpected EOF reading node value")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def cbytes(self) -> bytes:
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise EOFError("unterminated string")
        value = self.data[self.pos:end]
        self.pos = end + 1
        return value

    def cstr(self) -> str:
        return self.cbytes().decode("utf-8")


def parse_nodes(reader: Reader) -> list[Node]:
    nodes: list[Node] = []
    while True:
        type_id = reader.u8()
        if type_id == 8:
            return nodes
        if type_id not in TYPE_NAMES:
            raise ValueError(f"unknown Binary KeyValues node type {type_id} at offset {reader.pos - 1}")
        name = reader.cstr()
        node = Node(type_id, name)
        if type_id == 0:
            node.children = parse_nodes(reader)
        elif type_id == 1:
            raw = reader.cbytes()
            node.raw_value = raw
            node.value = raw.decode("utf-8")
        elif type_id in (2, 3, 4, 6):
            node.raw_value = reader.bytes(4)
        elif type_id == 7:
            node.raw_value = reader.bytes(8)
        elif type_id == 5:
            raise NotImplementedError("WideString nodes are not supported by the review parser")
        nodes.append(node)


def cstr(value: str) -> bytes:
    return value.encode("utf-8") + b"\0"


def serialize(nodes: list[Node]) -> bytes:
    output = bytearray()
    for node in nodes:
        output.append(node.type_id)
        output.extend(cstr(node.name))
        if node.type_id == 0:
            output.extend(serialize(node.children))
        elif node.type_id == 1:
            output.extend(cstr(node.value if node.value is not None else node.raw_value.decode("utf-8")))
        elif node.type_id in (2, 3, 4, 6, 7):
            output.extend(node.raw_value)
        else:
            raise NotImplementedError(f"cannot serialize Binary KeyValues node type {node.type_id}")
    output.append(8)
    return bytes(output)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def walk(nodes: list[Node]):
    for node in nodes:
        yield node
        if node.children:
            yield from walk(node.children)


def begins(node: Node, name: str) -> list[Node]:
    return [child for child in node.children if child.type_id == 0 and child.name == name]


def strings(node: Node, name: str) -> list[Node]:
    return [child for child in node.children if child.type_id == 1 and child.name == name]


def first_str(node: Node, name: str) -> str:
    matches = strings(node, name)
    return (matches[0].value or "") if matches else ""


def nested(node: Node, *names: str) -> Node | None:
    current: Node | None = node
    for name in names:
        if current is None:
            return None
        matches = begins(current, name)
        current = matches[0] if matches else None
    return current


def achievement_nodes(nodes: list[Node]) -> list[Node]:
    output: list[Node] = []
    for bits in [node for node in walk(nodes) if node.type_id == 0 and node.name == "bits"]:
        for child in bits.children:
            if child.type_id == 0 and strings(child, "name") and nested(child, "display", "name") and nested(child, "display", "desc"):
                output.append(child)
    return output


def load_schema(path: Path) -> tuple[bytes, list[Node]]:
    data = path.read_bytes()
    reader = Reader(data)
    nodes = parse_nodes(reader)
    if reader.pos != len(data):
        raise ValueError(f"parser stopped at offset {reader.pos}, file size is {len(data)}")
    return data, nodes


def achievement_rows(nodes: list[Node], languages: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, achievement in enumerate(achievement_nodes(nodes), 1):
        display_name = nested(achievement, "display", "name")
        display_desc = nested(achievement, "display", "desc")
        if display_name is None or display_desc is None:
            continue
        row = {
            "index": str(index),
            "node_key": achievement.name,
            "api_name": first_str(achievement, "name"),
            "english_name": first_str(display_name, "english"),
            "english_description": first_str(display_desc, "english"),
        }
        for language in languages:
            row[f"{language}_name"] = first_str(display_name, language)
            row[f"{language}_description"] = first_str(display_desc, language)
        rows.append(row)
    return rows


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_issue_form(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    chunks: list[str] = []
    for line in body.splitlines():
        if line.startswith("### "):
            if current is not None:
                fields[current] = "\n".join(chunks).strip()
            current = line.removeprefix("### ").strip()
            chunks = []
        elif current is not None:
            chunks.append(line)
    if current is not None:
        fields[current] = "\n".join(chunks).strip()
    return fields


def first_line(value: str) -> str:
    for line in value.splitlines():
        text = line.strip()
        if text and text != "_No response_":
            return text
    return ""


def field_value(fields: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name in fields:
            return fields[name]
    return ""


def parse_checked_languages(value: str) -> list[str]:
    languages: list[str] = []
    for line in value.splitlines():
        match = re.match(r"- \[[xX]\]\s*([a-z][a-z0-9_]*)\b", line.strip())
        if match:
            languages.append(match.group(1).lower())
    return languages


def parse_extra_languages(value: str) -> list[str]:
    text = first_line(value).lower()
    if not text or text in {"none", "n/a", "na", "no", "无"}:
        return []
    return [part.strip() for part in re.split(r"[,;\s，；]+", text) if part.strip()]


def parse_languages(checked: str, extra: str) -> list[str]:
    return sorted(set(parse_checked_languages(checked) + parse_extra_languages(extra)))


def extract_attachment(value: str) -> Attachment | None:
    matches = list(ATTACHMENT_RE.finditer(value))
    if len(matches) != 1:
        return None
    match = matches[0]
    url = match.group(2) or match.group("url")
    filename_from_url = not bool(match.group(1))
    filename = match.group(1) or Path(urllib.parse.urlparse(url).path).name
    return Attachment(filename=urllib.parse.unquote(filename.strip()), url=url, filename_from_url=filename_from_url)


def download_attachment(attachment: Attachment, token: str | None, destination: Path) -> None:
    request = urllib.request.Request(attachment.url, headers={"User-Agent": "steam-achievement-translation-library-bot"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=45) as response:
        total = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("uploaded file is larger than the 32 MiB review limit")
                handle.write(chunk)


def safe_archive_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for member in archive.infolist():
        normalized = member.filename.replace("\\", "/")
        if member.is_dir() or normalized.endswith("/"):
            continue
        parts = [part for part in normalized.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise ValueError("ZIP archive contains an unsafe file path")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValueError("ZIP archive contains an absolute file path")
        members.append(member)
    return members


def resolve_schema_upload(downloaded: Path, attachment: Attachment, game_id: str, output_dir: Path) -> Path:
    expected_name = f"UserGameStatsSchema_{game_id}.bin"
    expected_zip = f"UserGameStatsSchema_{game_id}.zip"
    if not attachment.filename_from_url and attachment.filename != expected_zip:
        raise ValueError(f"uploaded file must be {expected_zip}; got {attachment.filename}")
    if zipfile.is_zipfile(downloaded):
        with zipfile.ZipFile(downloaded) as archive:
            members = safe_archive_members(archive)
            if len(members) != 1:
                raise ValueError("ZIP upload must contain exactly one schema file")
            member = members[0]
            member_name = Path(member.filename.replace("\\", "/")).name
            if member_name != expected_name:
                raise ValueError(f"ZIP upload must contain {expected_name}; got {member_name}")
            if member.file_size > MAX_SCHEMA_BYTES:
                raise ValueError("schema file inside ZIP is larger than the 32 MiB review limit")
            output_path = output_dir / expected_name
            output_path.write_bytes(archive.read(member))
            return output_path
    raise ValueError(f"uploaded file must be a ZIP containing {expected_name}")


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


def write_index(index: dict[str, Any]) -> None:
    index.setdefault("version", 1)
    index.setdefault("description", "Community-submitted Steam achievement schema translations.")
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
    index["entries"] = [item for item in index.get("entries", []) if str(item.get("game_id")) != game_id] + [entry]
    write_index(index)
    write_human_index(index)


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def schema_download_url(schema_file: str) -> str:
    normalized = schema_file.replace("\\", "/").lstrip("/")
    encoded_path = urllib.parse.quote(normalized, safe="/")
    repo = os.environ.get("GITHUB_REPOSITORY", "GaBoron/steam-achievement-translation-library")
    return f"https://raw.githubusercontent.com/{repo}/main/{encoded_path}"


def github_link(url: str, label: str) -> str:
    return f"[{label}]({url})" if url else ""


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


def status_text(entry: dict[str, Any], language: str) -> str:
    if str(entry.get("status") or "current") == "outdated" or entry.get("outdated"):
        return "可能过期" if language == "zh" else "Possibly outdated"
    return "可用" if language == "zh" else "Current"


def write_human_index(index: dict[str, Any]) -> None:
    entries = sort_entries(index.get("entries", []))
    zh_lines = [
        "# Steam 成就翻译库索引",
        "",
        "简体中文 | [English](INDEX_EN.md) | [项目说明](README.md)",
        "",
        "> 下载前请同时查看“状态”和“最近更新”。Steam 更新可能改变成就 schema，标记为“可能过期”的文件建议等待更新 PR 合并后再使用。",
        "",
        "## 游戏列表",
        "",
    ]
    en_lines = [
        "# Steam Achievement Translation Index",
        "",
        "[简体中文](INDEX.md) | English | [Project README](README_EN.md)",
        "",
        "> Before downloading, check both Status and Last updated. Steam updates may change achievement schemas; files marked as possibly outdated should be used with extra care.",
        "",
        "## Games",
        "",
    ]
    if entries:
        zh_lines.extend([
            "| Steam app ID | 游戏 | 状态 | 最近更新 | 贡献者 | 语言 | 成就数 | 文件 | 原 PR | 过期报告 | 商店 |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ])
        en_lines.extend([
            "| Steam app ID | Game | Status | Last updated | Contributors | Languages | Achievements | File | Source PR | Outdated report | Store |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ])
        for entry in entries:
            game_id = str(entry.get("game_id", ""))
            schema_file = str(entry.get("schema_file", ""))
            schema_name = PurePosixPath(schema_file).name if schema_file else ""
            outdated = entry.get("outdated") if isinstance(entry.get("outdated"), dict) else {}
            source_pr = str(entry.get("source_pr") or "")
            outdated_link = str(outdated.get("source_pr") or outdated.get("source_issue") or "")
            row = (
                f"| `{game_id}` | {escape_table(str(entry.get('game_name', '')))} | {status_text(entry, 'zh')} | "
                f"{escape_table(str(entry.get('updated_at') or entry.get('submitted_at') or ''))} | {contributor_markdown(entry_contributors(entry))} | "
                f"{escape_table(', '.join(entry.get('languages', [])))} | {entry.get('achievement_count', '')} | "
                f"[`{escape_table(schema_name)}`]({schema_download_url(schema_file)}) | {github_link(source_pr, 'PR') if source_pr else ''} | "
                f"{github_link(outdated_link, '报告') if outdated_link else ''} | [Steam]({entry.get('store_url', '')}) |"
            )
            zh_lines.append(row)
            en_lines.append(
                f"| `{game_id}` | {escape_table(str(entry.get('game_name', '')))} | {status_text(entry, 'en')} | "
                f"{escape_table(str(entry.get('updated_at') or entry.get('submitted_at') or ''))} | {contributor_markdown(entry_contributors(entry))} | "
                f"{escape_table(', '.join(entry.get('languages', [])))} | {entry.get('achievement_count', '')} | "
                f"[`{escape_table(schema_name)}`]({schema_download_url(schema_file)}) | {github_link(source_pr, 'PR') if source_pr else ''} | "
                f"{github_link(outdated_link, 'Report') if outdated_link else ''} | [Steam]({entry.get('store_url', '')}) |"
            )
    else:
        zh_lines.append("暂无已收录游戏。")
        en_lines.append("No accepted games yet.")
    HUMAN_INDEX_PATH.write_text("\n".join(zh_lines) + "\n", encoding="utf-8")
    HUMAN_INDEX_EN_PATH.write_text("\n".join(en_lines) + "\n", encoding="utf-8")


def steam_store_id(url: str) -> str | None:
    match = re.search(r"store\.steampowered\.com/app/(\d+)(?:/|$)", url)
    return match.group(1) if match else None


def issue_labels(issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name") or "") for label in issue.get("labels", []) if isinstance(label, dict)}


def issue_kind(issue: dict[str, Any]) -> str:
    labels = issue_labels(issue)
    if "outdated" in labels:
        return "outdated"
    if "update" in labels:
        return "update"
    return "translation-contribution"


def issue_author(issue: dict[str, Any]) -> str:
    return str((issue.get("user") or {}).get("login") or "")


def language_coverage(rows: list[dict[str, str]], languages: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    coverage: dict[str, int] = {}
    missing: dict[str, list[str]] = {}
    for language in languages:
        present = [
            row for row in rows
            if row.get(f"{language}_name", "").strip() and row.get(f"{language}_description", "").strip()
        ]
        coverage[language] = len(present)
        missing[language] = [
            row.get("api_name", "")
            for row in rows
            if not row.get(f"{language}_name", "").strip() or not row.get(f"{language}_description", "").strip()
        ]
    return coverage, missing


def row_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("api_name", ""): row for row in rows if row.get("api_name", "")}


def summarize_update_diff(old_rows: list[dict[str, str]], new_rows: list[dict[str, str]], languages: list[str]) -> dict[str, Any]:
    old_by_id = row_map(old_rows)
    new_by_id = row_map(new_rows)
    old_ids = set(old_by_id)
    new_ids = set(new_by_id)
    compare_keys = ["english_name", "english_description"]
    for language in languages:
        compare_keys.extend([f"{language}_name", f"{language}_description"])
    changed: list[str] = []
    for achievement_id in sorted(old_ids & new_ids):
        if any(old_by_id[achievement_id].get(key, "") != new_by_id[achievement_id].get(key, "") for key in compare_keys):
            changed.append(achievement_id)
    return {
        "added": sorted(new_ids - old_ids),
        "deleted": sorted(old_ids - new_ids),
        "changed": changed,
    }


def markdown_list(values: list[str], empty_text: str = "None") -> str:
    if not values:
        return f"- {empty_text}"
    lines = [f"- `{value}`" for value in values[:100]]
    if len(values) > 100:
        lines.append(f"- ... and {len(values) - 100} more")
    return "\n".join(lines)


def build_review_table(rows: list[dict[str, str]], languages: list[str]) -> str:
    header = ["Achievement ID"]
    for language in languages:
        header.extend([f"{language} name", f"{language} description"])
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows:
        cells = [escape_table(row.get("api_name", ""))]
        for language in languages:
            cells.append(escape_table(row.get(f"{language}_name", "")))
            cells.append(escape_table(row.get(f"{language}_description", "")))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_failure(errors: list[str], retry_allowed: bool = False) -> None:
    result = {
        "ok": False,
        "errors": errors,
        "retry_allowed": retry_allowed,
        "close_issue": not retry_allowed,
    }
    Path("submission_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1)


def validate_common_fields(fields: dict[str, str], *, require_languages: bool) -> tuple[str, str, str, list[str], list[str]]:
    game_name = first_line(field_value(fields, ["Game name", "游戏名"]))
    game_id = first_line(field_value(fields, ["Steam app ID"]))
    store_url = first_line(field_value(fields, ["Steam store URL", "Steam 商店地址"]))
    languages = parse_languages(
        field_value(fields, ["Languages included in the uploaded file", "上传文件包含的语言"]),
        field_value(fields, ["Additional Steam language codes", "其他 Steam 语言代码"]),
    )
    errors: list[str] = []
    if not game_name:
        errors.append("Game name is required.")
    if not re.fullmatch(r"\d+", game_id):
        errors.append("Steam app ID must be numeric.")
    store_id = steam_store_id(store_url)
    if not store_id:
        errors.append("Steam store URL must be a store.steampowered.com/app/<id>/ URL.")
    elif game_id and store_id != game_id:
        errors.append(f"Steam store URL app ID {store_id} does not match submitted app ID {game_id}.")
    invalid_languages = [language for language in languages if not LANGUAGE_RE.fullmatch(language)]
    if require_languages and not languages:
        errors.append("Select or enter at least one Steam language code.")
    if invalid_languages:
        errors.append("Invalid Steam language code(s): " + ", ".join(invalid_languages))
    return game_name, game_id, store_url, languages, errors


def validate_schema_submission(
    attachment: Attachment,
    token: str | None,
    game_id: str,
    languages: list[str],
) -> tuple[bytes, list[Node], list[dict[str, str]], dict[str, int]]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        downloaded = tmp_dir / attachment.filename
        download_attachment(attachment, token, downloaded)
        schema_path = resolve_schema_upload(downloaded, attachment, game_id, tmp_dir)
        data, nodes = load_schema(schema_path)
        rebuilt = serialize(nodes)
        if data != rebuilt:
            raise ValueError("uploaded schema does not roundtrip byte-identically through the Binary KeyValues parser")
        rows = achievement_rows(nodes, languages)
        if not rows:
            raise ValueError("uploaded schema does not contain any Steam achievement display name/description records")
        achievement_ids = [row.get("api_name", "") for row in rows]
        if any(not achievement_id for achievement_id in achievement_ids):
            raise ValueError("every achievement must have a non-empty API name")
        if len(set(achievement_ids)) != len(achievement_ids):
            raise ValueError("achievement API names must be unique")
        coverage, missing = language_coverage(rows, languages)
        missing_messages: list[str] = []
        for language, missing_ids in missing.items():
            if missing_ids:
                preview = ", ".join(missing_ids[:10])
                suffix = " ..." if len(missing_ids) > 10 else ""
                missing_messages.append(f"{language}: {len(missing_ids)} missing achievement(s): {preview}{suffix}")
        if missing_messages:
            raise ValueError("uploaded schema has incomplete language coverage. " + "; ".join(missing_messages))
        return data, nodes, rows, coverage


def build_entry(
    existing: dict[str, Any] | None,
    *,
    game_name: str,
    game_id: str,
    store_url: str,
    languages: list[str],
    schema_file: str,
    achievement_count: int,
    schema_hash: str,
    source_issue: str,
    contributor: str,
    timestamp: str,
) -> dict[str, Any]:
    contributors = entry_contributors(existing or {})
    if contributor:
        contributors.append(contributor)
    entry = dict(existing or {})
    entry.update({
        "game_name": game_name,
        "game_id": game_id,
        "store_url": store_url,
        "languages": languages,
        "schema_file": schema_file,
        "achievement_count": achievement_count,
        "sha256": schema_hash,
        "source_issue": source_issue,
        "contributor_id": contributor,
        "contributors": sorted(set(contributors), key=str.casefold),
        "updated_at": timestamp,
        "status": "current",
    })
    entry.setdefault("submitted_at", timestamp)
    entry.pop("outdated", None)
    return entry


def build_submission_pr_body(
    *,
    kind: str,
    entry: dict[str, Any],
    coverage: dict[str, int],
    rows: list[dict[str, str]],
    languages: list[str],
    update_summary: str = "",
    update_diff: dict[str, Any] | None = None,
    previous_hash: str = "",
    issue_url: str = "",
) -> str:
    title = "Translation Library Update" if kind == "update" else "Translation Library Submission"
    coverage_lines = "\n".join(f"- `{language}`: {count}/{entry['achievement_count']} achievements" for language, count in coverage.items())
    update_section = ""
    if kind == "update" and update_diff is not None:
        update_section = f"""
## Update Check

- Contributor summary: {escape_table(update_summary)}
- Previous SHA-256: `{previous_hash}`
- New SHA-256: `{entry['sha256']}`
- Added achievements: {len(update_diff['added'])}
- Deleted achievements: {len(update_diff['deleted'])}
- Changed achievements: {len(update_diff['changed'])}

### Added

{markdown_list(update_diff['added'])}

### Deleted

{markdown_list(update_diff['deleted'])}

### Changed

{markdown_list(update_diff['changed'])}
"""
    return f"""## {title}

- Game name: {entry['game_name']}
- Steam app ID: `{entry['game_id']}`
- Steam store URL: {entry['store_url']}
- Contributors: {', '.join('@' + contributor for contributor in entry_contributors(entry)) or 'unknown'}
- Source issue: {issue_url}
- Supported languages: {', '.join(languages)}
- Achievement count: {entry['achievement_count']}
- Schema file: `{entry['schema_file']}`
- SHA-256: `{entry['sha256']}`
- Submitted at: {entry.get('submitted_at', '')}
- Updated at: {entry.get('updated_at', '')}

## Language Coverage

{coverage_lines}
{update_section}

## Achievement Text

{build_review_table(rows, languages)}
"""


def validate_translation_or_update(event: dict[str, Any], token: str | None, kind: str) -> dict[str, Any]:
    issue = event["issue"]
    fields = parse_issue_form(issue.get("body") or "")
    game_name, game_id, store_url, languages, errors = validate_common_fields(fields, require_languages=True)
    attachment = extract_attachment(field_value(fields, ["Achievement schema ZIP", "成就 schema ZIP"]))
    update_summary = first_line(field_value(fields, ["Update summary", "更新内容摘要"]))
    index = load_index()
    existing = existing_entry(index, game_id) if game_id else None

    if kind == "translation-contribution" and existing:
        errors.append(f"Steam app ID {game_id} already exists in index.json. Use the update template if you want to replace an existing file.")
    if kind == "update" and not existing:
        errors.append(f"Steam app ID {game_id} does not exist in index.json. Open pull requests do not count as accepted library entries.")
    if kind == "update" and not update_summary:
        errors.append("Update summary is required.")
    if not attachment:
        errors.append("Attach exactly one UserGameStatsSchema_<app_id>.zip file.")
    if errors:
        write_failure(errors, retry_allowed=True)

    assert attachment is not None
    try:
        data, nodes, rows, coverage = validate_schema_submission(attachment, token, game_id, languages)
    except Exception as exc:  # noqa: BLE001 - this becomes a user-facing review message.
        write_failure([f"Could not validate uploaded schema: {exc}."], retry_allowed=True)

    previous_hash = ""
    update_diff: dict[str, Any] | None = None
    if kind == "update":
        assert existing is not None
        old_schema = REPO_ROOT / str(existing.get("schema_file") or "")
        if not old_schema.is_file():
            write_failure([f"Existing schema file is missing from the repository: {existing.get('schema_file')}."], retry_allowed=False)
        old_data, old_nodes = load_schema(old_schema)
        previous_hash = sha256(old_data)
        if old_data == data:
            write_failure(["Uploaded schema is byte-identical to the current library file; no update PR was created."], retry_allowed=True)
        diff_languages = sorted(set(languages + list(existing.get("languages", []))))
        old_rows = achievement_rows(old_nodes, diff_languages)
        new_rows = achievement_rows(nodes, diff_languages)
        update_diff = summarize_update_diff(old_rows, new_rows, diff_languages)

    target_dir = FILES_ROOT / game_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"UserGameStatsSchema_{game_id}.bin"
    target_file.write_bytes(data)

    timestamp = now_utc()
    entry = build_entry(
        existing,
        game_name=game_name,
        game_id=game_id,
        store_url=store_url,
        languages=languages,
        schema_file=str(target_file.relative_to(REPO_ROOT)).replace("\\", "/"),
        achievement_count=len(rows),
        schema_hash=sha256(data),
        source_issue=issue.get("html_url", ""),
        contributor=issue_author(issue),
        timestamp=timestamp,
    )
    upsert_index_entry(entry)

    issue_number = int(issue["number"])
    branch_prefix = "translation-library/update" if kind == "update" else "translation-library/issue"
    title_prefix = "Update" if kind == "update" else "Add"
    result = {
        "ok": True,
        "kind": kind,
        "branch": f"{branch_prefix}-{issue_number}",
        "pr_title": f"{title_prefix} achievement translations for {game_name} ({game_id})",
        "pr_labels": "translation-contribution,update" if kind == "update" else "translation-contribution",
        "commit_message": f"data: {'update' if kind == 'update' else 'add'} achievement translations from issue #{issue_number}",
        "game_id": game_id,
        "game_name": game_name,
    }
    Path("submission_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("pr_title.txt").write_text(result["pr_title"] + "\n", encoding="utf-8")
    Path("pr_body.md").write_text(
        build_submission_pr_body(
            kind=kind,
            entry=entry,
            coverage=coverage,
            rows=rows,
            languages=languages,
            update_summary=update_summary,
            update_diff=update_diff,
            previous_hash=previous_hash,
            issue_url=issue.get("html_url", ""),
        ),
        encoding="utf-8",
    )
    return result


def validate_outdated_report(event: dict[str, Any]) -> dict[str, Any]:
    issue = event["issue"]
    fields = parse_issue_form(issue.get("body") or "")
    game_name, game_id, store_url, _languages, errors = validate_common_fields(fields, require_languages=False)
    reason = field_value(fields, ["Why do you think the file is outdated?", "过期说明"]).strip()
    source = first_line(field_value(fields, ["Reference or source", "参考来源"]))
    index = load_index()
    existing = existing_entry(index, game_id) if game_id else None
    if not existing:
        errors.append(f"Steam app ID {game_id} does not exist in index.json, so it cannot be marked outdated.")
    if not reason or reason == "_No response_":
        errors.append("Outdated reason is required.")
    if errors:
        write_failure(errors, retry_allowed=True)

    assert existing is not None
    timestamp = now_utc()
    entry = dict(existing)
    entry["game_name"] = game_name or existing.get("game_name", "")
    entry["store_url"] = store_url or existing.get("store_url", "")
    entry["status"] = "outdated"
    entry["outdated"] = {
        "reported_at": timestamp,
        "source_issue": issue.get("html_url", ""),
        "source_pr": None,
        "reporter_id": issue_author(issue),
        "reason": reason,
        "reference": source,
    }
    upsert_index_entry(entry)

    issue_number = int(issue["number"])
    result = {
        "ok": True,
        "kind": "outdated",
        "branch": f"translation-library/outdated-{issue_number}",
        "pr_title": f"Mark achievement translations for {entry['game_name']} ({game_id}) as outdated",
        "pr_labels": "outdated",
        "commit_message": f"data: mark achievement translation outdated from issue #{issue_number}",
        "game_id": game_id,
        "game_name": entry["game_name"],
    }
    Path("submission_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("pr_title.txt").write_text(result["pr_title"] + "\n", encoding="utf-8")
    Path("pr_body.md").write_text(
        f"""## Outdated Translation Report

- Game name: {entry['game_name']}
- Steam app ID: `{game_id}`
- Steam store URL: {entry.get('store_url', '')}
- Current schema file: `{entry.get('schema_file', '')}`
- Current SHA-256: `{entry.get('sha256', '')}`
- Last library update: {entry.get('updated_at', '')}
- Source issue: {issue.get('html_url', '')}
- Reporter: @{issue_author(issue)}
- Reported at: {timestamp}

## Reason

{reason}

## Reference

{source or 'No external reference provided.'}
""",
        encoding="utf-8",
    )
    return result


def validate_and_update(event: dict[str, Any], token: str | None) -> dict[str, Any]:
    issue = event["issue"]
    kind = issue_kind(issue)
    if kind == "outdated":
        return validate_outdated_report(event)
    return validate_translation_or_update(event, token, kind)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a translation library issue and prepare a PR.")
    parser.add_argument("--event", type=Path, required=True, help="GitHub event JSON path")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token for attachment downloads")
    args = parser.parse_args()
    validate_and_update(json.loads(args.event.read_text(encoding="utf-8")), args.token)


if __name__ == "__main__":
    main()
