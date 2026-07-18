#!/usr/bin/env python3
"""Validate translation-petition ZIPs and acknowledge recognized schemas."""
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
    entry_schema_variants,
    existing_entry,
    extract_attachment,
    field_value,
    find_open_translation_pr,
    first_line,
    load_index,
    load_schema,
    parse_comma_language_list,
    parse_issue_form,
    resolve_schema_upload,
    schema_download_url,
    steam_store_id,
    validate_schema_structure,
)

RECEIVED_MARKER = "<!-- translation-library-petition-received -->"
FAILURE_MARKER_PREFIX = "translation-library-petition-invalid"
INDEXED_MARKER = "<!-- translation-library-petition-indexed -->"
OPEN_PR_MARKER = "<!-- translation-library-petition-open-pr -->"


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


def close_issue(repo: str, token: str, issue_number: int) -> None:
    github_request(
        "PATCH",
        repo,
        token,
        f"/issues/{issue_number}",
        {"state": "closed", "state_reason": "completed"},
    )


def petition_game_id(issue: dict[str, Any]) -> str:
    fields = parse_issue_form(str(issue.get("body") or ""))
    return first_line(field_value(fields, ["Steam app ID"]))


def indexed_resource_comment(entry: dict[str, Any], game_id: str, repo: str) -> str:
    game_name = str(entry.get("game_name") or "该游戏")
    variants = entry_schema_variants(entry)
    lines = [
        INDEXED_MARKER,
        f"{game_name}（Steam app ID `{game_id}`）已经收录，无需再提交翻译请愿。",
        "",
        "## 可用资源",
        "",
    ]
    for variant in variants:
        schema_file = str(variant.get("schema_file") or "").strip()
        if not schema_file:
            continue
        variant_id = str(variant.get("variant_id") or "default")
        note = str(variant.get("note_zh") or variant_id).strip()
        filename = Path(schema_file).name
        lines.append(f"- {note}（`{variant_id}`）：[下载 `{filename}`]({schema_download_url(schema_file, repo)})")
    lines.extend([
        f"- 翻译库索引：[INDEX.md](https://github.com/{repo}/blob/main/INDEX.md)",
        "",
        "此 issue 已自动关闭。",
    ])
    return "\n".join(lines)


def open_pr_resource_comment(open_pr: dict[str, Any], game_id: str) -> str:
    pr_number = int(open_pr.get("number") or 0)
    pr_url = str(open_pr.get("html_url") or "").strip()
    pr_label = f"PR #{pr_number}" if pr_number else "开放 PR"
    pr_link = f"[{pr_label}]({pr_url})" if pr_url else pr_label
    return "\n".join([
        OPEN_PR_MARKER,
        f"Steam app ID `{game_id}` 已有正在审核的翻译投稿，无需重复提交翻译请愿。",
        "",
        f"- 投稿资源：{pr_link}",
        "- PR 合并后即可从翻译库下载；机器人也会在相关请愿中发送通知。",
        "",
        "此 issue 已自动关闭。",
    ])


def close_if_resource_exists(
    issue: dict[str, Any],
    repo: str,
    token: str,
) -> dict[str, Any] | None:
    game_id = petition_game_id(issue)
    if not re.fullmatch(r"\d+", game_id):
        return None
    issue_number = int(issue["number"])
    indexed = existing_entry(load_index(), game_id)
    if indexed:
        comment_issue_once(
            repo,
            token,
            issue_number,
            indexed_resource_comment(indexed, game_id, repo),
            INDEXED_MARKER,
        )
        close_issue(repo, token, issue_number)
        return {"ok": False, "closed": True, "reason": "indexed", "game_id": game_id, "errors": []}

    open_pr = find_open_translation_pr(repo, token, game_id)
    if open_pr:
        comment_issue_once(
            repo,
            token,
            issue_number,
            open_pr_resource_comment(open_pr, game_id),
            OPEN_PR_MARKER,
        )
        close_issue(repo, token, issue_number)
        return {"ok": False, "closed": True, "reason": "open-pr", "game_id": game_id, "errors": []}
    return None


def validate_petition(issue: dict[str, Any], token: str | None) -> dict[str, Any]:
    fields = parse_issue_form(str(issue.get("body") or ""))
    game_name = first_line(field_value(fields, ["Game name", "游戏名"]))
    game_id = first_line(field_value(fields, ["Steam app ID"]))
    store_url = first_line(field_value(fields, ["Steam store URL", "Steam 商店地址"]))
    target_text = field_value(fields, ["Requested target languages", "希望翻译到的语言"])
    attachment = extract_attachment(
        field_value(fields, ["Achievement schema ZIP to translate", "需要翻译的成就 schema ZIP"])
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

    expected_name = f"UserGameStatsSchema_{game_id}.zip" if game_id else "UserGameStatsSchema_<app_id>.zip"
    if attachment is None:
        errors.append("必须附加且只能附加一个 UserGameStatsSchema_<app_id>.zip 文件。")
    elif attachment.filename != expected_name:
        errors.append(f"上传文件名必须是 {expected_name}，当前识别为 {attachment.filename}。")

    achievement_count = 0
    if not errors and attachment is not None:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                archive_path = tmp_path / "petition-schema.zip"
                download_attachment(attachment, token, archive_path)
                schema_path = resolve_schema_upload(archive_path, attachment, game_id, tmp_path)
                data, nodes = load_schema(schema_path)
                achievement_count = len(validate_schema_structure(data, nodes))
        except Exception as exc:  # noqa: BLE001 - reported as an actionable issue validation error.
            errors.append(f"无法识别上传的 ZIP：{exc}")

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
    try:
        resource_result = close_if_resource_exists(issue, repo, token)
    except Exception as exc:  # noqa: BLE001 - keep the petition open when duplicate checks are unavailable.
        errors = [f"无法检查索引或正在打开的同 ID PR：{exc}。请稍后编辑或重新打开 issue 以重试。"]
        body, marker = invalid_comment(errors)
        comment_issue_once(repo, token, issue_number, body, marker)
        return {"ok": False, "closed": False, "game_id": petition_game_id(issue), "errors": errors}
    if resource_result is not None:
        return resource_result
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
