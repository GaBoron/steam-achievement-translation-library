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
    repository_path,
    require_language_coverage,
    save_schema_package,
    schema_file_size_bytes,
    schema_file_size_label,
    schema_variant_relative_path,
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
)

ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = ROOT / "files"
WAIT_FOR_UPDATE_LABEL = "等待更新"
BOT_USERS = {"github-actions[bot]"}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
UPDATE_LABELS = {"更新文件", "update"}
OUTDATED_LABELS = {"报告过期", "outdated"}
TRANSLATION_PETITION_LABEL = "翻译请愿"
TRANSLATION_PETITION_FULFILLED_MARKER = "translation-library-petition-fulfilled"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        command = " ".join(args)
        print(f"Command failed: {command}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        result.check_returncode()
    return result


def configure_git_identity() -> None:
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])


def github_request(
    method: str,
    repo: str,
    token: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_404: bool = False,
    allow_422: bool = False,
) -> Any:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-achievement-translation-library-pr-maintenance",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else None
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        if allow_422 and exc.code == 422:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed with HTTP {exc.code}: {detail}") from exc


def ensure_label(repo: str, token: str, name: str) -> None:
    encoded = urllib.parse.quote(name, safe="")
    if github_request("GET", repo, token, f"/labels/{encoded}", allow_404=True) is not None:
        return
    github_request(
        "POST",
        repo,
        token,
        "/labels",
        {"name": name, "color": "d29922", "description": "维护者要求修改，等待投稿者更新"},
        allow_422=True,
    )


def add_issue_label(repo: str, token: str, issue_number: int, label: str) -> None:
    ensure_label(repo, token, label)
    github_request("POST", repo, token, f"/issues/{issue_number}/labels", {"labels": [label]})


def remove_issue_label(repo: str, token: str, issue_number: int, label: str) -> None:
    encoded = urllib.parse.quote(label, safe="")
    github_request("DELETE", repo, token, f"/issues/{issue_number}/labels/{encoded}", allow_404=True)


def comment_issue(repo: str, token: str, issue_number: int, body: str) -> None:
    github_request("POST", repo, token, f"/issues/{issue_number}/comments", {"body": body})


def comment_issue_once(repo: str, token: str, issue_number: int, body: str, marker: str) -> None:
    comments = github_request("GET", repo, token, f"/issues/{issue_number}/comments?per_page=100") or []
    for comment in comments:
        if marker in str(comment.get("body") or ""):
            return
    comment_issue(repo, token, issue_number, body)


def lock_issue(repo: str, token: str, issue_number: int) -> None:
    github_request("PUT", repo, token, f"/issues/{issue_number}/lock", {"lock_reason": "resolved"}, allow_422=True)


def close_issue(repo: str, token: str, issue_number: int) -> None:
    github_request(
        "PATCH",
        repo,
        token,
        f"/issues/{issue_number}",
        {"state": "closed", "state_reason": "completed"},
    )


def close_pull_request(repo: str, token: str, pr_number: int) -> None:
    github_request("PATCH", repo, token, f"/pulls/{pr_number}", {"state": "closed"})


def issue_comments(repo: str, token: str, issue_number: int) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for page in range(1, 11):
        batch = github_request(
            "GET",
            repo,
            token,
            f"/issues/{issue_number}/comments?per_page=100&page={page}",
        ) or []
        if not isinstance(batch, list):
            raise RuntimeError("GitHub PR comments API 返回了无效数据")
        comments.extend(comment for comment in batch if isinstance(comment, dict))
        if len(batch) < 100:
            return comments
    raise RuntimeError("PR 评论数量超过自动检查上限")


def pr_labels(pr_or_issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name") or "") for label in pr_or_issue.get("labels", []) if isinstance(label, dict)}


def pr_kind(pr: dict[str, Any]) -> str:
    labels = pr_labels(pr)
    if labels & OUTDATED_LABELS:
        return "outdated"
    if labels & UPDATE_LABELS:
        return "update"
    body = str(pr.get("body") or "")
    if "## Outdated Translation Report" in body:
        return "outdated"
    if "## Translation Library Update" in body:
        return "update"
    return "translation-contribution"


def is_bot(actor: str) -> bool:
    return actor in BOT_USERS or actor.endswith("[bot]")


def comment_actor(event: dict[str, Any]) -> str:
    return str(((event.get("comment") or {}).get("user") or {}).get("login") or "")


def comment_is_authorized(event: dict[str, Any]) -> bool:
    comment = event.get("comment") or {}
    actor = comment_actor(event)
    if not actor or is_bot(actor):
        return False
    association = str(comment.get("author_association") or "").upper()
    if association in TRUSTED_ASSOCIATIONS:
        return True
    issue = event.get("issue") or {}
    try:
        metadata = parse_pr_metadata(issue)
        allowed_users = set(metadata.get("contributors", []))
        reporter = str(metadata.get("reporter") or "")
        if reporter:
            allowed_users.add(reporter)
    except (TypeError, ValueError):
        allowed_users = set()
    return actor in allowed_users


def source_issue_number(pr: dict[str, Any]) -> int:
    try:
        source_issue = str(parse_pr_metadata(pr).get("source_issue") or "")
    except (TypeError, ValueError):
        return 0
    match = re.search(r"/issues/(\d+)(?:[/?#]|$)", source_issue)
    return int(match.group(1)) if match else 0


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


def strip_inline_code(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        return text[1:-1].strip()
    return text


def body_field(body: str, label: str) -> str:
    pattern = re.compile(rf"^- {re.escape(label)}:\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(body)
    return strip_inline_code(match.group(1)) if match else ""


def split_languages(value: str) -> list[str]:
    text = value.strip().lower()
    if any(separator in text for separator in [";", "；", "，"]):
        raise ValueError("语言代码必须使用半角逗号 `,` 分隔。")
    return sorted({item.strip() for item in text.split(",") if item.strip()})


def parse_pr_metadata(pr: dict[str, Any]) -> dict[str, Any]:
    body = str(pr.get("body") or "")
    contributor_value = body_field(body, "Contributors")
    contributors = [item.strip().lstrip("@") for item in contributor_value.split(",") if item.strip()]
    languages = split_languages(body_field(body, "Supported languages"))
    schema_files = parse_schema_variants_marker(body)
    return {
        "kind": pr_kind(pr),
        "game_name": body_field(body, "Game name"),
        "game_id": body_field(body, "Steam app ID"),
        "store_url": body_field(body, "Steam store URL"),
        "contributors": contributors,
        "source_issue": body_field(body, "Source issue"),
        "reporter": body_field(body, "Reporter").lstrip("@"),
        "languages": languages,
        "achievement_count": body_field(body, "Achievement count"),
        "schema_file": body_field(body, "Schema file") or body_field(body, "Current schema file"),
        "schema_files": schema_files,
        "file_size": body_field(body, "File size") or body_field(body, "Current file size"),
        "sha256": body_field(body, "SHA-256") or body_field(body, "Current SHA-256"),
        "submitted_at": body_field(body, "Submitted at"),
        "updated_at": body_field(body, "Updated at") or body_field(body, "Last library update"),
        "update_summary": body_field(body, "Contributor summary"),
        "reason": section_after_heading(body, "## Reason"),
        "reference": section_after_heading(body, "## Reference"),
    }


def section_after_heading(body: str, heading: str) -> str:
    if heading not in body:
        return ""
    tail = body.split(heading, 1)[1].strip()
    match = re.search(r"\n##\s+", tail)
    if match:
        tail = tail[:match.start()].strip()
    return tail.strip()


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
    "store": "store",
    "url": "store",
    "store_url": "store",
    "languages": "languages",
    "language": "languages",
    "lang": "languages",
    "summary": "summary",
    "note": "summary",
    "reason": "reason",
    "reference": "reference",
    "ref": "reference",
}
UPDATE_VALUE_COMMANDS = {"id", "name", "store", "languages", "summary", "reason", "reference"}
UPDATE_COMMAND_HELP = (
    "支持的类型：`doc`、`id`、`name`、`store`、`languages`、`summary`、`reason`、`reference`。"
)
UPDATE_COMMANDS_BY_KIND = {
    "translation-contribution": {"doc", "id", "name", "store", "languages"},
    "update": {"doc", "id", "name", "store", "languages", "summary"},
    "outdated": {"name", "store", "reason", "reference"},
}


def update_first_line(body: str) -> str:
    return body.strip().splitlines()[0].strip() if body.strip() else ""


def is_update_command(body: str) -> bool:
    first = update_first_line(body).lower()
    return first == "/update" or first.startswith("/update ")


def parse_update_command_detail(body: str) -> tuple[str, str, str]:
    first = update_first_line(body)
    if not is_update_command(body):
        return "", "", ""
    rest = first[len("/update"):].strip()
    if not rest:
        return "", "", "`/update` 后面必须写明类型，例如 `/update doc` 或 `/update name <游戏名>`。"
    parts = rest.split(maxsplit=1)
    raw_command = parts[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ""
    command = UPDATE_COMMAND_ALIASES.get(raw_command, "")
    if not command:
        return "", "", f"不支持的 `/update {parts[0]}` 类型。{UPDATE_COMMAND_HELP}"
    if command in UPDATE_VALUE_COMMANDS and not value:
        return "", "", f"`/update {raw_command}` 后面缺少参数。{UPDATE_COMMAND_HELP}"
    return command, value, ""


def parse_update_command(body: str) -> tuple[str, str]:
    command, value, error = parse_update_command_detail(body)
    if error:
        return "", ""
    return command, value


def checkout_pr_branch(pr: dict[str, Any]) -> str:
    branch = str((pr.get("head") or {}).get("ref") or "")
    if not branch.startswith("translation-library/"):
        raise RuntimeError("Only translation-library PR branches can be updated by automation.")
    configure_git_identity()
    run(["git", "fetch", "origin", "main"], check=False)
    run(["git", "fetch", "origin", branch], check=False)
    run(["git", "checkout", "-B", branch, f"origin/{branch}"])
    run(["git", "rebase", "origin/main"])
    return branch


def validate_store_url(game_id: str, store_url: str) -> None:
    store_id = steam_store_id(store_url)
    if not store_id:
        raise ValueError("Steam 商店地址必须是 store.steampowered.com/app/<id>/ 格式。")
    if store_id != game_id:
        raise ValueError(f"Steam 商店地址中的 app ID {store_id} 与 Steam app ID {game_id} 不一致。")


def validate_languages_for_schema(schema_file: str, languages: list[str]) -> tuple[list[dict[str, str]], dict[str, int]]:
    invalid = [language for language in languages if not LANGUAGE_RE.fullmatch(language)]
    if invalid:
        raise ValueError("无效的 Steam 语言代码：" + ", ".join(invalid))
    if not languages:
        raise ValueError("至少填写一个 Steam 语言代码。")
    data, nodes = load_schema(repository_path(schema_file))
    validate_schema_structure(data, nodes)
    rows = achievement_rows(nodes, languages)
    coverage = require_language_coverage(rows, languages)
    return rows, coverage


def validate_metadata_variants(meta: dict[str, Any], languages: list[str]) -> tuple[list[dict[str, str]], dict[str, int]]:
    entry = {
        "schema_file": meta.get("schema_file"),
        "schema_files": meta.get("schema_files"),
        "file_size_bytes": 0,
        "sha256": meta.get("sha256"),
        "achievement_count": meta.get("achievement_count"),
    }
    variants = validated_entry_schema_variants(entry)
    if not variants:
        raise ValueError("PR 描述中没有可用的 schema 版本元数据。")
    primary_result: tuple[list[dict[str, str]], dict[str, int]] | None = None
    for variant in variants:
        result = validate_languages_for_schema(str(variant["schema_file"]), languages)
        if variant.get("primary"):
            primary_result = result
    if primary_result is None:
        raise ValueError("PR 的 schema 版本元数据缺少主版本。")
    return primary_result


def remove_index_entries(game_ids: set[str]) -> dict[str, Any]:
    index = load_index()
    index["entries"] = [entry for entry in index.get("entries", []) if str(entry.get("game_id")) not in game_ids]
    write_index(index)
    write_human_index(index)
    return index


def upsert_entry_for_pr(old_game_id: str, entry: dict[str, Any]) -> None:
    if old_game_id and old_game_id != str(entry.get("game_id")):
        remove_index_entries({old_game_id, str(entry.get("game_id"))})
    upsert_index_entry(entry)


def rename_schema_variants(
    old_game_id: str,
    new_game_id: str,
    meta: dict[str, Any],
) -> tuple[str, list[dict[str, Any]] | None]:
    if old_game_id == new_game_id:
        return str(meta["schema_file"]), meta.get("schema_files")
    schema_files = meta.get("schema_files")
    if schema_files is None:
        indexed = existing_entry(load_index(), old_game_id)
        if indexed and isinstance(indexed.get("schema_files"), list):
            schema_files = entry_schema_variants(indexed)
            for record in schema_files:
                if record.get("primary"):
                    record.update({
                        "schema_file": meta.get("schema_file"),
                        "file_size_bytes": schema_file_size_bytes(str(meta.get("schema_file") or "")),
                        "sha256": meta.get("sha256"),
                        "achievement_count": int(str(meta.get("achievement_count") or 0)),
                    })
    entry = {
        "schema_file": meta.get("schema_file"),
        "schema_files": schema_files,
        "file_size_bytes": 0,
        "sha256": meta.get("sha256"),
        "achievement_count": meta.get("achievement_count"),
    }
    records = validated_entry_schema_variants(entry)
    if not records:
        raise ValueError("当前 PR 没有可重命名的 schema 文件。")
    moves: list[tuple[Path, Path, dict[str, Any]]] = []
    for record in records:
        source = repository_path(str(record["schema_file"]))
        if not source.is_file():
            raise ValueError(f"当前 schema 文件不存在：{record['schema_file']}")
        destination_relative = schema_variant_relative_path(
            new_game_id,
            str(record["variant_id"]),
            bool(record.get("primary")),
        )
        destination = repository_path(destination_relative)
        if destination.exists() and destination != source:
            raise ValueError(f"目标 schema 文件已存在：{destination_relative}")
        updated = dict(record)
        updated["schema_file"] = destination_relative
        moves.append((source, destination, updated))
    for source, destination, _record in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    old_root = (FILES_ROOT / old_game_id).resolve()
    for directory in sorted({source.parent for source, _destination, _record in moves}, key=lambda path: len(path.parts), reverse=True):
        current = directory
        while current != old_root.parent and current.is_relative_to(old_root):
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
    updated_records = [record for _source, _destination, record in moves]
    updated_records.sort(key=lambda record: (not bool(record.get("primary")), str(record.get("variant_id"))))
    primary = next(record for record in updated_records if record.get("primary"))
    keep_records = updated_records if schema_files is not None else None
    return str(primary["schema_file"]), keep_records


def entry_from_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    index_entry = existing_entry(load_index(), str(meta["game_id"])) or {}
    entry = dict(index_entry)
    entry.update({
        "game_name": meta["game_name"],
        "game_id": meta["game_id"],
        "store_url": meta["store_url"],
        "languages": meta["languages"],
        "schema_file": meta["schema_file"],
        "file_size_bytes": schema_file_size_bytes(str(meta["schema_file"])),
        "achievement_count": int(str(meta.get("achievement_count") or "0") or 0),
        "sha256": meta["sha256"],
        "source_issue": meta["source_issue"],
        "contributors": meta.get("contributors", []),
        "contributor_id": (meta.get("contributors") or [""])[0] if meta.get("contributors") else "",
        "submitted_at": meta.get("submitted_at") or now_utc(),
        "updated_at": meta.get("updated_at") or now_utc(),
        "status": "current",
    })
    entry.pop("outdated", None)
    if meta.get("schema_files") is not None:
        entry["schema_files"] = list(meta["schema_files"])
    elif isinstance(entry.get("schema_files"), list):
        # Compatibility for PRs created before machine-readable variant metadata existed.
        records = entry_schema_variants(entry)
        for record in records:
            if record.get("primary"):
                record.update({
                    "schema_file": entry["schema_file"],
                    "file_size_bytes": entry["file_size_bytes"],
                    "sha256": entry["sha256"],
                    "achievement_count": entry["achievement_count"],
                })
        entry["schema_files"] = records
    return entry


def build_outdated_body(entry: dict[str, Any], meta: dict[str, Any]) -> str:
    outdated = entry.get("outdated") if isinstance(entry.get("outdated"), dict) else {}
    return f"""## Outdated Translation Report

- Game name: {entry['game_name']}
- Steam app ID: `{entry['game_id']}`
- Steam store URL: {entry.get('store_url', '')}
- Current schema file: `{entry.get('schema_file', '')}`
- Current file size: {entry_file_size_label(entry)}
- Current SHA-256: `{entry.get('sha256', '')}`
- Last library update: {entry.get('updated_at', '')}
- Source issue: {meta.get('source_issue', '')}
- Reporter: @{outdated.get('reporter_id', '')}
- Reported at: {outdated.get('reported_at', '')}

## Reason

{outdated.get('reason', '')}

## Reference

{outdated.get('reference', '') or 'No external reference provided.'}
"""


def update_pr_title_and_body(repo: str, token: str, pr_number: int, title: str, body: str) -> None:
    github_request("PATCH", repo, token, f"/pulls/{pr_number}", {"title": title, "body": body})


def update_comment_value(value: Any) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value)
    elif value is None:
        text = ""
    else:
        text = str(value)
    text = escape_table(text.strip())
    return text if text else "_空_"


def update_success_comment(command_text: str, result_text: str, changes: list[dict[str, Any]]) -> str:
    lines = [
        "<!-- translation-library-update-success -->",
        "`/update` 已处理完成。",
        "",
        f"- 命令：`{escape_table(command_text)}`",
        f"- 结果：{escape_table(result_text)}",
        "",
        "| 项目 | 原内容 | 更新后 |",
        "| --- | --- | --- |",
    ]
    for change in changes:
        lines.append(
            f"| {escape_table(str(change.get('field') or ''))} | "
            f"{update_comment_value(change.get('before'))} | {update_comment_value(change.get('after'))} |"
        )
    return "\n".join(lines)


def update_error_comment(message: str) -> str:
    return "\n".join([
        "`/update` 未通过检查，PR 未更新。",
        "",
        f"- 错误：{escape_table(message)}",
        "- 用法：`/update <类型> <参数>`。`/update doc` 接收完整包；"
        "`/update doc <variant_id>` 接收指定版本的单文件 ZIP，附件必须在同一条评论中。",
        f"- {UPDATE_COMMAND_HELP}",
    ])


def commit_and_push(branch: str, message: str, add_paths: list[str] | None = None) -> bool:
    configure_git_identity()
    run(["git", "add", *(add_paths or ["files", "index.json", "INDEX.md", "INDEX_EN.md"])])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False
    run(["git", "commit", "-m", message])
    run(["git", "fetch", "origin", branch], check=False)
    push = run(["git", "push", "--force-with-lease", "--set-upstream", "origin", branch], check=False)
    if push.returncode != 0:
        run(["git", "fetch", "origin", branch], check=False)
        run(["git", "push", "--force-with-lease", "--set-upstream", "origin", branch])
    return True


def push_main_with_retry() -> None:
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode == 0:
        return
    run(["git", "fetch", "origin", "main"])
    run(["git", "rebase", "origin/main"])
    run(["git", "push", "origin", "HEAD:main"])


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
            message = "报告过期 PR 仅支持 `name`、`store`、`reason` 和 `reference`。"
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
        if command == "doc":
            if not attachment:
                raise ValueError("`/update doc` 需要在同一条评论中附加 `UserGameStatsSchema_<app_id>.zip`。")
            target_variant_id = value.lower()
            if target_variant_id and not re.fullmatch(r"^[a-z0-9][a-z0-9-]{0,63}$", target_variant_id):
                raise ValueError("variant_id 只能包含小写字母、数字和连字符，最长 64 个字符。")
            package = validate_schema_package(attachment, token, old_game_id, list(meta["languages"]))
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
                old_data, old_nodes = load_schema(repository_path(str(current["schema_file"])))
                uploaded = package.variants[0]
                previous_hash = sha256(old_data)
                if old_data == uploaded.data:
                    raise ValueError(f"上传文件与当前 {target_variant_id} 版本字节级完全相同。")
                update_diff = summarize_update_diff(
                    achievement_rows(old_nodes, list(meta["languages"])),
                    achievement_rows(uploaded.nodes, list(meta["languages"])),
                    list(meta["languages"]),
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
                    update_diff = summarize_update_diff(
                        achievement_rows(old_nodes, list(meta["languages"])),
                        achievement_rows(new_by_id[review_variant_id].nodes, list(meta["languages"])),
                        list(meta["languages"]),
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
            record_change("schema file", previous_schema_file, meta["schema_file"])
            record_change("file size", previous_file_size, meta["file_size"])
            record_change(
                f"{review_variant_id} SHA-256",
                previous_hash or str(original_meta.get("sha256") or ""),
                review_variant_hash,
            )
            record_change("achievement count", previous_count, meta["achievement_count"])
            record_change("updated at", previous_updated_at, meta["updated_at"])
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
                    raise ValueError("报告过期 PR 的 `/update id` 必须指向库里已经收录的 Steam app ID。")
                meta["schema_file"] = str(replacement.get("schema_file") or "")
                meta["file_size"] = entry_file_size_label(replacement)
                meta["sha256"] = str(replacement.get("sha256") or "")
                meta["achievement_count"] = str(replacement.get("achievement_count") or "")
                meta["languages"] = list(replacement.get("languages", []))
            else:
                meta["schema_file"], meta["schema_files"] = rename_schema_variants(old_game_id, value, meta)
            meta["game_id"] = value
            if old_game_id and old_game_id in str(meta["store_url"]):
                meta["store_url"] = str(meta["store_url"]).replace(f"/app/{old_game_id}", f"/app/{value}")
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
        elif command == "store":
            previous_store_url = str(meta.get("store_url") or "")
            validate_store_url(str(meta["game_id"]), value)
            meta["store_url"] = value
            if kind == "outdated":
                rows, coverage = [], {}
            else:
                rows, coverage = validate_metadata_variants(meta, list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            if kind != "outdated":
                record_change("Steam store URL", previous_store_url, meta["store_url"])
        elif command == "languages":
            previous_languages = list(meta.get("languages") or [])
            languages = split_languages(value)
            rows, coverage = validate_metadata_variants(meta, languages)
            meta["languages"] = languages
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            record_change("supported languages", previous_languages, meta["languages"])
        elif command == "summary":
            if not value:
                raise ValueError("`/update summary` 后面必须填写更新摘要。")
            previous_summary = str(meta.get("update_summary") or "")
            meta["update_summary"] = value
            rows, coverage = validate_metadata_variants(meta, list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            record_change("update summary", previous_summary, meta["update_summary"])
        elif command in {"reason", "reference"}:
            if kind != "outdated":
                raise ValueError(f"`/update {command}` 只适用于报告过期 PR。")
            rows, coverage = [], {}
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
        else:
            raise ValueError("不支持的 `/update` 命令。")

        if kind == "outdated":
            entry = existing_entry(load_index(), old_game_id) or {}
            if not entry:
                raise ValueError("找不到该 PR 对应的索引条目。")
            outdated = entry.get("outdated") if isinstance(entry.get("outdated"), dict) else {}
            if command == "id":
                entry["game_id"] = meta["game_id"]
            if command == "name":
                record_change("game name", entry.get("game_name", ""), meta["game_name"])
                entry["game_name"] = meta["game_name"]
            if command == "store":
                record_change("Steam store URL", entry.get("store_url", ""), meta["store_url"])
                entry["store_url"] = meta["store_url"]
            if command == "reason":
                record_change("outdated reason", outdated.get("reason", ""), value)
                outdated["reason"] = value
            if command == "reference":
                record_change("outdated reference", outdated.get("reference", ""), value)
                outdated["reference"] = value
            entry["outdated"] = outdated
            upsert_entry_for_pr(old_game_id, entry)
            pr_title = f"Mark achievement translations for {entry['game_name']} ({entry['game_id']}) as outdated"
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
                review_variant_id=review_variant_id,
                review_variant_hash=review_variant_hash,
                variant_changes=variant_changes,
                rows_by_variant=rows_by_variant,
            )
    except Exception as exc:  # noqa: BLE001 - user-facing automation report.
        comment_issue(repo, token, pr_number, update_error_comment(str(exc)))
        return

    add_paths = ["index.json", "INDEX.md", "INDEX_EN.md"] if kind == "outdated" else ["files"]
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
    clear_wait_for_update_from_comment(repo, token, event)
    body = str((event.get("comment") or {}).get("body") or "").strip()
    if is_update_command(body):
        apply_pr_update(repo, token, event)


def mark_wait_for_update(repo: str, token: str, event: dict[str, Any]) -> None:
    pr = event.get("pull_request") or {}
    pr_number = int(pr["number"])
    add_issue_label(repo, token, pr_number, WAIT_FOR_UPDATE_LABEL)


def mark_source_pr(event: dict[str, Any], repo: str, token: str) -> bool:
    pr = event.get("pull_request") or {}
    labels = pr_labels(pr)
    body = str(pr.get("body") or "")
    game_id = body_field(body, "Steam app ID")
    if not game_id:
        return False

    index = load_index()
    entry = next((item for item in index.get("entries", []) if str(item.get("game_id")) == game_id), None)

    pr_url = str(pr.get("html_url") or "")
    merged_at = str(pr.get("merged_at") or "")
    changed = False

    if labels & OUTDATED_LABELS:
        if not entry:
            return False
        outdated = entry.get("outdated") if isinstance(entry.get("outdated"), dict) else {}
        if pr_url and outdated.get("source_pr") != pr_url:
            outdated["source_pr"] = pr_url
            entry["outdated"] = outdated
            changed = True
    else:
        meta = parse_pr_metadata(pr)
        entry = entry_from_metadata(meta)
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
            rows = achievement_rows(nodes, list(entry.get("languages", [])))
            require_language_coverage(rows, list(entry.get("languages", [])))
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
    run(["git", "add", "index.json", "INDEX.md", "INDEX_EN.md"])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False
    run(["git", "commit", "-m", f"data: record source PR for translation entry #{int(pr.get('number') or 0)}"])
    push_main_with_retry()
    return True


def delete_pr_branch(repo: str, token: str, pr: dict[str, Any]) -> None:
    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
    if str(head_repo.get("full_name") or "") != repo:
        return
    branch = str(head.get("ref") or "")
    if not branch.startswith("translation-library/"):
        return
    encoded = urllib.parse.quote(branch, safe="/")
    github_request("DELETE", repo, token, f"/git/refs/heads/{encoded}", allow_404=True, allow_422=True)


def merged_thanks_comment(pr: dict[str, Any]) -> str:
    meta = parse_pr_metadata(pr)
    kind = pr_kind(pr)
    contributors = [f"@{contributor}" for contributor in meta.get("contributors", []) if contributor]
    contributor_text = "、".join(contributors) if contributors else "本次贡献者"
    game_name = str(meta.get("game_name") or "该游戏")
    game_id = str(meta.get("game_id") or "")
    game_text = f"{game_name}（{game_id}）" if game_id else game_name
    source_issue = str(meta.get("source_issue") or "")

    if kind == "outdated":
        action_text = f"已将 {game_text} 标记为可能过期，并同步到翻译库索引。"
        follow_up = "如果之后准备好了新版成就文件，可以直接提交“更新已有 Steam 成就翻译”issue。"
    elif kind == "update":
        action_text = f"已合并 {game_text} 的成就翻译更新，并同步到翻译库索引。"
        follow_up = "后续如果游戏再次更新或发现翻译需要修正，可以继续提交更新 issue。"
    else:
        action_text = f"已收录 {game_text} 的 Steam 成就翻译文件，并同步到翻译库索引。"
        follow_up = "后续如果游戏更新导致 schema 变化，可以提交“更新已有 Steam 成就翻译”或“报告成就文件过期”。"

    lines = [
        "<!-- translation-library-merged-thanks -->",
        f"感谢 {contributor_text} 的贡献！",
        "",
        action_text,
        follow_up,
    ]
    if source_issue:
        lines.extend(["", f"来源 issue：{source_issue}"])
    return "\n".join(lines)


def translation_petition_game_id(issue: dict[str, Any]) -> str:
    fields = parse_issue_form(str(issue.get("body") or ""))
    return first_line(field_value(fields, ["Steam app ID"]))


def open_translation_petitions(repo: str, token: str) -> list[dict[str, Any]]:
    petitions: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "state": "open",
            "labels": TRANSLATION_PETITION_LABEL,
            "per_page": "100",
            "page": str(page),
        })
        batch = github_request("GET", repo, token, f"/issues?{query}") or []
        petitions.extend(
            issue for issue in batch
            if not issue.get("pull_request") and TRANSLATION_PETITION_LABEL in pr_labels(issue)
        )
        if len(batch) < 100:
            break
        page += 1
    return petitions


def fulfilled_petition_comment(meta: dict[str, Any], repo: str) -> str:
    contributors = [f"@{item}" for item in meta.get("contributors", []) if item]
    contributor_text = "、".join(contributors) if contributors else "贡献者"
    game_name = str(meta.get("game_name") or "该游戏")
    game_id = str(meta.get("game_id") or "")
    schema_file = str(meta.get("schema_file") or "")
    filename = Path(schema_file).name or f"UserGameStatsSchema_{game_id}.bin"
    download_url = f"https://github.com/{repo}/raw/refs/heads/main/{urllib.parse.quote(schema_file, safe='/')}"
    return "\n".join([
        f"<!-- {TRANSLATION_PETITION_FULFILLED_MARKER} -->",
        f"你请愿的 {game_name}（Steam app ID `{game_id}`）翻译已由 {contributor_text} 上传并通过审核，现在可以下载了。",
        "",
        f"[下载 `{filename}`]({download_url})",
    ])


def notify_fulfilled_translation_petitions(pr: dict[str, Any], repo: str, token: str) -> int:
    if pr_kind(pr) != "translation-contribution":
        return 0
    meta = parse_pr_metadata(pr)
    game_id = str(meta.get("game_id") or "")
    if not game_id:
        return 0
    body = fulfilled_petition_comment(meta, repo)
    notified = 0
    for petition in open_translation_petitions(repo, token):
        if translation_petition_game_id(petition) != game_id:
            continue
        issue_number = int(petition["number"])
        comment_issue_once(
            repo,
            token,
            issue_number,
            body,
            TRANSLATION_PETITION_FULFILLED_MARKER,
        )
        close_issue(repo, token, issue_number)
        notified += 1
    return notified


def finalize_merged_pr(event: dict[str, Any], repo: str, token: str) -> None:
    pr = event.get("pull_request") or {}
    pr_number = int(pr["number"])
    comment_issue_once(
        repo,
        token,
        pr_number,
        merged_thanks_comment(pr),
        "translation-library-merged-thanks",
    )
    notify_fulfilled_translation_petitions(pr, repo, token)
    delete_pr_branch(repo, token, pr)
    lock_issue(repo, token, pr_number)


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
