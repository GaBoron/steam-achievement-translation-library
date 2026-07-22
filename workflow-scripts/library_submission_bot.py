#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
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
PENDING_REPORTS_DIR = Path(".github") / "translation-reports"

NEW_LABEL = "翻译投稿"
UPDATE_LABEL = "更新文件"
OUTDATED_LABEL = "报告错误"
LEGACY_NEW_LABEL = "translation-contribution"
LEGACY_UPDATE_LABEL = "update"
LEGACY_OUTDATED_LABELS = {"报告过期", "outdated"}

MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SCHEMA_VARIANTS = 16
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
STATE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
VARIANT_MANIFEST_NAME = "translation-variants.json"
ATTACHMENT_RE = re.compile(
    r"\[([^\]]+)\]\((https://github\.com/user-attachments/[^\s)]+)\)|(?<!\()(?P<url>https://github\.com/user-attachments/[^\s)]+)"
)
TYPE_NAMES = {0: "BEGIN", 1: "STRING", 2: "INT32", 3: "FLOAT32", 4: "POINTER", 5: "WIDESTRING", 6: "COLOR", 7: "UINT64", 8: "END"}
PR_GAME_ID_RE = re.compile(r"(?mi)^-\s*Steam app ID:\s*`?(\d+)`?\s*$")


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


@dataclass
class ResolvedSchemaVariant:
    variant_id: str
    path: Path
    primary: bool
    note_zh: str = ""
    note_en: str = ""


@dataclass
class ValidatedSchemaVariant:
    variant_id: str
    primary: bool
    note_zh: str
    note_en: str
    data: bytes
    nodes: list[Node]
    rows: list[dict[str, str]]
    coverage: dict[str, int]


@dataclass
class ValidatedSchemaPackage:
    variants: list[ValidatedSchemaVariant]
    has_manifest: bool


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


def validate_schema_structure(data: bytes, nodes: list[Node]) -> list[dict[str, str]]:
    """Validate invariants that every accepted schema must preserve."""
    if data != serialize(nodes):
        raise ValueError("schema 无法通过 Binary KeyValues 解析器保持字节级 roundtrip")
    rows = achievement_rows(nodes, [])
    if not rows:
        raise ValueError("schema 中没有找到 Steam 成就名称/描述记录")
    achievement_ids = [row.get("api_name", "") for row in rows]
    if any(not achievement_id for achievement_id in achievement_ids):
        raise ValueError("每个成就都必须有非空的 API name")
    if len(set(achievement_ids)) != len(achievement_ids):
        raise ValueError("成就 API name 必须唯一")
    return rows


def require_language_coverage(
    rows: list[dict[str, str]],
    languages: list[str],
) -> dict[str, int]:
    coverage, missing = language_coverage(rows, languages)
    missing_messages: list[str] = []
    for language, missing_ids in missing.items():
        if missing_ids:
            preview = ", ".join(missing_ids[:10])
            suffix = " ..." if len(missing_ids) > 10 else ""
            missing_messages.append(f"{language}: 缺少 {len(missing_ids)} 个成就文本：{preview}{suffix}")
    if missing_messages:
        raise ValueError("schema 语言覆盖不完整。" + "；".join(missing_messages))
    return coverage


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


def optional_field_value(fields: dict[str, str], names: list[str]) -> str:
    value = field_value(fields, names).strip()
    return "" if value == "_No response_" else value


def parse_comma_language_list(value: str) -> list[str]:
    text = first_line(value).lower()
    if not text or text in {"none", "n/a", "na", "no", "无"}:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_checked_languages(value: str) -> list[str]:
    languages: list[str] = []
    for line in value.splitlines():
        match = re.match(r"- \[[xX]\]\s*([a-z][a-z0-9_]*)\b", line.strip())
        if match:
            languages.append(match.group(1).lower())
    if not languages:
        languages.extend(parse_comma_language_list(value))
    return languages


def parse_extra_languages(value: str) -> list[str]:
    return parse_comma_language_list(value)


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
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("上传文件超过 32 MiB 检查上限")
        total = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("上传文件超过 32 MiB 检查上限")
                handle.write(chunk)


def github_api_get(repo: str, token: str, path: str) -> Any:
    if not token:
        raise RuntimeError("缺少 GitHub token")
    encoded_repo = urllib.parse.quote(repo, safe="/")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{encoded_repo}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "steam-achievement-translation-library-bot",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pull_request_game_id(pull_request: dict[str, Any]) -> str:
    match = PR_GAME_ID_RE.search(str(pull_request.get("body") or ""))
    return match.group(1) if match else ""


def find_open_translation_pr(repo: str, token: str, game_id: str) -> dict[str, Any] | None:
    for page in range(1, 11):
        pulls = github_api_get(repo, token, f"/pulls?state=open&base=main&per_page=100&page={page}")
        if not isinstance(pulls, list):
            raise RuntimeError("GitHub open PR API 返回了无效数据")
        for pull_request in pulls:
            if not isinstance(pull_request, dict):
                continue
            head = pull_request.get("head") if isinstance(pull_request.get("head"), dict) else {}
            if not str(head.get("ref") or "").startswith("translation-library/"):
                continue
            if pull_request_game_id(pull_request) == game_id:
                return pull_request
        if len(pulls) < 100:
            return None
    raise RuntimeError("open PR 数量超过自动检查上限")


def safe_archive_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for member in archive.infolist():
        normalized = member.filename.replace("\\", "/")
        if member.is_dir() or normalized.endswith("/"):
            continue
        parts = [part for part in normalized.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise ValueError("ZIP 内包含不安全的文件路径")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValueError("ZIP 内包含绝对路径")
        members.append(member)
    return members


def clean_variant_note(value: Any, field_name: str) -> str:
    note = str(value or "").strip()
    if not note:
        raise ValueError(f"多版本清单中的 {field_name} 不能为空")
    if len(note) > 120:
        raise ValueError(f"多版本清单中的 {field_name} 不能超过 120 个字符")
    if any(ord(character) < 32 for character in note):
        raise ValueError(f"多版本清单中的 {field_name} 必须是单行文本")
    return note


def resolve_schema_package(
    downloaded: Path,
    attachment: Attachment,
    game_id: str,
    output_dir: Path,
) -> tuple[list[ResolvedSchemaVariant], bool]:
    expected_name = f"UserGameStatsSchema_{game_id}.bin"
    expected_zip = f"UserGameStatsSchema_{game_id}.zip"
    if not attachment.filename_from_url and attachment.filename != expected_zip:
        raise ValueError(f"上传文件名必须是 {expected_zip}，当前是 {attachment.filename}")
    if not zipfile.is_zipfile(downloaded):
        raise ValueError(f"上传文件必须是包含 {expected_name} 的 ZIP")

    with zipfile.ZipFile(downloaded) as archive:
        members = safe_archive_members(archive)
        members_by_name = {member.filename.replace("\\", "/"): member for member in members}
        if len(members_by_name) != len(members):
            raise ValueError("ZIP 内包含重复文件路径")
        manifest_member = members_by_name.get(VARIANT_MANIFEST_NAME)
        if manifest_member is None:
            if len(members) != 1:
                raise ValueError(
                    f"单版本 ZIP 内必须且只能包含一个 schema；多版本 ZIP 必须包含 {VARIANT_MANIFEST_NAME}"
                )
            member = members[0]
            member_name = member.filename.replace("\\", "/")
            if member_name != expected_name:
                raise ValueError(f"ZIP 内必须包含 {expected_name}，当前是 {member_name}")
            if member.file_size > MAX_SCHEMA_BYTES:
                raise ValueError("ZIP 内的 schema 文件超过 32 MiB 检查上限")
            output_path = output_dir / expected_name
            output_path.write_bytes(archive.read(member))
            return [ResolvedSchemaVariant("default", output_path, True)], False

        if manifest_member.file_size > MAX_MANIFEST_BYTES:
            raise ValueError(f"{VARIANT_MANIFEST_NAME} 超过 64 KiB 上限")
        try:
            manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{VARIANT_MANIFEST_NAME} 不是有效的 UTF-8 JSON：{exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("version") != 1:
            raise ValueError(f"{VARIANT_MANIFEST_NAME} 必须是 version=1 的 JSON 对象")
        raw_variants = manifest.get("variants")
        if not isinstance(raw_variants, list) or not 1 <= len(raw_variants) <= MAX_SCHEMA_VARIANTS:
            raise ValueError(f"版本清单必须包含 1 到 {MAX_SCHEMA_VARIANTS} 个 variants")

        resolved: list[ResolvedSchemaVariant] = []
        declared_files: set[str] = set()
        seen_ids: set[str] = set()
        primary_count = 0
        total_schema_bytes = 0
        for index, raw_variant in enumerate(raw_variants, 1):
            if not isinstance(raw_variant, dict):
                raise ValueError(f"variants[{index}] 必须是 JSON 对象")
            variant_id = str(raw_variant.get("variant_id") or "").strip().lower()
            if not VARIANT_ID_RE.fullmatch(variant_id):
                raise ValueError(f"无效的 variant_id：{variant_id or '<empty>'}")
            if variant_id in seen_ids:
                raise ValueError(f"重复的 variant_id：{variant_id}")
            seen_ids.add(variant_id)
            primary = raw_variant.get("primary") is True
            primary_count += int(primary)
            if primary and variant_id != "default":
                raise ValueError("主版本的 variant_id 必须是 default")
            if not primary and variant_id == "default":
                raise ValueError("variant_id=default 只能用于主版本")
            expected_file = expected_name if primary else f"{variant_id}/{expected_name}"
            schema_file = str(raw_variant.get("file") or "").strip().replace("\\", "/")
            if schema_file != expected_file:
                raise ValueError(f"版本 {variant_id} 的 file 必须是 {expected_file}")
            member = members_by_name.get(schema_file)
            if member is None:
                raise ValueError(f"ZIP 缺少清单声明的文件：{schema_file}")
            if member.file_size > MAX_SCHEMA_BYTES:
                raise ValueError(f"版本 {variant_id} 的 schema 超过 32 MiB 检查上限")
            total_schema_bytes += member.file_size
            if total_schema_bytes > MAX_PACKAGE_BYTES:
                raise ValueError("多版本 schema 解压后总大小超过 64 MiB 检查上限")
            declared_files.add(schema_file)
            destination = output_dir / Path(*PurePosixPath(schema_file).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
            resolved.append(ResolvedSchemaVariant(
                variant_id=variant_id,
                path=destination,
                primary=primary,
                note_zh=clean_variant_note(raw_variant.get("note_zh"), f"variants[{index}].note_zh"),
                note_en=clean_variant_note(raw_variant.get("note_en"), f"variants[{index}].note_en"),
            ))
        if primary_count != 1:
            raise ValueError("多版本清单必须且只能声明一个 primary=true 的主版本")
        extra_files = set(members_by_name) - declared_files - {VARIANT_MANIFEST_NAME}
        if extra_files:
            raise ValueError("ZIP 包含清单未声明的文件：" + ", ".join(sorted(extra_files)))
        resolved.sort(key=lambda variant: (not variant.primary, variant.variant_id))
        return resolved, True


def resolve_schema_upload(downloaded: Path, attachment: Attachment, game_id: str, output_dir: Path) -> Path:
    variants, has_manifest = resolve_schema_package(downloaded, attachment, game_id, output_dir)
    if has_manifest or len(variants) != 1:
        raise ValueError("此操作只接受单版本 ZIP")
    return variants[0].path


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


def validated_variant_record(game_id: str, variant: ValidatedSchemaVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "primary": variant.primary,
        "schema_file": schema_variant_relative_path(game_id, variant.variant_id, variant.primary),
        "note_zh": variant.note_zh,
        "note_en": variant.note_en,
        "file_size_bytes": len(variant.data),
        "sha256": sha256(variant.data),
        "achievement_count": len(variant.rows),
    }


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _remove_obsolete_variant_files(existing_records: list[dict[str, Any]], keep_files: set[str], game_id: str) -> None:
    game_root = (FILES_ROOT / game_id).resolve()
    for record in existing_records:
        schema_file = str(record.get("schema_file") or "")
        if not schema_file or schema_file in keep_files:
            continue
        path = repository_path(schema_file)
        try:
            path.relative_to(game_root)
        except ValueError as exc:
            raise ValueError(f"版本文件不在 files/{game_id}/ 范围内：{schema_file}") from exc
        if path.is_file():
            path.unlink()
        parent = path.parent
        while parent != game_root and parent.is_relative_to(game_root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def save_schema_package(
    package: ValidatedSchemaPackage,
    game_id: str,
    existing_entry: dict[str, Any] | None = None,
    *,
    target_variant_id: str = "",
) -> tuple[list[ValidatedSchemaVariant], list[dict[str, Any]]]:
    existing_records = entry_schema_variants(existing_entry or {})
    if target_variant_id:
        if len(existing_records) < 2:
            raise ValueError("只有已包含多个版本的游戏才能指定 variant_id 进行单独更新")
        if package.has_manifest or len(package.variants) != 1:
            raise ValueError("指定 variant_id 时只能上传不含多版本清单的单版本 ZIP")
        existing_by_id = {str(record["variant_id"]): record for record in existing_records}
        current = existing_by_id.get(target_variant_id)
        if current is None:
            raise ValueError(f"找不到 variant_id={target_variant_id}；新增版本请提交完整多版本包")
        uploaded = package.variants[0]
        effective = ValidatedSchemaVariant(
            variant_id=target_variant_id,
            primary=bool(current.get("primary")),
            note_zh=str(current.get("note_zh") or ""),
            note_en=str(current.get("note_en") or ""),
            data=uploaded.data,
            nodes=uploaded.nodes,
            rows=uploaded.rows,
            coverage=uploaded.coverage,
        )
        record = validated_variant_record(game_id, effective)
        existing_by_id[target_variant_id] = record
        records = list(existing_by_id.values())
        records.sort(key=lambda variant: (not bool(variant.get("primary")), str(variant.get("variant_id"))))
        path = repository_path(record["schema_file"])
        _write_bytes_atomic(path, effective.data)
        return [effective], records

    if not package.has_manifest and len(existing_records) > 1:
        raise ValueError(
            "该游戏包含多个版本；请上传带 translation-variants.json 的完整多版本包，"
            "或在“要更新的版本 ID”中指定一个 variant_id"
        )
    effective_variants = package.variants
    records = [validated_variant_record(game_id, variant) for variant in effective_variants]
    keep_files = {str(record["schema_file"]) for record in records}
    for variant, record in zip(effective_variants, records, strict=True):
        _write_bytes_atomic(repository_path(str(record["schema_file"])), variant.data)
    _remove_obsolete_variant_files(existing_records, keep_files, game_id)
    return effective_variants, records


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


def steam_store_id(url: str) -> str | None:
    match = re.search(r"store\.steampowered\.com/app/(\d+)(?:/|$)", url)
    return match.group(1) if match else None


def issue_labels(issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name") or "") for label in issue.get("labels", []) if isinstance(label, dict)}


def issue_kind(issue: dict[str, Any]) -> str:
    labels = issue_labels(issue)
    if OUTDATED_LABEL in labels or labels & LEGACY_OUTDATED_LABELS:
        return "outdated"
    if UPDATE_LABEL in labels or LEGACY_UPDATE_LABEL in labels:
        return "update"
    text = f"{issue.get('title') or ''}\n{issue.get('body') or ''}"
    if any(heading in text for heading in ("### 错误类型", "### Issue type", "### 错误说明", "### Issue details", "### 过期说明", "### Why do you think the file is outdated?")):
        return "outdated"
    if "### 更新内容摘要" in text or "### Update summary" in text:
        return "update"
    return "translation-contribution"


def issue_author(issue: dict[str, Any]) -> str:
    return str((issue.get("user") or {}).get("login") or "")


def language_coverage(rows: list[dict[str, str]], languages: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    coverage: dict[str, int] = {}
    missing: dict[str, list[str]] = {}
    for language in languages:
        def is_complete(row: dict[str, str]) -> bool:
            name_present = bool(row.get(f"{language}_name", "").strip())
            description_present = bool(row.get(f"{language}_description", "").strip())
            # Steam may intentionally leave the original English description empty.
            return name_present and (description_present or language == "english")

        present = [
            row for row in rows
            if is_complete(row)
        ]
        coverage[language] = len(present)
        missing[language] = [
            row.get("api_name", "")
            for row in rows
            if not is_complete(row)
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
    changed: list[dict[str, Any]] = []
    for achievement_id in sorted(old_ids & new_ids):
        field_changes = []
        for key in compare_keys:
            old_value = old_by_id[achievement_id].get(key, "")
            new_value = new_by_id[achievement_id].get(key, "")
            if old_value != new_value:
                field_changes.append({
                    "field": key,
                    "old": old_value,
                    "new": new_value,
                })
        if field_changes:
            changed.append({"id": achievement_id, "fields": field_changes})
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


def markdown_changed_details(values: list[Any], empty_text: str = "None") -> str:
    if not values:
        return f"- {empty_text}"
    if all(isinstance(value, str) for value in values):
        return markdown_list(values, empty_text)

    lines = [
        "| Achievement ID | Field | Before | After |",
        "| --- | --- | --- | --- |",
    ]
    rendered = 0
    for item in values:
        if not isinstance(item, dict):
            continue
        achievement_id = escape_table(str(item.get("id") or ""))
        fields = item.get("fields") if isinstance(item.get("fields"), list) else []
        for field in fields:
            if not isinstance(field, dict):
                continue
            lines.append(
                f"| `{achievement_id}` | `{escape_table(str(field.get('field') or ''))}` | "
                f"{escape_table(str(field.get('old') or ''))} | {escape_table(str(field.get('new') or ''))} |"
            )
            rendered += 1
            if rendered >= 100:
                lines.append("| ... | ... | ... | ... |")
                return "\n".join(lines)
    return "\n".join(lines) if rendered else f"- {empty_text}"


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
    language_field = field_value(fields, ["Languages included in the uploaded file", "上传文件包含的语言"])
    extra_language_field = field_value(fields, ["Additional Steam language codes", "其他 Steam 语言代码"])
    languages = parse_languages(
        language_field,
        extra_language_field,
    )
    errors: list[str] = []
    if not game_name:
        errors.append("必须填写游戏名。")
    if not re.fullmatch(r"\d+", game_id):
        errors.append("Steam app ID 必须只包含数字。")
    store_id = steam_store_id(store_url)
    if not store_id:
        errors.append("Steam 商店地址必须是 store.steampowered.com/app/<id>/ 格式。")
    elif game_id and store_id != game_id:
        errors.append(f"Steam 商店地址中的 app ID {store_id} 与填写的 app ID {game_id} 不一致。")
    language_text = "\n".join([language_field, extra_language_field]).lower()
    if any(separator in language_text for separator in [";", "；", "，"]):
        errors.append("语言代码必须使用半角逗号 `,` 分隔；请写出文件中实际存在的全部语言。")
    invalid_languages = [language for language in languages if not LANGUAGE_RE.fullmatch(language)]
    if require_languages and not languages:
        errors.append("至少填写一个 Steam 语言代码。")
    if invalid_languages:
        errors.append("无效的 Steam 语言代码：" + ", ".join(invalid_languages))
    return game_name, game_id, store_url, languages, errors


def validate_schema_package(
    attachment: Attachment,
    token: str | None,
    game_id: str,
    languages: list[str],
) -> ValidatedSchemaPackage:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        # The Markdown label is untrusted user input; never use it as a path.
        downloaded = tmp_dir / "attachment.zip"
        download_attachment(attachment, token, downloaded)
        resolved_variants, has_manifest = resolve_schema_package(downloaded, attachment, game_id, tmp_dir)
        variants: list[ValidatedSchemaVariant] = []
        for resolved in resolved_variants:
            data, nodes = load_schema(resolved.path)
            validate_schema_structure(data, nodes)
            rows = achievement_rows(nodes, languages)
            coverage = require_language_coverage(rows, languages)
            variants.append(ValidatedSchemaVariant(
                variant_id=resolved.variant_id,
                primary=resolved.primary,
                note_zh=resolved.note_zh,
                note_en=resolved.note_en,
                data=data,
                nodes=nodes,
                rows=rows,
                coverage=coverage,
            ))
        hashes: dict[str, str] = {}
        for variant in variants:
            digest = sha256(variant.data)
            previous_id = hashes.get(digest)
            if previous_id is not None:
                raise ValueError(f"版本 {variant.variant_id} 与 {previous_id} 的文件内容完全相同")
            hashes[digest] = variant.variant_id
        return ValidatedSchemaPackage(variants=variants, has_manifest=has_manifest)


def validate_schema_submission(
    attachment: Attachment,
    token: str | None,
    game_id: str,
    languages: list[str],
) -> tuple[bytes, list[Node], list[dict[str, str]], dict[str, int]]:
    """Compatibility wrapper for call sites that intentionally accept one schema only."""
    package = validate_schema_package(attachment, token, game_id, languages)
    if package.has_manifest or len(package.variants) != 1:
        raise ValueError("此操作只接受单版本 ZIP")
    variant = package.variants[0]
    return variant.data, variant.nodes, variant.rows, variant.coverage


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
    schema_files: list[dict[str, Any]] | None = None,
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
        "file_size_bytes": schema_file_size_bytes(schema_file),
        "achievement_count": achievement_count,
        "sha256": schema_hash,
        "source_issue": source_issue,
        "contributor_id": contributor,
        "contributors": sorted(set(contributors), key=str.casefold),
        "updated_at": timestamp,
        "status": "current",
    })
    entry.setdefault("submitted_at", timestamp)
    if schema_files is not None:
        entry["schema_files"] = schema_files
    entry.pop("outdated", None)
    entry.pop("report", None)
    return entry


def schema_variants_marker(schema_files: list[dict[str, Any]]) -> str:
    payload = json.dumps(schema_files, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii")
    return f"<!-- translation-library-schema-variants:{encoded} -->"


def parse_schema_variants_marker(body: str) -> list[dict[str, Any]] | None:
    match = re.search(r"<!-- translation-library-schema-variants:([A-Za-z0-9_=-]+) -->", body)
    if not match:
        return None
    try:
        decoded = base64.urlsafe_b64decode(match.group(1).encode("ascii"))
        value = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"PR 中的 schema 版本元数据无效：{exc}") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("PR 中的 schema 版本元数据必须是对象数组")
    return value


def build_schema_variants_section(entry: dict[str, Any]) -> str:
    raw_variants = entry.get("schema_files")
    if not isinstance(raw_variants, list) or not raw_variants:
        return ""
    variants = validated_entry_schema_variants(entry, require_metadata=True)
    lines = [
        "## Schema Variants",
        "",
        "| Variant ID | Role | Chinese note | English note | Achievements | Size | SHA-256 | File |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for variant in variants:
        role = "Primary" if variant.get("primary") else "Variant"
        size = schema_file_size_label(int(variant.get("file_size_bytes") or 0))
        lines.append(
            f"| `{variant.get('variant_id', '')}` | {role} | {escape_table(str(variant.get('note_zh') or ''))} | "
            f"{escape_table(str(variant.get('note_en') or ''))} | {variant.get('achievement_count', '')} | {size} | "
            f"`{variant.get('sha256', '')}` | `{variant.get('schema_file', '')}` |"
        )
    lines.extend(["", schema_variants_marker(variants)])
    return "\n".join(lines)


def variant_achievement_rows(
    entry: dict[str, Any],
    languages: list[str],
) -> dict[str, list[dict[str, str]]]:
    rows_by_variant: dict[str, list[dict[str, str]]] = {}
    for variant in validated_entry_schema_variants(entry):
        schema_file = str(variant["schema_file"])
        data, nodes = load_schema(repository_path(schema_file))
        validate_schema_structure(data, nodes)
        rows = achievement_rows(nodes, languages)
        require_language_coverage(rows, languages)
        rows_by_variant[str(variant["variant_id"])] = rows
    return rows_by_variant


def build_achievement_text_sections(
    rows: list[dict[str, str]],
    languages: list[str],
    review_variant_id: str,
    rows_by_variant: dict[str, list[dict[str, str]]] | None = None,
) -> str:
    variants = rows_by_variant or {review_variant_id: rows}
    return "\n\n".join(
        f"## Achievement Text (`{variant_id}`)\n\n{build_review_table(variant_rows, languages)}"
        for variant_id, variant_rows in variants.items()
    )


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
    contributor_notes: str = "",
    review_variant_id: str = "default",
    review_variant_hash: str = "",
    variant_changes: dict[str, list[str]] | None = None,
    rows_by_variant: dict[str, list[dict[str, str]]] | None = None,
) -> str:
    title = "Translation Library Update" if kind == "update" else "Translation Library Submission"
    coverage_lines = "\n".join(f"- `{language}`: {count}/{len(rows)} achievements" for language, count in coverage.items())
    file_size = entry_file_size_label(entry)
    variants_section = build_schema_variants_section(entry)
    notes_section = ""
    if contributor_notes:
        notes_section = f"""
## Contributor Notes

{contributor_notes}
"""
    update_section = ""
    if kind == "update" and (update_diff is not None or variant_changes is not None):
        variant_changes = variant_changes or {"added": [], "removed": [], "changed": [review_variant_id]}
        update_diff = update_diff or {"added": [], "deleted": [], "changed": []}
        update_section = f"""
## Update Check

- Contributor summary: {escape_table(update_summary)}
- Reviewed variant: `{review_variant_id}`
- Previous SHA-256: `{previous_hash}`
- New SHA-256: `{review_variant_hash or entry['sha256']}`
- Added variants: {', '.join(f'`{item}`' for item in variant_changes['added']) or 'None'}
- Removed variants: {', '.join(f'`{item}`' for item in variant_changes['removed']) or 'None'}
- Changed variants: {', '.join(f'`{item}`' for item in variant_changes['changed']) or 'None'}
- Added achievements: {len(update_diff['added'])}
- Deleted achievements: {len(update_diff['deleted'])}
- Changed achievements: {len(update_diff['changed'])}

### Added

{markdown_list(update_diff['added'])}

### Deleted

{markdown_list(update_diff['deleted'])}

### Changed

{markdown_changed_details(update_diff['changed'])}
"""
    achievement_sections = build_achievement_text_sections(
        rows,
        languages,
        review_variant_id,
        rows_by_variant,
    )
    return f"""## {title}

- Game name: {entry['game_name']}
- Steam app ID: `{entry['game_id']}`
- Steam store URL: {entry['store_url']}
- Contributors: {', '.join('@' + contributor for contributor in entry_contributors(entry)) or 'unknown'}
- Source issue: {issue_url}
- Supported languages: {', '.join(languages)}
- Achievement count: {entry['achievement_count']}
- Schema file: `{entry['schema_file']}`
- File size: {file_size}
- SHA-256: `{entry['sha256']}`
- Submitted at: {entry.get('submitted_at', '')}
- Updated at: {entry.get('updated_at', '')}

{variants_section}
{notes_section}

## Language Coverage

{coverage_lines}
{update_section}

{achievement_sections}
"""


def validate_translation_or_update(event: dict[str, Any], token: str | None, kind: str) -> dict[str, Any]:
    issue = event["issue"]
    fields = parse_issue_form(issue.get("body") or "")
    game_name, game_id, store_url, languages, errors = validate_common_fields(fields, require_languages=True)
    attachment = extract_attachment(field_value(fields, ["Achievement schema ZIP", "成就 schema ZIP"]))
    update_summary = first_line(field_value(fields, ["Update summary", "更新内容摘要"]))
    target_variant_id = first_line(field_value(fields, ["Version ID to update", "要更新的版本 ID"])).lower()
    contributor_notes = optional_field_value(fields, ["Notes", "备注"])
    index = load_index()
    existing = existing_entry(index, game_id) if game_id else None

    if kind == "translation-contribution" and existing:
        write_failure(
            [f"Steam app ID {game_id} 已经存在于 index.json；如需替换已收录文件，请使用“更新已有 Steam 成就翻译”模板。"],
            retry_allowed=False,
        )
    if kind == "translation-contribution" and game_id and re.fullmatch(r"\d+", game_id):
        repository = event.get("repository") if isinstance(event.get("repository"), dict) else {}
        repo = str(repository.get("full_name") or os.environ.get("GITHUB_REPOSITORY") or "").strip()
        if not repo:
            errors.append("无法确定 GitHub 仓库，不能检查正在打开的同 ID PR。")
        else:
            try:
                open_pr = find_open_translation_pr(repo, token or "", game_id)
            except Exception as exc:  # noqa: BLE001 - this becomes a user-facing review message.
                errors.append(f"无法检查正在打开的同 ID PR：{exc}。请稍后重试。")
            else:
                if open_pr:
                    pr_number = int(open_pr.get("number") or 0)
                    pr_url = str(open_pr.get("html_url") or "").strip()
                    pr_reference = pr_url or (f"PR #{pr_number}" if pr_number else "现有 PR")
                    write_failure(
                        [f"Steam app ID {game_id} 已有正在审核的投稿 PR：{pr_reference}。请在该 PR 中继续处理，不要重复投稿。"],
                        retry_allowed=False,
                    )
    if kind == "update" and not existing:
        errors.append(f"Steam app ID {game_id} 不存在于 index.json；正在打开的 PR 不算已收录条目。")
    if kind == "update" and not update_summary:
        errors.append("必须填写更新内容摘要。")
    if target_variant_id and kind != "update":
        errors.append("只有更新已有文件时才能指定版本 ID。")
    if target_variant_id and not VARIANT_ID_RE.fullmatch(target_variant_id):
        errors.append("版本 ID 只能包含小写字母、数字和连字符，最长 64 个字符。")
    if not attachment:
        errors.append("必须附加且只能附加一个 UserGameStatsSchema_<app_id>.zip 文件。")
    if errors:
        write_failure(errors, retry_allowed=True)

    assert attachment is not None
    try:
        package = validate_schema_package(attachment, token, game_id, languages)
    except Exception as exc:  # noqa: BLE001 - this becomes a user-facing review message.
        write_failure([f"无法校验上传的 schema：{exc}。"], retry_allowed=True)

    previous_hash = ""
    update_diff: dict[str, Any] | None = None
    variant_changes: dict[str, list[str]] | None = None
    review_variant_id = target_variant_id or "default"
    if kind == "update":
        assert existing is not None
        existing_records = validated_entry_schema_variants(existing, require_metadata=True)
        existing_by_id = {str(record["variant_id"]): record for record in existing_records}
        if target_variant_id:
            if languages != sorted(set(str(item) for item in existing.get("languages", []))):
                write_failure(["单独更新一个版本时不能修改全局语言列表；请提交完整多版本包。"], retry_allowed=True)
            current = existing_by_id.get(target_variant_id)
            if current is None:
                write_failure([f"找不到 variant_id={target_variant_id}；新增版本请提交完整多版本包。"], retry_allowed=True)
            if package.has_manifest:
                write_failure(["指定版本 ID 时只能上传不含多版本清单的单版本 ZIP。"], retry_allowed=True)
            old_data, old_nodes = load_schema(repository_path(str(current["schema_file"])))
            uploaded = package.variants[0]
            previous_hash = sha256(old_data)
            if old_data == uploaded.data:
                write_failure([f"上传文件与当前 {target_variant_id} 版本字节级完全相同。"], retry_allowed=True)
            diff_languages = sorted(set(languages + list(existing.get("languages", []))))
            update_diff = summarize_update_diff(
                achievement_rows(old_nodes, diff_languages),
                achievement_rows(uploaded.nodes, diff_languages),
                diff_languages,
            )
            variant_changes = {"added": [], "removed": [], "changed": [target_variant_id]}
        else:
            if len(existing_records) > 1 and not package.has_manifest:
                write_failure([
                    "该游戏包含多个版本。请上传带 translation-variants.json 的完整多版本包，"
                    "或填写“要更新的版本 ID”以单独更新一个版本。"
                ], retry_allowed=True)
            new_by_id = {variant.variant_id: variant for variant in package.variants}
            old_ids = set(existing_by_id)
            new_ids = set(new_by_id)
            changed_ids: list[str] = []
            for variant_id in sorted(old_ids & new_ids):
                old_data = repository_path(str(existing_by_id[variant_id]["schema_file"])).read_bytes()
                if old_data != new_by_id[variant_id].data:
                    changed_ids.append(variant_id)
            variant_changes = {
                "added": sorted(new_ids - old_ids),
                "removed": sorted(old_ids - new_ids),
                "changed": changed_ids,
            }
            if not any(variant_changes.values()):
                write_failure(["上传包中的所有版本都与当前翻译库字节级完全相同。"], retry_allowed=True)
            review_variant_id = changed_ids[0] if changed_ids else ("default" if "default" in new_by_id else sorted(new_ids)[0])
            review_variant = new_by_id[review_variant_id]
            old_record = existing_by_id.get(review_variant_id)
            if old_record:
                old_data, old_nodes = load_schema(repository_path(str(old_record["schema_file"])))
                previous_hash = sha256(old_data)
                diff_languages = sorted(set(languages + list(existing.get("languages", []))))
                update_diff = summarize_update_diff(
                    achievement_rows(old_nodes, diff_languages),
                    achievement_rows(review_variant.nodes, diff_languages),
                    diff_languages,
                )

    try:
        effective_variants, schema_files = save_schema_package(
            package,
            game_id,
            existing,
            target_variant_id=target_variant_id,
        )
    except Exception as exc:  # noqa: BLE001 - this becomes a user-facing review message.
        write_failure([f"无法保存 schema 版本：{exc}。"], retry_allowed=True)

    primary_record = next((record for record in schema_files if record.get("primary")), None)
    if primary_record is None:
        write_failure(["保存后的版本集合缺少主版本。"], retry_allowed=False)
    review_variant = next((variant for variant in effective_variants if variant.variant_id == review_variant_id), effective_variants[0])
    rows = review_variant.rows
    coverage = review_variant.coverage

    timestamp = now_utc()
    keep_schema_files = package.has_manifest or target_variant_id or isinstance((existing or {}).get("schema_files"), list)
    entry = build_entry(
        existing,
        game_name=game_name,
        game_id=game_id,
        store_url=store_url,
        languages=languages,
        schema_file=str(primary_record["schema_file"]),
        achievement_count=int(primary_record["achievement_count"]),
        schema_hash=str(primary_record["sha256"]),
        source_issue=issue.get("html_url", ""),
        contributor=issue_author(issue),
        timestamp=timestamp,
        schema_files=schema_files if keep_schema_files else None,
    )
    rows_by_variant = variant_achievement_rows(entry, languages)
    issue_number = int(issue["number"])
    branch_prefix = "translation-library/update" if kind == "update" else "translation-library/issue"
    title_prefix = "Update" if kind == "update" else "Add"
    result = {
        "ok": True,
        "kind": kind,
        "branch": f"{branch_prefix}-{issue_number}",
        "pr_title": f"{title_prefix} achievement translations for {game_name} ({game_id})",
        "pr_labels": f"{NEW_LABEL},{UPDATE_LABEL}" if kind == "update" else NEW_LABEL,
        "commit_message": f"data: {'update' if kind == 'update' else 'add'} achievement translations from issue #{issue_number}",
        "game_id": game_id,
        "game_name": game_name,
        "schema_variant_count": len(schema_files),
        "updated_variant_id": target_variant_id or None,
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
            contributor_notes=contributor_notes,
            review_variant_id=review_variant.variant_id,
            review_variant_hash=sha256(review_variant.data),
            variant_changes=variant_changes,
            rows_by_variant=rows_by_variant,
        ),
        encoding="utf-8",
    )
    return result


def validate_outdated_report(event: dict[str, Any]) -> dict[str, Any]:
    issue = event["issue"]
    fields = parse_issue_form(issue.get("body") or "")
    game_name, game_id, store_url, _languages, errors = validate_common_fields(fields, require_languages=False)
    report_type = field_value(fields, ["Issue type", "错误类型"])
    reason = field_value(fields, ["Issue details", "错误说明", "Why do you think the file is outdated?", "过期说明"]).strip()
    source = first_line(field_value(fields, ["Reference or source", "参考来源"]))
    try:
        state = report_state(report_type)
    except ValueError as exc:
        errors.append(str(exc))
        state = "outdated"
    index = load_index()
    existing = existing_entry(index, game_id) if game_id else None
    if not existing:
        errors.append(f"Steam app ID {game_id} 不存在于 index.json，不能报告错误。")
    if not reason or reason == "_No response_":
        errors.append("必须填写错误说明。")
    if errors:
        write_failure(errors, retry_allowed=True)

    assert existing is not None
    timestamp = now_utc()
    entry = dict(existing)
    entry["game_name"] = game_name or existing.get("game_name", "")
    entry["store_url"] = store_url or existing.get("store_url", "")
    entry["status"] = state
    entry["report"] = {
        "type": state,
        "reported_at": timestamp,
        "source_issue": issue.get("html_url", ""),
        "source_pr": None,
        "reporter_id": issue_author(issue),
        "reason": reason,
        "reference": source,
    }
    issue_number = int(issue["number"])
    entry.pop("outdated", None)
    report_path = write_pending_report(entry, issue_number)
    result = {
        "ok": True,
        "kind": "outdated",
        "branch": f"translation-library/report-{issue_number}",
        "pr_title": f"Report achievement translation issue for {entry['game_name']} ({game_id})",
        "pr_labels": OUTDATED_LABEL,
        "commit_message": f"data: report achievement translation issue from issue #{issue_number}",
        "game_id": game_id,
        "game_name": entry["game_name"],
        "report_state": state,
        "report_path": report_path,
    }
    Path("submission_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("pr_title.txt").write_text(result["pr_title"] + "\n", encoding="utf-8")
    Path("pr_body.md").write_text(
        f"""## Achievement Translation Error Report

- Game name: {entry['game_name']}
- Steam app ID: `{game_id}`
- Steam store URL: {entry.get('store_url', '')}
- Current schema file: `{entry.get('schema_file', '')}`
- Current file size: {entry_file_size_label(entry)}
- Current SHA-256: `{entry.get('sha256', '')}`
- Last library update: {entry.get('updated_at', '')}
- Source issue: {issue.get('html_url', '')}
- Reporter: @{issue_author(issue)}
- Reported at: {timestamp}
- Report type: `{state}`

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
