#!/usr/bin/env python3
"""Validate translation petitions and acknowledge recognized schema files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from library_submission_bot import (
    LANGUAGE_RE,
    download_attachment,
    extract_attachment,
    field_value,
    first_line,
    load_schema,
    parse_comma_language_list,
    parse_issue_form,
    steam_store_id,
    validate_schema_structure,
)

RECEIVED_MARKER = "<!-- translation-library-petition-received -->"
FAILURE_MARKER_PREFIX = "translation-library-petition-invalid"


def github_request(
    method: str,
    repo: str,
    token: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-achievement-translation-library-petition-bot",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed with HTTP {exc.code}: {detail}") from exc


def comment_issue_once(repo: str, token: str, issue_number: int, body: str, marker: str) -> None:
    comments = github_request("GET", repo, token, f"/issues/{issue_number}/comments?per_page=100") or []
    if any(marker in str(comment.get("body") or "") for comment in comments):
        return
    github_request("POST", repo, token, f"/issues/{issue_number}/comments", {"body": body})


def validate_petition(issue: dict[str, Any], token: str | None) -> dict[str, Any]:
    fields = parse_issue_form(str(issue.get("body") or ""))
    game_name = first_line(field_value(fields, ["Game name", "游戏名"]))
    game_id = first_line(field_value(fields, ["Steam app ID"]))
    store_url = first_line(field_value(fields, ["Steam store URL", "Steam 商店地址"]))
    target_text = field_value(fields, ["Requested target languages", "希望翻译到的语言"])
    attachment = extract_attachment(
        field_value(fields, ["Achievement schema BIN to translate", "需要翻译的成就 schema BIN"])
    )
    errors: list[str] = []

    if not game_name:
        errors.append("必须填写游戏名。")
    if not re.fullmatch(r"\d+", game_id):
        errors.append("Steam app ID 必须只包含数字。")
    store_id = steam_store_id(store_url)
    if not store_id:
        errors.append("Steam 商店地址必须是 store.steampowered.com/app/<id>/ 格式。")
    elif game_id and store_id != game_id:
        errors.append(f"Steam 商店地址中的 app ID {store_id} 与填写的 app ID {game_id} 不一致。")

    target_languages = parse_comma_language_list(target_text)
    invalid_languages = [language for language in target_languages if not LANGUAGE_RE.fullmatch(language)]
    if not target_languages:
        errors.append("至少填写一个希望翻译到的 Steam 语言代码。")
    if invalid_languages:
        errors.append("无效的 Steam 语言代码：" + ", ".join(invalid_languages))
    if any(separator in target_text for separator in [";", "；", "，"]):
        errors.append("目标语言必须使用半角逗号 `,` 分隔。")

    expected_name = f"UserGameStatsSchema_{game_id}.bin" if game_id else "UserGameStatsSchema_<app_id>.bin"
    if attachment is None:
        errors.append("必须附加且只能附加一个未经压缩的 UserGameStatsSchema_<app_id>.bin 文件。")
    elif attachment.filename != expected_name:
        errors.append(f"上传文件名必须是 {expected_name}，当前识别为 {attachment.filename}。")

    achievement_count = 0
    if not errors and attachment is not None:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                schema_path = Path(tmp) / "petition-schema.bin"
                download_attachment(attachment, token, schema_path)
                data, nodes = load_schema(schema_path)
                achievement_count = len(validate_schema_structure(data, nodes))
        except Exception as exc:  # noqa: BLE001 - reported as an actionable issue validation error.
            errors.append(f"无法识别上传的 BIN：{exc}")

    return {
        "ok": not errors,
        "errors": errors,
        "game_name": game_name,
        "game_id": game_id,
        "target_languages": target_languages,
        "achievement_count": achievement_count,
    }


def received_comment(result: dict[str, Any]) -> str:
    languages = ", ".join(f"`{item}`" for item in result["target_languages"])
    return "\n".join([
        RECEIVED_MARKER,
        "翻译请愿已收到；若有人上传并通过审核，机器人会在这里通知你。",
        "",
        f"- 游戏：{result['game_name']}",
        f"- Steam app ID：`{result['game_id']}`",
        f"- 已识别成就数：{result['achievement_count']}",
        f"- 目标语言：{languages}",
    ])


def invalid_comment(errors: list[str]) -> tuple[str, str]:
    error_text = "\n".join(errors)
    digest = hashlib.sha256(error_text.encode("utf-8")).hexdigest()[:12]
    marker = f"<!-- {FAILURE_MARKER_PREFIX}:{digest} -->"
    lines = [
        marker,
        "暂时无法识别这份翻译请愿。请编辑 issue 修正以下问题；编辑后机器人会重新检查。",
        "",
        "## 问题说明",
        "",
    ]
    lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines), marker


def handle_petition(event: dict[str, Any], repo: str, token: str) -> dict[str, Any]:
    issue = event.get("issue") or {}
    issue_number = int(issue["number"])
    result = validate_petition(issue, token)
    if result["ok"]:
        comment_issue_once(repo, token, issue_number, received_comment(result), RECEIVED_MARKER)
    else:
        body, marker = invalid_comment(result["errors"])
        comment_issue_once(repo, token, issue_number, body, marker)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and acknowledge a translation petition issue.")
    parser.add_argument("--event", type=Path, required=True, help="GitHub event JSON path")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/repo")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    args = parser.parse_args()
    if not args.repo or not args.token:
        raise SystemExit("Both --repo and --token are required.")
    event = json.loads(args.event.read_text(encoding="utf-8"))
    handle_petition(event, args.repo, args.token)


if __name__ == "__main__":
    main()
