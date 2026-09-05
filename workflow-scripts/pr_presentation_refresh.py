"""Refresh generated translation PR presentation from checked-out schema files."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from library_index import (
    repository_path,
    schema_file_size_label,
    validated_entry_schema_variants,
)
from pr_metadata import parse_pr_metadata, validate_store_url
from steam_schema import (
    achievement_rows,
    load_schema,
    require_language_coverage,
    schema_languages,
    sha256,
    validate_schema_structure,
)
from submission_inputs import now_utc
from submission_presentation import (
    build_achievement_text_sections,
    build_schema_variants_section,
)


@dataclass(frozen=True)
class RefreshedPrPresentation:
    title: str
    body: str
    metadata_changed: bool


def _replace_metadata_line(body: str, label: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^- {re.escape(label)}:\s*.*$")
    if not pattern.search(body):
        raise ValueError(f"PR 描述缺少 {label} 元数据。")
    return pattern.sub(lambda _match: f"- {label}: {value}", body, count=1)


def _replace_section(body: str, heading: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(heading)}\s*\n.*?(?=^##\s|\Z)"
    )
    if not pattern.search(body):
        raise ValueError(f"PR 描述缺少 {heading} 部分。")
    return pattern.sub(replacement.rstrip() + "\n\n", body, count=1).rstrip() + "\n"


def build_refreshed_translation_pr_presentation(pr: dict[str, Any]) -> RefreshedPrPresentation:
    """Rebuild dynamic metadata and achievement tables from current branch files."""
    meta = parse_pr_metadata(pr)
    kind = str(meta.get("kind") or "")
    if kind not in {"translation-contribution", "update"}:
        return RefreshedPrPresentation(
            title=str(pr.get("title") or ""),
            body=str(pr.get("body") or ""),
            metadata_changed=False,
        )

    game_id = str(meta.get("game_id") or "")
    validate_store_url(game_id, str(meta.get("store_url") or ""))
    seed_entry = {
        "game_id": game_id,
        "languages": list(meta.get("languages") or []),
        "schema_file": meta.get("schema_file"),
        "schema_files": meta.get("schema_files"),
        "file_size_bytes": 0,
        "sha256": meta.get("sha256"),
        "achievement_count": meta.get("achievement_count"),
    }
    records = validated_entry_schema_variants(seed_entry)
    refreshed_records: list[dict[str, Any]] = []
    rows_by_variant: dict[str, list[dict[str, str]]] = {}
    coverage_by_variant: dict[str, dict[str, int]] = {}
    all_languages: set[str] = set()

    for record in records:
        variant_id = str(record["variant_id"])
        schema_file = str(record["schema_file"])
        data, nodes = load_schema(repository_path(schema_file))
        validate_schema_structure(data, nodes)
        languages = schema_languages(nodes)
        if not languages:
            raise ValueError(f"版本 {variant_id} 未检测到完整的 Steam 语言。")
        rows = achievement_rows(nodes, languages)
        coverage = require_language_coverage(rows, languages)
        refreshed = dict(record)
        refreshed.update({
            "languages": languages,
            "file_size_bytes": len(data),
            "sha256": sha256(data),
            "achievement_count": len(rows),
        })
        refreshed_records.append(refreshed)
        rows_by_variant[variant_id] = rows
        coverage_by_variant[variant_id] = coverage
        all_languages.update(languages)

    primary = next(record for record in refreshed_records if record.get("primary"))
    languages = sorted(all_languages)
    old_fingerprint = (
        str(meta.get("sha256") or ""),
        str(meta.get("file_size") or ""),
        str(meta.get("achievement_count") or ""),
        tuple(meta.get("languages") or []),
        meta.get("schema_files"),
    )
    explicit_variants = meta.get("schema_files") is not None
    refreshed_schema_files = refreshed_records if explicit_variants else None
    new_fingerprint = (
        str(primary["sha256"]),
        schema_file_size_label(int(primary["file_size_bytes"])),
        str(primary["achievement_count"]),
        tuple(languages),
        refreshed_schema_files,
    )
    metadata_changed = old_fingerprint != new_fingerprint
    updated_at = now_utc() if metadata_changed else str(meta.get("updated_at") or "")

    entry: dict[str, Any] = {
        "game_name": str(meta.get("game_name") or ""),
        "game_id": game_id,
        "store_url": str(meta.get("store_url") or ""),
        "languages": languages,
        "schema_file": str(primary["schema_file"]),
        "file_size_bytes": int(primary["file_size_bytes"]),
        "achievement_count": int(primary["achievement_count"]),
        "sha256": str(primary["sha256"]),
        "source_issue": str(meta.get("source_issue") or ""),
        "contributors": list(meta.get("contributors") or []),
        "submitted_at": str(meta.get("submitted_at") or ""),
        "updated_at": updated_at,
        "status": "current",
    }
    if refreshed_schema_files is not None:
        entry["schema_files"] = refreshed_schema_files

    body = str(pr.get("body") or "")
    body = _replace_metadata_line(body, "Supported languages", ", ".join(languages))
    body = _replace_metadata_line(body, "Achievement count", str(primary["achievement_count"]))
    body = _replace_metadata_line(body, "Schema file", f"`{primary['schema_file']}`")
    body = _replace_metadata_line(body, "File size", schema_file_size_label(int(primary["file_size_bytes"])))
    body = _replace_metadata_line(body, "SHA-256", f"`{primary['sha256']}`")
    body = _replace_metadata_line(body, "Updated at", updated_at)

    if explicit_variants:
        body = _replace_section(body, "## Schema Variants", build_schema_variants_section(entry))
    primary_coverage = coverage_by_variant[str(primary["variant_id"])]
    coverage_lines = "\n".join(
        f"- `{language}`: {primary_coverage.get(language, 0)}/{primary['achievement_count']} achievements"
        for language in languages
    )
    body = _replace_section(body, "## Language Coverage", f"## Language Coverage\n\n{coverage_lines}")
    first_achievement_heading = re.search(r"(?m)^## Achievement Text \(`[^`]+`\)$", body)
    if first_achievement_heading is None:
        raise ValueError("PR 描述缺少 Achievement Text 部分。")
    achievement_sections = build_achievement_text_sections(
        rows_by_variant[str(primary["variant_id"])],
        languages,
        str(primary["variant_id"]),
        rows_by_variant,
    )
    body = body[:first_achievement_heading.start()].rstrip() + "\n\n" + achievement_sections.rstrip() + "\n"
    title_prefix = "Update" if kind == "update" else "Add"
    title = f"{title_prefix} achievement translations for {entry['game_name']} ({game_id})"
    return RefreshedPrPresentation(title=title, body=body, metadata_changed=metadata_changed)
