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
    "报告过期": {
        "color": "bf8700",
        "description": "报告已收录文件可能过期",
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
    "outdated": "报告过期",
    "translation-petition": "翻译请愿",
}
LEGACY_LABELS = {
    "translation-contribution": "translation-contribution",
    "update": "update",
    "outdated": "outdated",
    "translation-petition": "translation-petition",
}
UPDATE_HELP = "支持的类型：`doc`、`variant`、`id`、`name`、`store`、`languages`、`summary`、`reason`、`reference`、`notes`。"
UPDATE_ALIASES = {
    "doc": "doc",
    "file": "doc",
    "schema": "doc",
    "variant": "variant",
    "version": "variant",
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
    "note": "notes",
    "notes": "notes",
    "reason": "reason",
    "reference": "reference",
    "ref": "reference",
}
VALUE_COMMANDS = {"variant", "id", "name", "store", "languages", "summary", "reason", "reference", "notes"}
FIELD_LABELS = {
    "id": ["Steam app ID"],
    "name": ["游戏名", "Game name"],
    "store": ["Steam 商店地址", "Steam store URL"],
    "languages": ["上传文件包含的语言", "Languages included in the uploaded file"],
    "extra_languages": ["其他 Steam 语言代码", "Additional Steam language codes"],
    "summary": ["更新内容摘要", "Update summary"],
    "reason": ["过期说明", "Why do you think the file is outdated?"],
    "reference": ["参考来源", "Reference or source"],
    "notes": ["备注", "Notes"],
    "doc": ["成就 schema ZIP", "Achievement schema ZIP"],
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
) -> dict[str, Any] | None:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-achievement-translation-library-issue-guard",
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
        if label in labels or LEGACY_LABELS[kind] in labels:
            return kind
    text = issue_text(issue)
    if "### 过期说明" in text or "### Why do you think the file is outdated?" in text:
        return "outdated"
    if "### 更新内容摘要" in text or "### Update summary" in text:
        return "update"
    if "### 需要翻译的成就 schema ZIP" in text or "### Achievement schema ZIP to translate" in text:
        return "translation-petition"
    if "### 成就 schema ZIP" in text or "### Achievement schema ZIP" in text:
        return "translation-contribution"
    return None


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


def update_first_line(body: str) -> str:
    return body.strip().splitlines()[0].strip() if body.strip() else ""


def is_update_command(body: str) -> bool:
    first = update_first_line(body).lower()
    return first == "/update" or first.startswith("/update ")


def comment_is_authorized(event: dict[str, Any]) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    actor = str((comment.get("user") or {}).get("login") or "")
    issue_author = str((issue.get("user") or {}).get("login") or "")
    association = str(comment.get("author_association") or "").upper()
    return bool(actor) and (actor == issue_author or association in TRUSTED_ASSOCIATIONS)


def close_comment_is_authorized(event: dict[str, Any]) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    actor = str((comment.get("user") or {}).get("login") or "")
    issue_author = str((issue.get("user") or {}).get("login") or "")
    return bool(actor) and not actor.endswith("[bot]") and actor == issue_author


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


def parse_update_command(body: str) -> tuple[str, str, str]:
    first = update_first_line(body)
    if not is_update_command(body):
        return "", "", ""
    rest = first[len("/update"):].strip()
    if not rest:
        return "", "", "`/update` 后面必须写明类型，例如 `/update doc` 或 `/update name <游戏名>`。"
    parts = rest.split(maxsplit=1)
    raw_command = parts[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ""
    command = UPDATE_ALIASES.get(raw_command, "")
    if not command:
        return "", "", f"不支持的 `/update {parts[0]}` 类型。{UPDATE_HELP}"
    if command in VALUE_COMMANDS and not value:
        return "", "", f"`/update {raw_command}` 后面缺少参数。{UPDATE_HELP}"
    return command, value, ""


def comma_languages(value: str) -> list[str]:
    text = value.strip().lower()
    if not text:
        raise ValueError("`/update languages` 后面必须写出该文件包含的全部语言代码。")
    if any(separator in text for separator in [";", "；", "，"]):
        raise ValueError("语言代码必须使用半角逗号 `,` 分隔。")
    languages = [part.strip() for part in text.split(",") if part.strip()]
    if not languages:
        raise ValueError("`/update languages` 后面必须写出该文件包含的全部语言代码。")
    invalid = [language for language in languages if not re.fullmatch(r"^[a-z][a-z0-9_]{1,31}$", language)]
    if invalid:
        raise ValueError("无效的 Steam 语言代码：" + ", ".join(invalid))
    return sorted(set(languages))


def extract_attachment_markdown(body: str) -> str:
    matches = list(ATTACHMENT_RE.finditer(body))
    if len(matches) != 1:
        raise ValueError("`/update doc` 需要在同一条评论中附加一个 `UserGameStatsSchema_<app_id>.zip`。")
    match = matches[0]
    label = (match.group(1) or "UserGameStatsSchema_<app_id>.zip").strip()
    url = match.group(2) or match.group("url")
    return f"[{label}]({url})"


def find_section(body: str, labels: list[str]) -> tuple[int, int, str] | None:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("### "):
            continue
        heading = line.removeprefix("### ").strip()
        if heading not in labels:
            continue
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            if lines[next_index].startswith("### "):
                end = next_index
                break
        return index, end, heading
    return None


def section_value(body: str, labels: list[str]) -> str:
    section = find_section(body, labels)
    if section is None:
        return ""
    start, end, _heading = section
    return "\n".join(body.splitlines()[start + 1:end]).strip()


def replace_section(body: str, labels: list[str], value: str) -> tuple[str, str, str]:
    lines = body.splitlines()
    section = find_section(body, labels)
    heading = labels[0]
    replacement = value.strip() or "_No response_"
    if section is None:
        before = ""
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"### {heading}", "", replacement])
        return "\n".join(lines) + "\n", before, replacement
    start, end, heading = section
    before = "\n".join(lines[start + 1:end]).strip()
    new_lines = lines[:start] + [f"### {heading}", "", replacement] + lines[end:]
    return "\n".join(new_lines) + "\n", before, replacement


def escape_table(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip() or "_空_"


def update_success_comment(command_text: str, changes: list[dict[str, str]]) -> str:
    lines = [
        "<!-- translation-library-issue-update-success -->",
        "`/update` 已更新 issue 描述。",
        "",
        f"- 命令：`{escape_table(command_text)}`",
        "- 后续：机器人会基于更新后的 issue 描述重新运行自动检查。",
        "",
        "| 项目 | 原内容 | 更新后 |",
        "| --- | --- | --- |",
    ]
    for change in changes:
        lines.append(f"| {escape_table(change['field'])} | {escape_table(change['before'])} | {escape_table(change['after'])} |")
    return "\n".join(lines)


def update_error_comment(message: str) -> str:
    return "\n".join([
        "`/update` 未通过检查，issue 描述未更新。",
        "",
        f"- 错误：{escape_table(message)}",
        "- 用法：`/update <类型> <参数>`。替换文件时使用 `/update doc`，并在同一条评论中附加 ZIP。",
        "- 语言列表必须写出该文件包含的全部语言代码，并使用半角逗号分隔，例如 `schinese, english, japanese`。",
        f"- {UPDATE_HELP}",
    ])


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
        elif command == "languages":
            languages = comma_languages(value)
            body, before, after = replace_section(body, FIELD_LABELS["languages"], ", ".join(languages))
            changes.append({"field": "上传文件包含的语言", "before": before, "after": after})
            if find_section(body, FIELD_LABELS["extra_languages"]) is not None:
                body, extra_before, extra_after = replace_section(body, FIELD_LABELS["extra_languages"], "none")
                changes.append({"field": "其他 Steam 语言代码", "before": extra_before, "after": extra_after})
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
        apply_issue_update(args.repo, args.token, event)
        return
    issue = event.get("issue") or {}
    labels = issue_labels(issue)
    for label in LABELS:
        ensure_label(args.repo, args.token, label)
    kind = infer_issue_kind(issue)
    if not kind:
        raise SystemExit("This workflow only handles translation submissions, translation petitions, file updates, or outdated reports.")
    expected = KIND_LABELS[kind]
    if expected not in labels:
        add_issue_labels(args.repo, args.token, int(issue["number"]), [expected])
        labels.add(expected)
    active = sorted(label for label in KIND_LABELS.values() if label in labels)
    if len(active) > 1:
        raise SystemExit("每个 issue 只能使用一个自动化标签: " + ", ".join(active))


if __name__ == "__main__":
    main()
