"""Submission metadata interpretation and pull-request presentation."""
from __future__ import annotations

import base64
import json
import re
from pathlib import PurePosixPath
from typing import Any

from library_index import (
    entry_contributors,
    escape_table,
    repository_path,
    schema_file_size_label,
    validated_entry_schema_variants,
)
from steam_schema import achievement_rows, load_schema, require_language_coverage, validate_schema_structure


UPDATE_LABEL = "更新文件"
OUTDATED_LABEL = "报告错误"
LEGACY_UPDATE_LABEL = "update"
LEGACY_OUTDATED_LABELS = {"报告过期", "outdated"}


def steam_store_id(url: str) -> str | None:
    match = re.search(r"store\.steampowered\.com/app/(\d+)(?:/|$)", url)
    return match.group(1) if match else None


def steam_store_url(app_id: str) -> str:
    return f"https://store.steampowered.com/app/{app_id}/"


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
    variants = validated_entry_schema_variants(entry, require_metadata=True)
    lines = [
        "## Schema Variants",
        "",
        "| Variant | Languages | Achievements | Size | SHA-256 | Files |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for variant in variants:
        size = schema_file_size_label(int(variant.get("file_size_bytes") or 0))
        schema_file = str(variant.get("schema_file") or "")
        catalog_file = str(PurePosixPath(schema_file).with_name("achievements.md"))
        lines.append(
            f"| `{variant.get('variant_id', '')}` | {escape_table(', '.join(variant.get('languages') or []))} | "
            f"{variant.get('achievement_count', '')} | {size} | `{variant.get('sha256', '')}` | "
            f"[bin]({schema_file}) · [achievements]({catalog_file}) |"
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
        variant_languages = [str(value) for value in variant.get("languages") or languages]
        rows = achievement_rows(nodes, variant_languages)
        require_language_coverage(rows, variant_languages)
        rows_by_variant[str(variant["variant_id"])] = rows
    return rows_by_variant


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
    del coverage, rows, rows_by_variant
    title = "Translation Library Update" if kind == "update" else "Translation Library Submission"
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
## Update Summary

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
    issue_match = re.search(r"(?:/issues/|#)(\d+)(?:[/?#]|$)", issue_url)
    closes = f"\n\nCloses #{issue_match.group(1)}" if issue_match else ""
    game_link = f"[{entry['game_name']}]({steam_store_url(str(entry['game_id']))})"
    return f"""## {title}

- Game: {game_link}
- Steam app ID: `{entry['game_id']}`
- Contributors: {', '.join('@' + contributor for contributor in entry_contributors(entry)) or 'unknown'}
- Variants: {len(validated_entry_schema_variants(entry))}
- Languages: {', '.join(f'`{language}`' for language in languages)}
- Achievements: {entry['achievement_count']}

{variants_section}
{notes_section}
{update_section}

## Review

The human-readable achievement catalog is generated from each submitted BIN file.
Review the corresponding `achievements.md` file for names and descriptions.{closes}
"""
