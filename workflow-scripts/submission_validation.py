"""Submission field and uploaded schema validation."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from library_index import entry_contributors, schema_file_size_bytes
from schema_package import ValidatedSchemaPackage, ValidatedSchemaVariant, resolve_schema_package
from steam_schema import (
    Node,
    achievement_rows,
    load_schema,
    require_language_coverage,
    schema_languages,
    sha256,
    validate_schema_structure,
)
from submission_inputs import Attachment, download_attachment, field_value, first_line
from submission_presentation import steam_store_url


def write_failure(errors: list[str], retry_allowed: bool = False) -> None:
    result = {
        "ok": False,
        "errors": errors,
        "retry_allowed": retry_allowed,
        "close_issue": not retry_allowed,
    }
    Path("submission_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1)


def validate_common_fields(fields: dict[str, str]) -> tuple[str, str, str, list[str]]:
    game_name = first_line(field_value(fields, ["Game name", "游戏名"]))
    game_id = first_line(field_value(fields, ["Steam app ID"]))
    errors: list[str] = []
    if not game_name:
        errors.append("必须填写游戏名。")
    if not re.fullmatch(r"\d+", game_id):
        errors.append("Steam app ID 必须只包含数字。")
    store_url = steam_store_url(game_id) if re.fullmatch(r"\d+", game_id) else ""
    return game_name, game_id, store_url, errors


def validate_schema_package(
    attachment: Attachment,
    token: str | None,
    game_id: str,
) -> ValidatedSchemaPackage:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        # The Markdown label is untrusted user input; never use it as a path.
        downloaded = tmp_dir / "attachment.zip"
        download_attachment(attachment, token, downloaded)
        resolved_variants, has_manifest = resolve_schema_package(downloaded, attachment, game_id, tmp_dir)
        variants: list[ValidatedSchemaVariant] = []
        package_languages: list[str] | None = None
        for resolved in resolved_variants:
            data, nodes = load_schema(resolved.path)
            validate_schema_structure(data, nodes)
            languages = schema_languages(nodes)
            if not languages:
                raise ValueError(f"版本 {resolved.variant_id} 未检测到完整的 Steam 语言")
            if package_languages is None:
                package_languages = languages
            elif languages != package_languages:
                raise ValueError(
                    f"版本 {resolved.variant_id} 检测到的语言与主版本不一致："
                    f"{', '.join(languages)}；主版本：{', '.join(package_languages)}"
                )
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
        return ValidatedSchemaPackage(
            variants=variants,
            has_manifest=has_manifest,
            languages=package_languages or [],
        )


def validate_schema_submission(
    attachment: Attachment,
    token: str | None,
    game_id: str,
) -> tuple[bytes, list[Node], list[dict[str, str]], dict[str, int]]:
    """Compatibility wrapper for call sites that intentionally accept one schema only."""
    package = validate_schema_package(attachment, token, game_id)
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
