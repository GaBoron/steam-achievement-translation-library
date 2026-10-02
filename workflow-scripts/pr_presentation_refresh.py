"""Refresh generated translation PR presentation from checked-out schema files."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from achievement_catalog import write_entry_achievement_catalogs
from legacy_pr_schema import normalize_legacy_pr_schema_paths
from library_index import repository_path, upsert_catalog_entry, validated_entry_schema_variants
from pr_metadata import entry_from_metadata, parse_pr_metadata, validate_store_url
from steam_schema import achievement_rows, load_schema, require_language_coverage, schema_languages, sha256, validate_schema_structure
from submission_presentation import build_schema_variants_section, build_submission_pr_body


@dataclass(frozen=True)
class RefreshedPrPresentation:
    title: str
    body: str
    metadata_changed: bool


def _replace_line(body: str, label: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^- {re.escape(label)}:\s*.*$")
    if not pattern.search(body):
        raise ValueError(f"PR 描述缺少 {label} 元数据。")
    return pattern.sub(lambda _match: f"- {label}: {value}", body, count=1)


def _replace_section(body: str, heading: str, replacement: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(heading)}\s*\n.*?(?=^##\s|\Z)")
    if not pattern.search(body):
        raise ValueError(f"PR 描述缺少 {heading} 部分。")
    return pattern.sub(replacement.rstrip() + "\n\n", body, count=1).rstrip() + "\n"


def _refreshed_entry(meta: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    game_id = str(meta.get("game_id") or "")
    seed = entry_from_metadata(meta)
    normalize_legacy_pr_schema_paths(seed, context="refresh PR")
    records = validated_entry_schema_variants(seed)
    refreshed: list[dict[str, Any]] = []
    all_languages: set[str] = set()
    for record in records:
        data, nodes = load_schema(repository_path(str(record["schema_file"])))
        validate_schema_structure(data, nodes)
        languages = schema_languages(nodes)
        rows = achievement_rows(nodes, languages)
        require_language_coverage(rows, languages)
        updated = dict(record)
        updated.update({
            "languages": languages,
            "file_size_bytes": len(data),
            "sha256": sha256(data),
            "achievement_count": len(rows),
        })
        refreshed.append(updated)
        all_languages.update(languages)
    primary = next(record for record in refreshed if record.get("primary"))
    explicit = meta.get("schema_files") is not None
    entry = seed
    entry.update({
        "game_name": str(meta.get("game_name") or ""),
        "game_id": game_id,
        "store_url": str(meta.get("store_url") or ""),
        "languages": sorted(all_languages),
        "schema_file": str(primary["schema_file"]),
        "file_size_bytes": int(primary["file_size_bytes"]),
        "achievement_count": int(primary["achievement_count"]),
        "sha256": str(primary["sha256"]),
        "contributors": list(meta.get("contributors") or []),
        "status": "current",
    })
    if explicit or isinstance(entry.get("schema_files"), list):
        entry["schema_files"] = refreshed
    old = (meta.get("languages"), meta.get("sha256"), meta.get("achievement_count"), meta.get("schema_files"))
    new = (entry["languages"], entry["sha256"], str(entry["achievement_count"]), entry.get("schema_files"))
    return entry, old != new


def build_refreshed_translation_pr_presentation(pr: dict[str, Any]) -> RefreshedPrPresentation:
    meta = parse_pr_metadata(pr)
    kind = str(meta.get("kind") or "")
    if kind not in {"translation-contribution", "update"}:
        return RefreshedPrPresentation(str(pr.get("title") or ""), str(pr.get("body") or ""), False)
    validate_store_url(str(meta.get("game_id") or ""), str(meta.get("store_url") or ""))
    entry, changed = _refreshed_entry(meta)
    write_entry_achievement_catalogs(entry)
    upsert_catalog_entry(entry)
    body = str(pr.get("body") or "")
    if "- Languages:" in body and "## Review" in body:
        body = _replace_line(body, "Languages", ", ".join(f"`{value}`" for value in entry["languages"]))
        body = _replace_line(body, "Achievements", str(entry["achievement_count"]))
        body = _replace_line(body, "Variants", str(len(validated_entry_schema_variants(entry))))
        body = _replace_section(body, "## Schema Variants", build_schema_variants_section(entry))
    else:
        primary_path = repository_path(str(entry["schema_file"]))
        _data, nodes = load_schema(primary_path)
        rows = achievement_rows(nodes, entry["languages"])
        body = build_submission_pr_body(
            kind=kind,
            entry=entry,
            coverage={language: len(rows) for language in entry["languages"]},
            rows=rows,
            languages=entry["languages"],
            update_summary=str(meta.get("update_summary") or "Refreshed from the current PR branch."),
            issue_url=str(meta.get("source_issue") or ""),
            contributor_notes=str(meta.get("contributor_notes") or ""),
        )
    prefix = "Update" if kind == "update" else "Add"
    title = f"{prefix} achievement translations for {entry['game_name']} ({entry['game_id']})"
    return RefreshedPrPresentation(title, body, changed)
