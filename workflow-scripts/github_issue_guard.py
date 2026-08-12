#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from issue_commands import (
    close_comment_is_authorized,
    comment_is_authorized,
    escape_table,
    extract_attachment_markdown,
    is_force_refresh_command,
    is_update_command,
    parse_update_command,
    replace_section,
    section_value,
    update_error_comment,
    update_first_line,
    update_success_comment,
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

LABELS = {
    "翻译投稿": {
        "color": "2da44e",
        "description": "新的 Steam 成就翻译投稿",
    },
    "更新文件": {
        "color": "0969da",
        "description": "更新已收录的成就翻译文件",
    },
    "报告错误": {
        "color": "bf8700",
        "description": "报告已收录文件可能过期或可能不生效",
    },
    "等待更新": {
        "color": "d29922",
        "description": "维护者要求修改，等待投稿者更新",
    },
    "功能请愿": {
        "color": "a2eeef",
        "description": "请求翻译库、投稿流程或自动化支持的新功能",
    },
    "翻译请愿": {
        "color": "d4c5f9",
        "description": "请求社区翻译指定 Steam 游戏的成就 schema",
    },
}

KIND_LABELS = {
    "translation-contribution": "翻译投稿",
    "update": "更新文件",
    "outdated": "报告错误",
    "translation-petition": "翻译请愿",
}
LEGACY_LABELS = {
    "translation-contribution": "translation-contribution",
    "update": "update",
    "outdated": "outdated",
    "translation-petition": "translation-petition",
}
FIELD_LABELS = {
    "id": ["Steam app ID"],
    "name": ["游戏名", "Game name"],
    "summary": ["更新内容摘要", "Update summary"],
    "type": ["错误类型", "Issue type"],
    "reason": ["错误说明", "Issue details", "过期说明", "Why do you think the file is outdated?"],
    "reference": ["参考来源", "Reference or source"],
    "notes": ["备注", "Notes"],
    "doc": ["成就 schema ZIP", "Uploaded achievement schema ZIP", "Achievement schema ZIP"],
    "variant": ["要更新的版本 ID", "Version ID to update"],
}
ATTACHMENT_RE = re.compile(
    r"\[([^\]]+)\]\((https://github\.com/user-attachments/[^\s)]+)\)|(?<!\()(?P<url>https://github\.com/user-attachments/[^\s)]+)"
)
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def github_request(
    method: str,
    repo: str,
    token: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_404: bool = False,
    allow_422: bool = False,
    api_version: str = "2022-11-28",
) -> dict[str, Any] | None:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-achievement-translation-library-issue-guard",
        "X-GitHub-Api-Version": api_version,
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
    config = LABELS[name]
    github_request(
        "POST",
        repo,
        token,
        "/labels",
        {"name": name, "color": config["color"], "description": config["description"]},
        allow_422=True,
    )


def issue_labels(issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name") or "") for label in issue.get("labels", []) if isinstance(label, dict)}


def issue_text(issue: dict[str, Any]) -> str:
    return f"{issue.get('title') or ''}\n{issue.get('body') or ''}"


def infer_issue_kind(issue: dict[str, Any]) -> str | None:
    labels = issue_labels(issue)
    for kind, label in KIND_LABELS.items():
        if label in labels or LEGACY_LABELS[kind] in labels or (kind == "outdated" and "报告过期" in labels):
            return kind
    text = issue_text(issue)
    if any(heading in text for heading in ("### 错误类型", "### Issue type", "### 错误说明", "### Issue details", "### 过期说明", "### Why do you think the file is outdated?")):
        return "outdated"
    if "### 更新内容摘要" in text or "### Update summary" in text:
        return "update"
    if "### 需要翻译的成就 schema ZIP" in text or "### Achievement schema ZIP to translate" in text:
        return "translation-petition"
    if "### 成就 schema ZIP" in text or "### Uploaded achievement schema ZIP" in text:
        return "translation-contribution"
    return None


def issue_game_id(issue: dict[str, Any]) -> str:
    value = section_value(str(issue.get("body") or ""), FIELD_LABELS["id"])
    first = value.strip().splitlines()[0].strip() if value.strip() else ""
    return first if re.fullmatch(r"\d+", first) else ""


def list_open_issues(repo: str, token: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for page in range(1, 11):
        query = urllib.parse.urlencode({
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": "100",
            "page": str(page),
        })
        batch = github_request("GET", repo, token, f"/issues?{query}") or []
        if not isinstance(batch, list):
            raise RuntimeError("GitHub open issues API 返回了无效数据")
        issues.extend(issue for issue in batch if isinstance(issue, dict))
        if len(batch) < 100:
            return issues
    raise RuntimeError("open issue 数量超过自动检查上限")


def older_open_duplicate_issues(current: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_number = int(current.get("number") or 0)
    current_kind = infer_issue_kind(current)
    game_id = issue_game_id(current)
    if not current_number or not current_kind or not game_id:
        return []
    duplicates: list[dict[str, Any]] = []
    for issue in issues:
        if "pull_request" in issue or str(issue.get("state") or "") != "open":
            continue
        issue_number = int(issue.get("number") or 0)
        if not issue_number or issue_number >= current_number:
            continue
        if infer_issue_kind(issue) != current_kind or issue_game_id(issue) != game_id:
            continue
        duplicates.append(issue)
    return sorted(duplicates, key=lambda issue: int(issue.get("number") or 0))


def close_duplicate_issue(repo: str, token: str, issue_number: int, canonical_issue_id: int) -> None:
    github_request(
        "PATCH",
        repo,
        token,
        f"/issues/{issue_number}",
        {
            "state": "closed",
            "state_reason": "duplicate",
            "duplicate_issue_id": canonical_issue_id,
        },
        api_version="2026-03-10",
    )


def revalidate_open_duplicate_issue(
    repo: str,
    token: str,
    current: dict[str, Any],
    issue_number: int,
) -> dict[str, Any] | None:
    latest = github_request("GET", repo, token, f"/issues/{issue_number}")
    if not isinstance(latest, dict):
        return None
    matches = older_open_duplicate_issues(current, [latest])
    return matches[0] if matches else None


def close_older_duplicate_issues(repo: str, token: str, event: dict[str, Any]) -> list[int]:
    if str(event.get("action") or "") != "opened":
        return []
    current = event.get("issue") or {}
    if "pull_request" in current or str(current.get("state") or "") != "open":
        return []
    canonical_issue_id = int(current.get("id") or 0)
    current_number = int(current.get("number") or 0)
    if not canonical_issue_id or not current_number:
        return []
    game_id = issue_game_id(current)
    if not game_id or not infer_issue_kind(current):
        return []
    duplicates = older_open_duplicate_issues(current, list_open_issues(repo, token))
    closed: list[int] = []
    for duplicate in duplicates:
        issue_number = int(duplicate["number"])
        latest = revalidate_open_duplicate_issue(repo, token, current, issue_number)
        if latest is None:
            continue
        close_duplicate_issue(repo, token, issue_number, canonical_issue_id)
        closed.append(issue_number)
        try:
            comment_issue(
                repo,
                token,
                issue_number,
                "\n".join([
                    "<!-- translation-library-duplicate-issue -->",
                    f"此 issue 已由更新的同类型投稿 #{current_number} 替代，因此被标记为重复项并自动关闭。",
                    "",
                    f"- Steam app ID：`{game_id}`",
                    f"- 保留的 issue：#{current_number}",
                    "- 自动化只关闭当时仍为 open 的旧 issue。",
                ]),
            )
        except RuntimeError as exc:
            print(f"Warning: duplicate issue #{issue_number} was closed but could not be commented: {exc}")
    return closed


def add_issue_labels(repo: str, token: str, issue_number: int, labels: list[str]) -> None:
    for label in labels:
        ensure_label(repo, token, label)
    github_request("POST", repo, token, f"/issues/{issue_number}/labels", {"labels": labels})


def comment_issue(repo: str, token: str, issue_number: int, body: str) -> None:
    github_request("POST", repo, token, f"/issues/{issue_number}/comments", {"body": body})


def patch_issue_body(repo: str, token: str, issue_number: int, body: str) -> None:
    github_request("PATCH", repo, token, f"/issues/{issue_number}", {"body": body})


def close_issue(repo: str, token: str, issue_number: int) -> None:
    github_request(
        "PATCH",
        repo,
        token,
        f"/issues/{issue_number}",
        {"state": "closed", "state_reason": "not_planned"},
    )


def lock_issue(repo: str, token: str, issue_number: int) -> None:
    github_request("PUT", repo, token, f"/issues/{issue_number}/lock", {"lock_reason": "resolved"}, allow_422=True)


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
            raise RuntimeError("GitHub issue comments API 返回了无效数据")
        comments.extend(comment for comment in batch if isinstance(comment, dict))
        if len(batch) < 100:
            return comments
    raise RuntimeError("issue 评论数量超过自动检查上限")


def handle_issue_force_refresh(repo: str, token: str, event: dict[str, Any]) -> bool:
    issue = event.get("issue") or {}
    comment_body = str((event.get("comment") or {}).get("body") or "")
    if not is_force_refresh_command(comment_body):
        return False
    issue_number = int(issue["number"])
    if not comment_is_authorized(event):
        comment_issue(repo, token, issue_number, "`/force-refresh` 只能由 issue 投稿者或仓库维护者执行。")
        return True
    if str(issue.get("state") or "") != "open":
        comment_issue(repo, token, issue_number, "`/force-refresh` 只能用于打开状态的投稿 issue。")
        return True
    if not infer_issue_kind(issue):
        comment_issue(repo, token, issue_number, "`/force-refresh` 只适用于翻译投稿、更新文件、报告错误或翻译请愿 issue。")
        return True
    comment_issue(
        repo,
        token,
        issue_number,
        "\n".join([
            "<!-- translation-library-force-refresh -->",
            "已接收 `/force-refresh` 命令。",
            "",
            "- 机器人将基于 issue 当前内容重新运行检查与校对流程。",
            "- 检查通过后会重新进入创建 PR 和推送流程；未通过时会发布新的检查报告。",
        ]),
    )
    return True


def handle_issue_close(repo: str, token: str, event: dict[str, Any]) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    comment_body = str(comment.get("body") or "")
    if not is_close_command(comment_body):
        return False
    issue_number = int(issue["number"])
    if not close_comment_is_authorized(event):
        comment_issue(repo, token, issue_number, close_command_error("`/close` 只能由该 issue 的原投稿者执行。"))
        return True
    if str(issue.get("state") or "") != "open":
        comment_issue(repo, token, issue_number, close_command_error("`/close` 只能用于打开状态的 issue。"))
        return True
    action, reason, error = parse_close_command(comment_body)
    if error:
        comment_issue(repo, token, issue_number, close_command_error(error))
        return True
    actor = str((comment.get("user") or {}).get("login") or "")
    if action == "request":
        comment_issue(repo, token, issue_number, close_request_comment(actor, reason, "issue"))
        return True
    comments = issue_comments(repo, token, issue_number)
    request = latest_close_request(comments, actor)
    if request is None:
        comment_issue(repo, token, issue_number, close_command_error("没有找到你尚待确认的关闭请求。请先输入 `/close 关闭原因`。"))
        return True
    if not confirmation_follows_reply(comment, request):
        comment_issue(repo, token, issue_number, close_command_error("必须等待机器人确认回复出现后，再新建评论输入 `/close confirm`。"))
        return True
    comment_issue(repo, token, issue_number, close_completed_comment(actor, request["reason"], "issue"))
    close_issue(repo, token, issue_number)
    lock_issue(repo, token, issue_number)
    return True


def apply_issue_update(repo: str, token: str, event: dict[str, Any]) -> None:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    issue_number = int(issue["number"])
    comment_body = str(comment.get("body") or "")
    if is_update_command(comment_body) and not comment_is_authorized(event):
        comment_issue(repo, token, issue_number, "`/update` 只能由 issue 投稿者或仓库维护者执行。")
        return
    command, value, error = parse_update_command(comment_body)
    if error:
        comment_issue(repo, token, issue_number, update_error_comment(error))
        return
    if not command:
        return
    if str(issue.get("state") or "") != "open":
        comment_issue(repo, token, issue_number, update_error_comment("`/update` 只能用于打开状态的 issue。"))
        return
    issue_kind = infer_issue_kind(issue)
    if (command == "variant" or (command == "doc" and value)) and issue_kind != "update":
        comment_issue(repo, token, issue_number, update_error_comment("版本 ID 只适用于更新已有文件的 issue。"))
        return

    latest_issue = github_request("GET", repo, token, f"/issues/{issue_number}") or issue
    body = str(latest_issue.get("body") or "")
    changes: list[dict[str, str]] = []

    try:
        if command == "doc":
            new_value = extract_attachment_markdown(comment_body)
            body, before, after = replace_section(body, FIELD_LABELS["doc"], new_value)
            changes.append({"field": "成就 schema ZIP", "before": before, "after": after})
            if value:
                variant_id = value.lower()
                if not re.fullmatch(r"^[a-z0-9][a-z0-9-]{0,63}$", variant_id):
                    raise ValueError("版本 ID 只能包含小写字母、数字和连字符，最长 64 个字符。")
                body, variant_before, variant_after = replace_section(body, FIELD_LABELS["variant"], variant_id)
                changes.append({"field": "要更新的版本 ID", "before": variant_before, "after": variant_after})
        elif command == "variant":
            replacement = "" if value.lower() in {"none", "clear", "无"} else value.lower()
            if replacement and not re.fullmatch(r"^[a-z0-9][a-z0-9-]{0,63}$", replacement):
                raise ValueError("版本 ID 只能包含小写字母、数字和连字符，最长 64 个字符。")
            body, before, after = replace_section(body, FIELD_LABELS["variant"], replacement)
            changes.append({"field": "要更新的版本 ID", "before": before, "after": after})
        else:
            field_labels = FIELD_LABELS[command]
            body, before, after = replace_section(body, field_labels, value)
            changes.append({"field": field_labels[0], "before": before, "after": after})
    except Exception as exc:  # noqa: BLE001 - user-facing issue update error.
        comment_issue(repo, token, issue_number, update_error_comment(str(exc)))
        return

    patch_issue_body(repo, token, issue_number, body)
    command_text = update_first_line(comment_body)
    comment_issue(repo, token, issue_number, update_success_comment(command_text, changes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate translation library automation labels.")
    parser.add_argument("--event", type=Path, required=True, help="GitHub event JSON path")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/repo")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    parser.add_argument("--handle-comment", action="store_true")
    args = parser.parse_args()

    if not args.repo or not args.token:
        raise SystemExit("Both --repo and --token are required.")
    event = json.loads(args.event.read_text(encoding="utf-8"))
    if args.handle_comment:
        if handle_issue_close(args.repo, args.token, event):
            return
        if handle_issue_force_refresh(args.repo, args.token, event):
            return
        apply_issue_update(args.repo, args.token, event)
        return
    comment_body = str((event.get("comment") or {}).get("body") or "")
    if is_force_refresh_command(comment_body):
        if not comment_is_authorized(event):
            raise SystemExit("Unauthorized /force-refresh command.")
        issue = event.get("issue") or {}
        if str(issue.get("state") or "") != "open":
            raise SystemExit("/force-refresh only supports open issues.")
    issue = event.get("issue") or {}
    labels = issue_labels(issue)
    for label in LABELS:
        ensure_label(args.repo, args.token, label)
    kind = infer_issue_kind(issue)
    if not kind:
        raise SystemExit("This workflow only handles translation submissions, translation petitions, file updates, or file issue reports.")
    expected = KIND_LABELS[kind]
    if expected not in labels:
        add_issue_labels(args.repo, args.token, int(issue["number"]), [expected])
        labels.add(expected)
    active = sorted(label for label in KIND_LABELS.values() if label in labels)
    if len(active) > 1:
        raise SystemExit("每个 issue 只能使用一个自动化标签: " + ", ".join(active))
    close_older_duplicate_issues(args.repo, args.token, event)


if __name__ == "__main__":
    main()
