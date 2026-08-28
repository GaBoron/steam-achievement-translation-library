"""Schema ZIP variant resolution and repository file persistence."""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from library_index import (
    FILES_ROOT,
    VARIANT_ID_RE,
    clean_variant_note,
    entry_schema_variants,
    repository_path,
    schema_variant_relative_path,
)
from steam_schema import Node, sha256
from submission_inputs import Attachment


MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SCHEMA_VARIANTS = 16
VARIANT_MANIFEST_NAME = "translation-variants.json"


@dataclass
class ResolvedSchemaVariant:
    variant_id: str
    path: Path
    primary: bool
    note_zh: str = ""
    note_en: str = ""
    description_zh: str = ""
    description_en: str = ""


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
    description_zh: str = ""
    description_en: str = ""
    languages: list[str] = field(default_factory=list)


@dataclass
class ValidatedSchemaPackage:
    variants: list[ValidatedSchemaVariant]
    has_manifest: bool
    languages: list[str]


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
        if not isinstance(manifest, dict) or set(manifest) != {"variants"}:
            raise ValueError(f"{VARIANT_MANIFEST_NAME} 只能包含 variants 对象")
        raw_variants = manifest.get("variants")
        if not isinstance(raw_variants, dict) or not 1 <= len(raw_variants) <= MAX_SCHEMA_VARIANTS:
            raise ValueError(f"版本清单必须包含 1 到 {MAX_SCHEMA_VARIANTS} 个 variants")
        if "default" not in raw_variants:
            raise ValueError("版本清单必须包含 default")

        resolved: list[ResolvedSchemaVariant] = []
        declared_files: set[str] = set()
        seen_ids: set[str] = set()
        total_schema_bytes = 0
        for variant_id, raw_variant in raw_variants.items():
            if not isinstance(raw_variant, dict):
                raise ValueError(f"variants.{variant_id} 必须是 JSON 对象")
            if not VARIANT_ID_RE.fullmatch(variant_id):
                raise ValueError(f"无效的 variant_id：{variant_id or '<empty>'}")
            if variant_id in seen_ids:
                raise ValueError(f"重复的 variant_id：{variant_id}")
            seen_ids.add(variant_id)
            unexpected = set(raw_variant) - {"label", "description"}
            if unexpected:
                raise ValueError(
                    f"版本 {variant_id} 包含可由自动化推导的字段：{', '.join(sorted(unexpected))}"
                )
            primary = variant_id == "default"
            expected_file = expected_name if primary else f"{variant_id}/{expected_name}"
            member = members_by_name.get(expected_file)
            if member is None:
                raise ValueError(f"ZIP 缺少版本 {variant_id} 的文件：{expected_file}")
            if member.file_size > MAX_SCHEMA_BYTES:
                raise ValueError(f"版本 {variant_id} 的 schema 超过 32 MiB 检查上限")
            total_schema_bytes += member.file_size
            if total_schema_bytes > MAX_PACKAGE_BYTES:
                raise ValueError("多版本 schema 解压后总大小超过 64 MiB 检查上限")
            declared_files.add(expected_file)
            destination = output_dir / Path(*PurePosixPath(expected_file).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
            label = raw_variant.get("label")
            if not isinstance(label, dict) or set(label) != {"zh", "en"}:
                raise ValueError(f"版本 {variant_id} 的 label 必须包含且只能包含 zh 和 en")
            description = raw_variant.get("description")
            if description is not None and (not isinstance(description, dict) or set(description) != {"zh", "en"}):
                raise ValueError(f"版本 {variant_id} 的 description 必须包含且只能包含 zh 和 en")
            resolved.append(ResolvedSchemaVariant(
                variant_id=variant_id,
                path=destination,
                primary=primary,
                note_zh=clean_variant_note(label.get("zh"), f"variants.{variant_id}.label.zh"),
                note_en=clean_variant_note(label.get("en"), f"variants.{variant_id}.label.en"),
                description_zh=_clean_description(
                    (description or {}).get("zh"), f"variants.{variant_id}.description.zh"
                ),
                description_en=_clean_description(
                    (description or {}).get("en"), f"variants.{variant_id}.description.en"
                ),
            ))
        extra_files = set(members_by_name) - declared_files - {VARIANT_MANIFEST_NAME}
        if extra_files:
            raise ValueError("ZIP 包含清单未声明的文件：" + ", ".join(sorted(extra_files)))
        resolved.sort(key=lambda variant: (not variant.primary, variant.variant_id))
        return resolved, True


def _clean_description(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 1000:
        raise ValueError(f"多版本清单中的 {field_name} 不能超过 1000 个字符")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in text):
        raise ValueError(f"多版本清单中的 {field_name} 包含无效控制字符")
    return text


def resolve_schema_upload(downloaded: Path, attachment: Attachment, game_id: str, output_dir: Path) -> Path:
    variants, has_manifest = resolve_schema_package(downloaded, attachment, game_id, output_dir)
    if has_manifest or len(variants) != 1:
        raise ValueError("此操作只接受单版本 ZIP")
    return variants[0].path


def validated_variant_record(game_id: str, variant: ValidatedSchemaVariant) -> dict[str, Any]:
    record = {
        "variant_id": variant.variant_id,
        "primary": variant.primary,
        "schema_file": schema_variant_relative_path(game_id, variant.variant_id, variant.primary),
        "note_zh": variant.note_zh,
        "note_en": variant.note_en,
        "file_size_bytes": len(variant.data),
        "sha256": sha256(variant.data),
        "achievement_count": len(variant.rows),
        "languages": list(variant.languages),
    }
    if variant.description_zh or variant.description_en:
        record["description_zh"] = variant.description_zh
        record["description_en"] = variant.description_en
    return record


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
            description_zh=str(current.get("description_zh") or ""),
            description_en=str(current.get("description_en") or ""),
            languages=list(uploaded.languages),
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
