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

from submission_validation import (
    build_entry,
    validate_common_fields,
    validate_schema_package,
    validate_schema_submission,
    write_failure,
)

from submission_presentation import (
    build_achievement_text_sections,
    build_review_table,
    build_schema_variants_section,
    build_submission_pr_body,
    issue_author,
    issue_kind,
    issue_labels,
    markdown_changed_details,
    markdown_list,
    parse_schema_variants_marker,
    schema_variants_marker,
    steam_store_id,
    variant_achievement_rows,
)

from schema_package import (
    ResolvedSchemaVariant,
    ValidatedSchemaPackage,
    ValidatedSchemaVariant,
    resolve_schema_package,
    resolve_schema_upload,
    safe_archive_members,
    save_schema_package,
    validated_variant_record,
)

from library_index import (
    clean_variant_note,
    contributor_markdown,
    entry_contributors,
    entry_file_size_bytes,
    entry_file_size_label,
    entry_problem_report,
    entry_schema_variants,
    entry_sort_key,
    escape_table,
    existing_entry,
    file_link_with_details,
    github_item_label,
    github_link,
    index_states,
    load_index,
    normalized_schema_file,
    note_text,
    pending_report_relative_path,
    pinyin_sort_key,
    pull_request_label,
    refresh_index_file_sizes,
    render_human_index,
    report_state,
    repository_path,
    schema_download_url,
    schema_file_links,
    schema_file_size_bytes,
    schema_file_size_label,
    schema_variant_relative_path,
    sort_entries,
    status_text,
    upsert_index_entry,
    validated_entry_schema_variants,
    variant_file_size_bytes,
    write_human_index,
    write_index,
    write_pending_report,
)

from submission_inputs import (
    Attachment,
    download_attachment,
    extract_attachment,
    field_value,
    find_open_translation_pr,
    first_line,
    github_api_get,
    now_utc,
    optional_field_value,
    parse_checked_languages,
    parse_comma_language_list,
    parse_extra_languages,
    parse_issue_form,
    parse_languages,
    pull_request_game_id,
)

from steam_schema import (
    Node,
    Reader,
    achievement_nodes,
    achievement_rows,
    begins,
    cstr,
    first_str,
    language_coverage,
    load_schema,
    nested,
    parse_nodes,
    require_language_coverage,
    row_map,
    serialize,
    sha256,
    strings,
    summarize_update_diff,
    validate_schema_structure,
    walk,
)

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
