"""Authorized PR comment commands and update workflow orchestration."""
from __future__ import annotations

import re
from typing import Any

from close_command import (
    close_command_error,
    close_completed_comment,
    close_request_comment,
    confirmation_follows_reply,
    is_close_command,
    latest_close_request,
    parse_close_command,
)
from github_repository import (
    add_issue_label,
    close_pull_request,
    comment_issue,
    github_request,
    issue_comments,
    lock_issue,
    remove_issue_label,
)
from library_index import (
    entry_file_size_label,
    entry_problem_report,
    escape_table,
    existing_entry,
    load_index,
    report_state,
    repository_path,
    schema_file_size_bytes,
    schema_file_size_label,
    validated_entry_schema_variants,
    write_pending_report,
)
from legacy_pr_schema import normalize_legacy_pr_schema_paths
from pr_git import checkout_pr_branch, commit_and_push, push_branch, rename_schema_variants, run
from pr_metadata import (
    build_outdated_body,
    comment_actor,
    comment_is_authorized,
    entry_from_metadata,
    is_bot,
    is_force_refresh_command,
    is_update_command,
    parse_pr_metadata,
    parse_update_command_detail,
    pr_labels,
    reported_entry_from_metadata,
    source_issue_number,
    update_error_comment,
    update_success_comment,
    validate_metadata_variants,
    validate_store_url,
)
from schema_package import save_schema_package
from steam_schema import achievement_rows, load_schema, sha256, summarize_update_diff
from submission_inputs import extract_attachment, now_utc
from submission_presentation import build_submission_pr_body, steam_store_url, variant_achievement_rows
from submission_validation import validate_schema_package


WAIT_FOR_UPDATE_LABEL = "等待更新"
DEFAULT_REVIEWERS = ["GaBoron"]
UPDATE_COMMANDS_BY_KIND = {
    "translation-contribution": {"doc", "id", "name"},
    "update": {"doc", "id", "name", "summary"},
    "outdated": {"name", "type", "reason", "reference"},
}


def close_comment_is_authorized(repo: str, token: str, pr: dict[str, Any], actor: str) -> bool:
    if not actor or is_bot(actor):
        return False
    issue_number = source_issue_number(pr)
    if issue_number:
        source_issue = github_request("GET", repo, token, f"/issues/{issue_number}") or {}
        source_author = str((source_issue.get("user") or {}).get("login") or "")
        return actor == source_author
    try:
        reporter = str(parse_pr_metadata(pr).get("reporter") or "")
    except (TypeError, ValueError):
        reporter = ""
    if reporter:
        return actor == reporter
    pr_author = str((pr.get("user") or {}).get("login") or "")
    return bool(pr_author) and not is_bot(pr_author) and actor == pr_author


def handle_pr_close(repo: str, token: str, event: dict[str, Any]) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    comment_body = str(comment.get("body") or "")
    if not is_close_command(comment_body):
        return False
    pr_number = int(issue["number"])
    pr = github_request("GET", repo, token, f"/pulls/{pr_number}") or issue
    actor = comment_actor(event)
    if not close_comment_is_authorized(repo, token, pr, actor):
        comment_issue(repo, token, pr_number, close_command_error("`/close` 只能由该 PR 对应来源 issue 的原投稿者执行。"))
        return True
    if str(pr.get("state") or "") != "open":
        comment_issue(repo, token, pr_number, close_command_error("`/close` 只能用于打开状态的 PR。"))
        return True
    action, reason, error = parse_close_command(comment_body)
    if error:
        comment_issue(repo, token, pr_number, close_command_error(error))
        return True
    if action == "request":
        comment_issue(repo, token, pr_number, close_request_comment(actor, reason, "PR"))
        return True
    comments = issue_comments(repo, token, pr_number)
    request = latest_close_request(comments, actor)
    if request is None:
        comment_issue(repo, token, pr_number, close_command_error("没有找到你尚待确认的关闭请求。请先输入 `/close 关闭原因`。"))
        return True
    if not confirmation_follows_reply(comment, request):
        comment_issue(repo, token, pr_number, close_command_error("必须等待机器人确认回复出现后，再新建评论输入 `/close confirm`。"))
        return True
    comment_issue(repo, token, pr_number, close_completed_comment(actor, request["reason"], "PR"))
    close_pull_request(repo, token, pr_number)
    lock_issue(repo, token, pr_number)
    return True


def update_pr_title_and_body(repo: str, token: str, pr_number: int, title: str, body: str) -> None:
    github_request("PATCH", repo, token, f"/pulls/{pr_number}", {"title": title, "body": body})


def force_refresh_pr(repo: str, token: str, event: dict[str, Any]) -> None:
    issue = event.get("issue") or {}
    pr_number = int(issue["number"])
    if not comment_is_authorized(event):
        comment_issue(repo, token, pr_number, "`/force-refresh` 只能由该投稿的贡献者、报告者或仓库维护者执行。")
        return
    pr = github_request("GET", repo, token, f"/pulls/{pr_number}")
    if not pr or str(pr.get("state") or "") != "open":
        comment_issue(repo, token, pr_number, "`/force-refresh` 只能用于打开状态的翻译 PR。")
        return
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    if (
        str(base.get("ref") or "") != "main"
        or str((head.get("repo") or {}).get("full_name") or "") != repo
        or not str(head.get("ref") or "").startswith("translation-library/")
    ):
        comment_issue(repo, token, pr_number, "`/force-refresh` 只适用于本仓库以 `translation-library/` 开头、目标为 `main` 的翻译 PR。")
        return
    try:
        branch = checkout_pr_branch(pr)
        run(["git", "commit", "--allow-empty", "-m", f"chore: force refresh PR #{pr_number}"])
        push_branch(branch)
        github_request(
            "POST",
            repo,
            token,
            f"/pulls/{pr_number}/requested_reviewers",
            {"reviewers": DEFAULT_REVIEWERS},
            allow_422=True,
        )
        if WAIT_FOR_UPDATE_LABEL in pr_labels(issue):
            remove_issue_label(repo, token, pr_number, WAIT_FOR_UPDATE_LABEL)
    except Exception as exc:  # noqa: BLE001 - user-facing automation report.
        comment_issue(repo, token, pr_number, f"`/force-refresh` 执行失败：{escape_table(str(exc))}")
        return
    comment_issue(
        repo,
        token,
        pr_number,
        "\n".join([
            "<!-- translation-library-force-refresh -->",
            "`/force-refresh` 已处理完成。",
            "",
            "- 已将投稿分支变基到最新 `main`，并推送新的空提交以重新触发自动检查。",
            "- 已重新请求维护者校对；通过检查和批准后，PR 会继续自动合并与入库推送流程。",
        ]),
    )


def apply_pr_update(repo: str, token: str, event: dict[str, Any]) -> None:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    pr_number = int(issue["number"])
    comment_body = str(comment.get("body") or "")
    if is_update_command(comment_body) and not comment_is_authorized(event):
        comment_issue(repo, token, pr_number, "`/update` 只能由该投稿的贡献者或仓库维护者执行。")
        return
    command, value, command_error = parse_update_command_detail(comment_body)
    if command_error:
        comment_issue(repo, token, pr_number, update_error_comment(command_error))
        return
    if not command:
        return
    pr = github_request("GET", repo, token, f"/pulls/{pr_number}")
    if not pr or str(pr.get("state") or "") != "open":
        comment_issue(repo, token, pr_number, "`/update` 只能用于打开状态的翻译 PR。")
        return

    meta = parse_pr_metadata(pr)
    original_meta = dict(meta)
    old_game_id = str(meta.get("game_id") or "")
    kind = str(meta["kind"])
    if command not in UPDATE_COMMANDS_BY_KIND.get(kind, set()):
        if kind == "outdated":
            message = "报告错误 PR 仅支持 `name`、`type`、`reason` 和 `reference`。"
        elif kind == "translation-contribution":
            message = "新投稿 PR 不支持 `summary`；该字段仅用于更新已有文件。"
        else:
            message = f"`/update {command}` 不适用于当前 PR 类型。"
        comment_issue(repo, token, pr_number, update_error_comment(message))
        return

    branch = checkout_pr_branch(pr)
    attachment = extract_attachment(comment_body)
    command_text = comment_body.strip().splitlines()[0].strip() if comment_body.strip() else "/update"
    changes: list[dict[str, Any]] = []
    variant_changes: dict[str, list[str]] | None = None
    review_variant_id = "default"
    review_variant_hash = ""

    def record_change(field: str, before: Any, after: Any) -> None:
        changes.append({"field": field, "before": before, "after": after})

    try:
        if kind != "outdated":
            previous_schema_file = str(meta.get("schema_file") or "")
            if normalize_legacy_pr_schema_paths(meta):
                record_change("schema file", previous_schema_file, meta["schema_file"])
        if command == "doc":
            if not attachment:
                raise ValueError("`/update doc` 需要在同一条评论中附加 `UserGameStatsSchema_<app_id>.zip`。")
            target_variant_id = value.lower()
            if target_variant_id and not re.fullmatch(r"^[a-z0-9][a-z0-9-]{0,63}$", target_variant_id):
                raise ValueError("variant_id 只能包含小写字母、数字和连字符，最长 64 个字符。")
            package = validate_schema_package(attachment, token, old_game_id)
            previous_languages = list(meta["languages"])
            detected_languages = package.languages
            current_entry = {
                "schema_file": meta.get("schema_file"),
                "schema_files": meta.get("schema_files"),
                "file_size_bytes": 0,
                "sha256": meta.get("sha256"),
                "achievement_count": meta.get("achievement_count"),
            }
            existing_records = validated_entry_schema_variants(current_entry)
            existing_by_id = {str(record["variant_id"]): record for record in existing_records}
            review_variant_id = target_variant_id or "default"
            update_diff = None
            if target_variant_id:
                current = existing_by_id.get(target_variant_id)
                if current is None:
                    raise ValueError(f"找不到 variant_id={target_variant_id}；新增版本请提交完整多版本包。")
                if package.has_manifest:
                    raise ValueError("指定 variant_id 时只能上传不含多版本清单的单版本 ZIP。")
                if detected_languages != previous_languages:
                    raise ValueError("单独更新一个版本时不能修改自动识别的全局语言；请提交完整多版本包。")
                old_data, old_nodes = load_schema(repository_path(str(current["schema_file"])))
                uploaded = package.variants[0]
                previous_hash = sha256(old_data)
                if old_data == uploaded.data:
                    raise ValueError(f"上传文件与当前 {target_variant_id} 版本字节级完全相同。")
                update_diff = summarize_update_diff(
                    achievement_rows(old_nodes, previous_languages),
                    achievement_rows(uploaded.nodes, previous_languages),
                    previous_languages,
                )
                variant_changes = {"added": [], "removed": [], "changed": [target_variant_id]}
            else:
                if len(existing_records) > 1 and not package.has_manifest:
                    raise ValueError(
                        "该 PR 包含多个版本；请上传带 translation-variants.json 的完整多版本包，"
                        "或使用 `/update doc <variant_id>` 单独更新一个版本。"
                    )
                new_by_id = {variant.variant_id: variant for variant in package.variants}
                old_ids = set(existing_by_id)
                new_ids = set(new_by_id)
                changed_ids = [
                    variant_id
                    for variant_id in sorted(old_ids & new_ids)
                    if repository_path(str(existing_by_id[variant_id]["schema_file"])).read_bytes()
                    != new_by_id[variant_id].data
                ]
                variant_changes = {
                    "added": sorted(new_ids - old_ids),
                    "removed": sorted(old_ids - new_ids),
                    "changed": changed_ids,
                }
                if not any(variant_changes.values()):
                    raise ValueError("上传包中的所有版本都与当前 PR 字节级完全相同。")
                review_variant_id = changed_ids[0] if changed_ids else ("default" if "default" in new_by_id else sorted(new_ids)[0])
                old_record = existing_by_id.get(review_variant_id)
                if old_record:
                    old_data, old_nodes = load_schema(repository_path(str(old_record["schema_file"])))
                    previous_hash = sha256(old_data)
                    diff_languages = sorted(set(previous_languages + detected_languages))
                    update_diff = summarize_update_diff(
                        achievement_rows(old_nodes, diff_languages),
                        achievement_rows(new_by_id[review_variant_id].nodes, diff_languages),
                        diff_languages,
                    )
                else:
                    previous_hash = ""

            effective_variants, schema_files = save_schema_package(
                package,
                old_game_id,
                current_entry,
                target_variant_id=target_variant_id,
            )
            primary_record = next(record for record in schema_files if record.get("primary"))
            review_variant = next(
                (variant for variant in effective_variants if variant.variant_id == review_variant_id),
                effective_variants[0],
            )
            rows, coverage = review_variant.rows, review_variant.coverage
            review_variant_hash = sha256(review_variant.data)
            previous_schema_file = str(meta.get("schema_file") or "")
            previous_file_size = str(meta.get("file_size") or "")
            previous_count = str(meta.get("achievement_count") or "")
            previous_updated_at = str(meta.get("updated_at") or "")
            meta["schema_file"] = str(primary_record["schema_file"])
            meta["schema_files"] = schema_files if package.has_manifest or target_variant_id or meta.get("schema_files") is not None else None
            meta["file_size"] = schema_file_size_label(int(primary_record["file_size_bytes"]))
            meta["sha256"] = str(primary_record["sha256"])
            meta["achievement_count"] = str(primary_record["achievement_count"])
            meta["updated_at"] = now_utc()
            if not target_variant_id:
                meta["languages"] = detected_languages
            record_change("schema file", previous_schema_file, meta["schema_file"])
            record_change("file size", previous_file_size, meta["file_size"])
            record_change(
                f"{review_variant_id} SHA-256",
                previous_hash or str(original_meta.get("sha256") or ""),
                review_variant_hash,
            )
            record_change("achievement count", previous_count, meta["achievement_count"])
            record_change("updated at", previous_updated_at, meta["updated_at"])
            if not target_variant_id and previous_languages != meta["languages"]:
                record_change("automatically detected languages", previous_languages, meta["languages"])
            record_change(
                "schema variants",
                ", ".join(sorted(existing_by_id)),
                ", ".join(str(record["variant_id"]) for record in schema_files),
            )
        elif command == "id":
            if not re.fullmatch(r"\d+", value):
                raise ValueError("`/update id` 后面必须是数字 Steam app ID。")
            previous_schema_file = str(meta.get("schema_file") or "")
            previous_file_size = str(meta.get("file_size") or "")
            previous_store_url = str(meta.get("store_url") or "")
            previous_hash = str(meta.get("sha256") or "")
            previous_count = str(meta.get("achievement_count") or "")
            previous_updated_at = str(meta.get("updated_at") or "")
            if kind == "outdated":
                replacement = existing_entry(load_index(), value)
                if not replacement:
                    raise ValueError("报告错误 PR 的 `/update id` 必须指向库里已经收录的 Steam app ID。")
                meta["schema_file"] = str(replacement.get("schema_file") or "")
                meta["file_size"] = entry_file_size_label(replacement)
                meta["sha256"] = str(replacement.get("sha256") or "")
                meta["achievement_count"] = str(replacement.get("achievement_count") or "")
                meta["languages"] = list(replacement.get("languages", []))
            else:
                meta["schema_file"], meta["schema_files"] = rename_schema_variants(old_game_id, value, meta)
            meta["game_id"] = value
            meta["store_url"] = steam_store_url(value)
            validate_store_url(value, str(meta["store_url"]))
            rows, coverage = validate_metadata_variants(meta, list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            meta["file_size"] = schema_file_size_label(schema_file_size_bytes(str(meta["schema_file"])))
            meta["sha256"] = sha256(repository_path(str(meta["schema_file"])).read_bytes())
            meta["achievement_count"] = str(len(rows))
            meta["updated_at"] = now_utc()
            update_diff = None
            record_change("Steam app ID", old_game_id, meta["game_id"])
            if kind != "outdated":
                record_change("Steam store URL", previous_store_url, meta["store_url"])
                record_change("schema file", previous_schema_file, meta["schema_file"])
                record_change("file size", previous_file_size, meta["file_size"])
                record_change("SHA-256", previous_hash, meta["sha256"])
                record_change("achievement count", previous_count, meta["achievement_count"])
                record_change("updated at", previous_updated_at, meta["updated_at"])
        elif command == "name":
            if not value:
                raise ValueError("`/update name` 后面必须填写游戏名。")
            previous_name = str(meta.get("game_name") or "")
            meta["game_name"] = value
            if kind == "outdated":
                rows, coverage = [], {}
            else:
                rows, coverage = validate_metadata_variants(meta, list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            if kind != "outdated":
                record_change("game name", previous_name, meta["game_name"])
        elif command == "summary":
            if not value:
                raise ValueError("`/update summary` 后面必须填写更新摘要。")
            previous_summary = str(meta.get("update_summary") or "")
            meta["update_summary"] = value
            rows, coverage = validate_metadata_variants(meta, list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            record_change("update summary", previous_summary, meta["update_summary"])
        elif command in {"type", "reason", "reference"}:
            if kind != "outdated":
                raise ValueError(f"`/update {command}` 只适用于报告错误 PR。")
            rows, coverage = [], {}
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
        else:
            raise ValueError("不支持的 `/update` 命令。")

        if kind == "outdated":
            entry = existing_entry(load_index(), old_game_id) or {}
            if not entry:
                raise ValueError("找不到该 PR 对应的索引条目。")
            entry = reported_entry_from_metadata(entry, meta)
            report = entry_problem_report(entry)
            if command == "id":
                entry["game_id"] = meta["game_id"]
            if command == "name":
                record_change("game name", entry.get("game_name", ""), meta["game_name"])
                entry["game_name"] = meta["game_name"]
            if command == "type":
                previous_type = str(report.get("type") or entry.get("status") or "outdated")
                new_type = report_state(value)
                record_change("report type", previous_type, new_type)
                report["type"] = new_type
                entry["status"] = new_type
            if command == "reason":
                record_change("report reason", report.get("reason", ""), value)
                report["reason"] = value
            if command == "reference":
                record_change("report reference", report.get("reference", ""), value)
                report["reference"] = value
            entry["report"] = report
            entry.pop("outdated", None)
            report_path = write_pending_report(entry, source_issue_number(pr) or pr_number)
            pr_title = f"Report achievement translation issue for {entry['game_name']} ({entry['game_id']})"
            pr_body = build_outdated_body(entry, meta)
        else:
            validate_store_url(str(meta["game_id"]), str(meta["store_url"]))
            entry = entry_from_metadata(meta)
            entry["achievement_count"] = int(str(meta["achievement_count"]))
            rows_by_variant = variant_achievement_rows(entry, list(meta["languages"]))
            pr_title = f"{'Update' if kind == 'update' else 'Add'} achievement translations for {meta['game_name']} ({meta['game_id']})"
            pr_body = build_submission_pr_body(
                kind=kind,
                entry=entry,
                coverage=coverage,
                rows=rows,
                languages=list(meta["languages"]),
                update_summary=str(meta.get("update_summary") or "Updated from PR comment."),
                update_diff=update_diff,
                previous_hash=previous_hash,
                issue_url=str(meta.get("source_issue") or ""),
                contributor_notes=str(meta.get("contributor_notes") or ""),
                review_variant_id=review_variant_id,
                review_variant_hash=review_variant_hash,
                variant_changes=variant_changes,
                rows_by_variant=rows_by_variant,
            )
    except Exception as exc:  # noqa: BLE001 - user-facing automation report.
        comment_issue(repo, token, pr_number, update_error_comment(str(exc)))
        return

    add_paths = [report_path] if kind == "outdated" else ["files"]
    changed = commit_and_push(branch, f"data: apply PR update command #{pr_number}", add_paths)
    update_pr_title_and_body(repo, token, pr_number, pr_title, pr_body)
    suffix = "投稿分支和 PR 描述已更新。" if changed else "PR 描述已更新；文件内容没有产生新的提交。"
    if not changes:
        changes.append({"field": "requested update", "before": "未记录", "after": "已处理"})
    comment_issue(repo, token, pr_number, update_success_comment(command_text, suffix, changes))


def clear_wait_for_update_from_comment(repo: str, token: str, event: dict[str, Any]) -> None:
    issue = event.get("issue") or {}
    if WAIT_FOR_UPDATE_LABEL not in pr_labels(issue):
        return
    if not comment_is_authorized(event):
        return
    remove_issue_label(repo, token, int(issue["number"]), WAIT_FOR_UPDATE_LABEL)


def handle_comment(repo: str, token: str, event: dict[str, Any]) -> None:
    if handle_pr_close(repo, token, event):
        return
    body = str((event.get("comment") or {}).get("body") or "").strip()
    if is_force_refresh_command(body):
        force_refresh_pr(repo, token, event)
        return
    clear_wait_for_update_from_comment(repo, token, event)
    if is_update_command(body):
        apply_pr_update(repo, token, event)


def mark_wait_for_update(repo: str, token: str, event: dict[str, Any]) -> None:
    pr = event.get("pull_request") or {}
    pr_number = int(pr["number"])
    add_issue_label(repo, token, pr_number, WAIT_FOR_UPDATE_LABEL)
