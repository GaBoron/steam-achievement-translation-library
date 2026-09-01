#!/usr/bin/env python3
"""PR-side maintenance for translation library pull requests."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from pr_comment_workflow import (
    apply_pr_update,
    clear_wait_for_update_from_comment,
    close_comment_is_authorized,
    force_refresh_pr,
    handle_comment,
    handle_pr_close,
    mark_wait_for_update,
    update_pr_title_and_body,
)

from pr_finalization import (
    finalize_merged_pr,
    notify_fulfilled_translation_petitions,
    open_translation_petitions,
)

from legacy_pr_schema import normalize_legacy_pr_schema_paths

from pr_metadata import (
    body_field,
    build_outdated_body,
    comment_actor,
    comment_is_authorized,
    entry_from_metadata,
    fulfilled_petition_comment,
    is_bot,
    is_force_refresh_command,
    is_update_command,
    merged_thanks_comment,
    parse_pr_metadata,
    parse_update_command,
    parse_update_command_detail,
    pr_kind,
    pr_labels,
    reported_entry_from_metadata,
    section_after_heading,
    source_issue_number,
    split_languages,
    strip_inline_code,
    translation_petition_game_id,
    update_comment_value,
    update_error_comment,
    update_first_line,
    update_success_comment,
    validate_languages_for_schema,
    validate_metadata_variants,
    validate_store_url,
)

from pr_git import (
    checkout_pr_branch,
    commit_and_push,
    configure_git_identity,
    delete_pr_branch,
    push_branch,
    push_main_with_retry,
    remove_index_entries,
    rename_schema_variants,
    run,
    upsert_entry_for_pr,
)

from github_repository import (
    add_issue_label,
    close_issue,
    close_pull_request,
    comment_issue,
    comment_issue_once,
    ensure_label,
    github_request,
    issue_comments,
    lock_issue,
    remove_issue_label,
)

from close_command import (
    close_command_error,
    close_completed_comment,
    close_request_comment,
    confirmation_follows_reply,
    is_close_command,
    latest_close_request,
    parse_close_command,
)

from library_submission_bot import (
    LANGUAGE_RE,
    achievement_rows,
    build_submission_pr_body,
    entry_problem_report,
    entry_file_size_label,
    entry_schema_variants,
    escape_table,
    existing_entry,
    extract_attachment,
    field_value,
    first_line,
    load_index,
    load_schema,
    now_utc,
    parse_issue_form,
    parse_schema_variants_marker,
    pending_report_relative_path,
    repository_path,
    require_language_coverage,
    report_state,
    save_schema_package,
    schema_file_size_bytes,
    schema_file_size_label,
    sha256,
    steam_store_id,
    summarize_update_diff,
    upsert_index_entry,
    validate_schema_package,
    validate_schema_structure,
    validated_entry_schema_variants,
    variant_achievement_rows,
    write_human_index,
    write_index,
    write_pending_report,
)

ROOT = Path(__file__).resolve().parent.parent
WAIT_FOR_UPDATE_LABEL = "等待更新"
BOT_USERS = {"github-actions[bot]"}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
UPDATE_LABELS = {"更新文件", "update"}
OUTDATED_LABELS = {"报告错误", "报告过期", "outdated"}
TRANSLATION_PETITION_LABEL = "翻译请愿"
TRANSLATION_PETITION_FULFILLED_MARKER = "translation-library-petition-fulfilled"
DEFAULT_REVIEWERS = ["GaBoron"]


UPDATE_COMMAND_ALIASES = {
    "doc": "doc",
    "file": "doc",
    "schema": "doc",
    "id": "id",
    "app": "id",
    "appid": "id",
    "app-id": "id",
    "name": "name",
    "title": "name",
    "summary": "summary",
    "note": "summary",
    "type": "type",
    "reason": "reason",
    "reference": "reference",
    "ref": "reference",
}
UPDATE_VALUE_COMMANDS = {"id", "name", "summary", "type", "reason", "reference"}
UPDATE_COMMAND_HELP = (
    "支持的类型：`doc`、`id`、`name`、`summary`、`type`、`reason`、`reference`。"
)
UPDATE_COMMANDS_BY_KIND = {
    "translation-contribution": {"doc", "id", "name"},
    "update": {"doc", "id", "name", "summary"},
    "outdated": {"name", "type", "reason", "reference"},
}


def mark_source_pr(event: dict[str, Any], repo: str, token: str) -> bool:
    pr = event.get("pull_request") or {}
    body = str(pr.get("body") or "")
    game_id = body_field(body, "Steam app ID")
    if not game_id:
        return False

    index = load_index()
    entry = next((item for item in index.get("entries", []) if str(item.get("game_id")) == game_id), None)

    pr_url = str(pr.get("html_url") or "")
    merged_at = str(pr.get("merged_at") or "")
    changed = False
    pending_report_path: Path | None = None

    if pr_kind(pr) == "outdated":
        if not entry:
            return False
        meta = parse_pr_metadata(pr)
        updated_entry = reported_entry_from_metadata(entry, meta, source_pr=pr_url or None)
        changed = updated_entry != entry
        entry = updated_entry
        issue_number = source_issue_number(pr)
        if issue_number:
            pending_report_path = ROOT / pending_report_relative_path(issue_number)
            if pending_report_path.is_file():
                pending_report_path.unlink()
                changed = True
    else:
        meta = parse_pr_metadata(pr)
        entry = entry_from_metadata(meta)
        normalize_legacy_pr_schema_paths(entry, context="merged PR")
        primary_rows: list[dict[str, str]] | None = None
        primary_variant: dict[str, Any] | None = None
        primary_digest = ""
        seen_variant_hashes: dict[str, str] = {}
        for variant in validated_entry_schema_variants(entry, require_metadata=True):
            schema_path = repository_path(str(variant.get("schema_file") or ""))
            if not schema_path.is_file():
                raise RuntimeError(f"merged PR schema file is missing from main: {variant.get('schema_file') or '<empty>'}")
            data, nodes = load_schema(schema_path)
            validate_schema_structure(data, nodes)
            variant_languages = [str(value) for value in variant.get("languages") or entry.get("languages", [])]
            rows = achievement_rows(nodes, variant_languages)
            require_language_coverage(rows, variant_languages)
            expected_hash = str(variant.get("sha256") or "")
            if expected_hash and sha256(data) != expected_hash:
                raise RuntimeError(f"merged PR schema SHA-256 does not match PR metadata for {variant.get('schema_file')}")
            digest = sha256(data)
            duplicate_id = seen_variant_hashes.get(digest)
            if duplicate_id is not None:
                raise RuntimeError(
                    f"merged PR variants {duplicate_id} and {variant.get('variant_id')} contain identical files"
                )
            seen_variant_hashes[digest] = str(variant.get("variant_id"))
            expected_count = variant.get("achievement_count")
            if expected_count not in (None, "") and int(str(expected_count)) != len(rows):
                raise RuntimeError(f"merged PR achievement count does not match PR metadata for {variant.get('schema_file')}")
            if variant.get("primary"):
                primary_rows = rows
                primary_variant = variant
                primary_digest = digest
        if primary_rows is None:
            raise RuntimeError("merged PR schema metadata has no primary variant")
        assert primary_variant is not None
        if str(entry.get("schema_file") or "") != str(primary_variant.get("schema_file") or ""):
            raise RuntimeError("merged PR primary schema path does not match top-level metadata")
        if str(entry.get("sha256") or "") != primary_digest:
            raise RuntimeError("merged PR primary schema SHA-256 does not match top-level metadata")
        entry["achievement_count"] = len(primary_rows)
        if pr_url and entry.get("source_pr") != pr_url:
            entry["source_pr"] = pr_url
            changed = True
        if merged_at and entry.get("updated_at") != merged_at:
            entry["updated_at"] = merged_at
            changed = True
        changed = True

    if not changed:
        return False
    upsert_index_entry(entry)
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    add_paths = ["files", "index.json", "index-v2.json", "INDEX.md", "INDEX_EN.md"]
    if pending_report_path is not None:
        add_paths.append(pending_report_path.relative_to(ROOT).as_posix())
    run(["git", "add", "-A", "--", *add_paths])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False
    run(["git", "commit", "-m", f"data: record source PR for translation entry #{int(pr.get('number') or 0)}"])
    push_main_with_retry()
    return True


def finalize_pr_number(repo: str, token: str, pr_number: int) -> None:
    pr = github_request("GET", repo, token, f"/pulls/{pr_number}")
    if not pr:
        raise RuntimeError(f"Pull request #{pr_number} was not found.")
    if not pr.get("merged"):
        raise RuntimeError(f"Pull request #{pr_number} is not merged.")
    event = {"pull_request": pr}
    mark_source_pr(event, repo, token)
    finalize_merged_pr(event, repo, token)


def finalize_head_branch(repo: str, token: str, head_branch: str) -> bool:
    if not head_branch.startswith("translation-library/"):
        return False
    owner = repo.split("/", 1)[0]
    query = urllib.parse.urlencode({
        "state": "closed",
        "base": "main",
        "head": f"{owner}:{head_branch}",
        "per_page": "100",
    })
    pulls = github_request("GET", repo, token, f"/pulls?{query}") or []
    merged_numbers = [
        int(pr["number"])
        for pr in pulls
        if pr.get("merged_at") and int(pr.get("number") or 0)
    ]
    for number in sorted(set(merged_numbers)):
        finalize_pr_number(repo, token, number)
    return bool(merged_numbers)


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain translation PR metadata, comments, and labels.")
    parser.add_argument("--event", type=Path, help="GitHub event JSON path")
    parser.add_argument("--repo", default="", help="owner/repo")
    parser.add_argument("--token", default="", help="GitHub token")
    parser.add_argument("--mark-source-pr", action="store_true")
    parser.add_argument("--lock-merged-pr", action="store_true")
    parser.add_argument("--mark-wait-for-update", action="store_true")
    parser.add_argument("--handle-comment", action="store_true")
    parser.add_argument("--finalize-pr", type=int, default=0, help="Fetch and finalize a merged PR by number")
    parser.add_argument("--finalize-head-branch", default="", help="Find and finalize merged PRs from a head branch")
    args = parser.parse_args()

    event = json.loads(args.event.read_text(encoding="utf-8")) if args.event else {}
    if args.finalize_pr:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        finalize_pr_number(args.repo, args.token, args.finalize_pr)
    if args.finalize_head_branch:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        finalize_head_branch(args.repo, args.token, args.finalize_head_branch)
    if args.mark_source_pr:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        mark_source_pr(event, args.repo, args.token)
    if args.lock_merged_pr:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        finalize_merged_pr(event, args.repo, args.token)
    if args.mark_wait_for_update:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        mark_wait_for_update(args.repo, args.token, event)
    if args.handle_comment:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        handle_comment(args.repo, args.token, event)


if __name__ == "__main__":
    main()
