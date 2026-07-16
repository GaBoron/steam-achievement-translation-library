from __future__ import annotations

import base64
import html
import json
import re
from datetime import datetime
from typing import Any

CLOSE_REQUEST_MARKER_RE = re.compile(
    r"<!-- translation-library-close-request:([A-Za-z0-9_-]+) -->"
)
BOT_COMMENT_AUTHOR = "github-actions[bot]"


def command_first_line(body: str) -> str:
    return body.strip().splitlines()[0].strip() if body.strip() else ""


def is_close_command(body: str) -> bool:
    first = command_first_line(body).lower()
    return first == "/close" or first.startswith("/close ")


def parse_close_command(body: str) -> tuple[str, str, str]:
    first = command_first_line(body)
    if not is_close_command(body):
        return "", "", ""
    value = first[len("/close"):].strip()
    if not value:
        return "", "", "`/close` 后面必须填写关闭原因，例如 `/close 已有更完整的投稿`。"
    if value.lower() == "confirm":
        return "confirm", "", ""
    if len(value) > 500:
        return "", "", "关闭原因不能超过 500 个字符。"
    return "request", value, ""


def encode_close_request(actor: str, reason: str) -> str:
    payload = json.dumps(
        {"actor": actor, "reason": reason},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_close_request(body: str) -> dict[str, str] | None:
    match = CLOSE_REQUEST_MARKER_RE.search(body)
    if not match:
        return None
    encoded = match.group(1)
    encoded += "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    actor = str(payload.get("actor") or "").strip() if isinstance(payload, dict) else ""
    reason = str(payload.get("reason") or "").strip() if isinstance(payload, dict) else ""
    if not actor or not reason:
        return None
    return {"actor": actor, "reason": reason}


def close_request_comment(actor: str, reason: str, target_name: str) -> str:
    marker = encode_close_request(actor, reason)
    return "\n".join([
        f"<!-- translation-library-close-request:{marker} -->",
        f"已收到 @{actor} 的{target_name}关闭请求，但尚未关闭。",
        "",
        f"- 关闭原因：{html.escape(reason)}",
        "- 确认操作：请等待本回复出现后，新建一条评论并输入 `/close confirm`。",
        "- 注意：只有原投稿者可以确认；确认后将立即关闭并锁定，不能通过机器人撤销。",
    ])


def latest_close_request(comments: list[dict[str, Any]], actor: str) -> dict[str, str] | None:
    for comment in reversed(comments):
        author = str(((comment.get("user") or {}).get("login") or ""))
        if author != BOT_COMMENT_AUTHOR:
            continue
        request = decode_close_request(str(comment.get("body") or ""))
        if request and request["actor"] == actor:
            request["created_at"] = str(comment.get("created_at") or "")
            request["comment_id"] = str(comment.get("id") or "")
            return request
    return None


def parse_github_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def confirmation_follows_reply(comment: dict[str, Any], request: dict[str, str]) -> bool:
    confirmation_id = str(comment.get("id") or "")
    reply_id = str(request.get("comment_id") or "")
    if confirmation_id.isdigit() and reply_id.isdigit():
        return int(confirmation_id) > int(reply_id)
    confirmation_time = parse_github_timestamp(str(comment.get("created_at") or ""))
    reply_time = parse_github_timestamp(str(request.get("created_at") or ""))
    return bool(confirmation_time and reply_time and confirmation_time > reply_time)


def close_command_error(message: str) -> str:
    return "\n".join([
        "`/close` 未执行。",
        "",
        f"- 原因：{html.escape(message)}",
        "- 用法：先输入 `/close 关闭原因`，等待机器人回复后，再新建一条评论输入 `/close confirm`。",
    ])


def close_completed_comment(actor: str, reason: str, target_name: str) -> str:
    return "\n".join([
        f"@{actor} 已确认关闭{target_name}。",
        "",
        f"- 关闭原因：{html.escape(reason)}",
        "- 状态：确认完成，机器人正在关闭并锁定。",
    ])
