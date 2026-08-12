"""Pure authorization and update-command parsing for issue comments."""
from __future__ import annotations

import re
from typing import Any


UPDATE_HELP = "支持的类型：`doc`、`variant`、`id`、`name`、`summary`、`type`、`reason`、`reference`、`notes`。"
UPDATE_ALIASES = {
    "doc": "doc", "file": "doc", "schema": "doc", "variant": "variant", "version": "variant",
    "id": "id", "app": "id", "appid": "id", "app-id": "id", "name": "name", "title": "name",
    "summary": "summary", "type": "type",
    "note": "notes", "notes": "notes", "reason": "reason", "reference": "reference", "ref": "reference",
}
VALUE_COMMANDS = {"variant", "id", "name", "summary", "type", "reason", "reference", "notes"}
ATTACHMENT_RE = re.compile(
    r"\[([^\]]+)\]\((https://github\.com/user-attachments/[^\s)]+)\)|(?<!\()(?P<url>https://github\.com/user-attachments/[^\s)]+)"
)
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def update_first_line(body: str) -> str:
    return body.strip().splitlines()[0].strip() if body.strip() else ""


def is_update_command(body: str) -> bool:
    first = update_first_line(body).lower()
    return first == "/update" or first.startswith("/update ")


def is_force_refresh_command(body: str) -> bool:
    # Keep this exact match aligned with the workflow job condition so an
    # acknowledgement can never be posted without the review job also running.
    return body == "/force-refresh"


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
        "- 商店地址由 App ID 生成，语言列表由上传的 schema 自动识别。",
        f"- {UPDATE_HELP}",
    ])
