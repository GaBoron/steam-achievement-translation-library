"""Catalog submission metadata, variant validation, and shared display helpers."""
from __future__ import annotations

import math
import os
import re
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any

import catalog_v2
from pr_submission_data import load_submission_catalog, write_submission_entry


REPO_ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = REPO_ROOT / "files"
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
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
    catalog = load_submission_catalog(root=REPO_ROOT)
    index = catalog_v2.legacy_index_from_catalog(catalog)
    index["entries"] = sort_entries(index["entries"])
    return index


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
    del primary  # Kept for compatibility with existing workflow call sites.
    return catalog_v2.schema_relative_path(game_id, variant_id)


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
        record.setdefault("languages", entry.get("languages"))
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
    primary_path = PurePosixPath(str(entry.get("schema_file") or ""))
    inferred_game_id = primary_path.parts[1] if len(primary_path.parts) >= 2 else ""
    game_id = str(entry.get("game_id") or inferred_game_id)
    explicit_variants = isinstance(raw_variants, list)
    for record in records:
        variant_id = str(record.get("variant_id") or "")
        expected_path = schema_variant_relative_path(game_id, variant_id, bool(record.get("primary")))
        if str(record.get("schema_file") or "") != expected_path:
            raise ValueError(f"版本 {variant_id} 的路径必须是 {expected_path}")
        if explicit_variants and not record.get("primary"):
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
            languages = record.get("languages")
            if not isinstance(languages, list) or not languages:
                raise ValueError(f"版本 {variant_id} 的 languages 无效")
            normalized_languages = [str(language) for language in languages]
            if normalized_languages != sorted(set(normalized_languages)) or any(
                not LANGUAGE_RE.fullmatch(language) for language in normalized_languages
            ):
                raise ValueError(f"版本 {variant_id} 的 languages 无效")
    return records


def existing_entry(index: dict[str, Any], game_id: str) -> dict[str, Any] | None:
    for entry in index.get("entries", []):
        if str(entry.get("game_id")) == game_id:
            return entry
    return None


def upsert_catalog_entry(entry: dict[str, Any], *, previous_game_id: str = "") -> None:
    """Persist only this game's pending metadata in an in-flight PR."""
    index = load_index()
    game_id = str(entry.get("game_id") or "")
    existing = existing_entry(index, game_id)
    if existing and "schema_files" in existing and "schema_files" not in entry:
        entry = dict(entry)
        entry["schema_files"] = existing["schema_files"]
    write_submission_entry(entry, previous_game_id=previous_game_id, root=REPO_ROOT)


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def schema_download_url(schema_file: str, repository: str | None = None) -> str:
    normalized = normalized_schema_file(schema_file)
    encoded_path = urllib.parse.quote(normalized, safe="/")
    repo = repository or os.environ.get("GITHUB_REPOSITORY", "GaBoron/steam-achievement-translation-library")
    return f"https://cdn.jsdelivr.net/gh/{repo}@main/{encoded_path}"


def entry_file_size_bytes(entry: dict[str, Any], schema_file: str) -> int:
    raw_size = entry.get("file_size_bytes")
    if isinstance(raw_size, int):
        return raw_size
    if isinstance(raw_size, str) and raw_size.isdigit():
        return int(raw_size)
    return schema_file_size_bytes(schema_file)


def entry_file_size_label(entry: dict[str, Any]) -> str:
    schema_file = str(entry.get("schema_file") or "").strip()
    if not schema_file:
        return ""
    return schema_file_size_label(entry_file_size_bytes(entry, schema_file))


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
