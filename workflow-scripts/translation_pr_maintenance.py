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

from library_submission_bot import (
    LANGUAGE_RE,
    achievement_rows,
    build_submission_pr_body,
    escape_table,
    existing_entry,
    extract_attachment,
    language_coverage,
    load_index,
    load_schema,
    now_utc,
    sha256,
    steam_store_id,
    summarize_update_diff,
    upsert_index_entry,
    validate_schema_submission,
    write_human_index,
    write_index,
)

ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = ROOT / "files"
WAIT_FOR_UPDATE_LABEL = "等待更新"
BOT_USERS = {"github-actions[bot]"}
UPDATE_LABELS = {"更新文件", "update"}
OUTDATED_LABELS = {"报告过期", "outdated"}


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
    return {
        "kind": pr_kind(pr),
        "game_name": body_field(body, "Game name"),
        "game_id": body_field(body, "Steam app ID"),
        "store_url": body_field(body, "Steam store URL"),
        "contributors": contributors,
        "source_issue": body_field(body, "Source issue"),
        "languages": languages,
        "achievement_count": body_field(body, "Achievement count"),
        "schema_file": body_field(body, "Schema file"),
        "sha256": body_field(body, "SHA-256"),
        "submitted_at": body_field(body, "Submitted at"),
        "updated_at": body_field(body, "Updated at"),
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
    data, nodes = load_schema(ROOT / schema_file)
    rows = achievement_rows(nodes, languages)
    coverage, missing = language_coverage(rows, languages)
    missing_messages = []
    for language, missing_ids in missing.items():
        if missing_ids:
            preview = ", ".join(missing_ids[:10])
            missing_messages.append(f"{language}: 缺少 {len(missing_ids)} 个成就文本：{preview}")
    if missing_messages:
        raise ValueError("语言覆盖不完整。" + "；".join(missing_messages))
    if sha256(data) == "":
        raise ValueError("Schema hash could not be calculated.")
    return rows, coverage


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


def rename_schema_file(old_game_id: str, new_game_id: str, schema_file: str) -> str:
    if old_game_id == new_game_id:
        return schema_file
    old_path = ROOT / schema_file
    if not old_path.is_file():
        raise ValueError(f"当前 schema 文件不存在：{schema_file}")
    new_dir = FILES_ROOT / new_game_id
    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / f"UserGameStatsSchema_{new_game_id}.bin"
    old_path.replace(new_path)
    old_dir = old_path.parent
    try:
        old_dir.rmdir()
    except OSError:
        pass
    return str(new_path.relative_to(ROOT)).replace("\\", "/")


def entry_from_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    index_entry = existing_entry(load_index(), str(meta["game_id"])) or {}
    entry = dict(index_entry)
    entry.update({
        "game_name": meta["game_name"],
        "game_id": meta["game_id"],
        "store_url": meta["store_url"],
        "languages": meta["languages"],
        "schema_file": meta["schema_file"],
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
    return entry


def build_outdated_body(entry: dict[str, Any], meta: dict[str, Any]) -> str:
    outdated = entry.get("outdated") if isinstance(entry.get("outdated"), dict) else {}
    return f"""## Outdated Translation Report

- Game name: {entry['game_name']}
- Steam app ID: `{entry['game_id']}`
- Steam store URL: {entry.get('store_url', '')}
- Current schema file: `{entry.get('schema_file', '')}`
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
        f"- 用法：`/update <类型> <参数>`。`/update doc` 的参数是同一条评论中的 `UserGameStatsSchema_<app_id>.zip` 附件。",
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

    branch = checkout_pr_branch(pr)
    meta = parse_pr_metadata(pr)
    original_meta = dict(meta)
    old_game_id = str(meta.get("game_id") or "")
    kind = str(meta["kind"])
    attachment = extract_attachment(comment_body)
    command_text = comment_body.strip().splitlines()[0].strip() if comment_body.strip() else "/update"
    changes: list[dict[str, Any]] = []

    def record_change(field: str, before: Any, after: Any) -> None:
        changes.append({"field": field, "before": before, "after": after})

    try:
        if command == "doc":
            if not attachment:
                raise ValueError("`/update doc` 需要在同一条评论中附加 `UserGameStatsSchema_<app_id>.zip`。")
            data, _nodes, rows, coverage = validate_schema_submission(attachment, token, old_game_id, list(meta["languages"]))
            schema_path = FILES_ROOT / old_game_id / f"UserGameStatsSchema_{old_game_id}.bin"
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            previous_rows = achievement_rows(load_schema(schema_path)[1], list(meta["languages"])) if schema_path.is_file() else []
            previous_hash = sha256(schema_path.read_bytes()) if schema_path.is_file() else ""
            previous_schema_file = str(meta.get("schema_file") or "")
            previous_count = str(meta.get("achievement_count") or "")
            previous_updated_at = str(meta.get("updated_at") or "")
            schema_path.write_bytes(data)
            meta["schema_file"] = str(schema_path.relative_to(ROOT)).replace("\\", "/")
            meta["sha256"] = sha256(data)
            meta["achievement_count"] = str(len(rows))
            meta["updated_at"] = now_utc()
            update_diff = summarize_update_diff(previous_rows, rows, list(meta["languages"])) if previous_rows else None
            record_change("schema file", previous_schema_file, meta["schema_file"])
            record_change("SHA-256", previous_hash or str(original_meta.get("sha256") or ""), meta["sha256"])
            record_change("achievement count", previous_count, meta["achievement_count"])
            record_change("updated at", previous_updated_at, meta["updated_at"])
            if update_diff is not None:
                record_change(
                    "achievement diff",
                    "current PR file",
                    f"+{len(update_diff['added'])} / -{len(update_diff['deleted'])} / ~{len(update_diff['changed'])}",
                )
        elif command == "id":
            if not re.fullmatch(r"\d+", value):
                raise ValueError("`/update id` 后面必须是数字 Steam app ID。")
            previous_schema_file = str(meta.get("schema_file") or "")
            previous_store_url = str(meta.get("store_url") or "")
            previous_hash = str(meta.get("sha256") or "")
            previous_count = str(meta.get("achievement_count") or "")
            previous_updated_at = str(meta.get("updated_at") or "")
            if kind == "outdated":
                replacement = existing_entry(load_index(), value)
                if not replacement:
                    raise ValueError("报告过期 PR 的 `/update id` 必须指向库里已经收录的 Steam app ID。")
                meta["schema_file"] = str(replacement.get("schema_file") or "")
                meta["sha256"] = str(replacement.get("sha256") or "")
                meta["achievement_count"] = str(replacement.get("achievement_count") or "")
                meta["languages"] = list(replacement.get("languages", []))
            else:
                meta["schema_file"] = rename_schema_file(old_game_id, value, str(meta["schema_file"]))
            meta["game_id"] = value
            if old_game_id and old_game_id in str(meta["store_url"]):
                meta["store_url"] = str(meta["store_url"]).replace(f"/app/{old_game_id}", f"/app/{value}")
            validate_store_url(value, str(meta["store_url"]))
            rows, coverage = validate_languages_for_schema(str(meta["schema_file"]), list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            meta["sha256"] = sha256((ROOT / str(meta["schema_file"])).read_bytes())
            meta["achievement_count"] = str(len(rows))
            meta["updated_at"] = now_utc()
            update_diff = None
            record_change("Steam app ID", old_game_id, meta["game_id"])
            if kind != "outdated":
                record_change("Steam store URL", previous_store_url, meta["store_url"])
                record_change("schema file", previous_schema_file, meta["schema_file"])
                record_change("SHA-256", previous_hash, meta["sha256"])
                record_change("achievement count", previous_count, meta["achievement_count"])
                record_change("updated at", previous_updated_at, meta["updated_at"])
        elif command == "name":
            if not value:
                raise ValueError("`/update name` 后面必须填写游戏名。")
            previous_name = str(meta.get("game_name") or "")
            meta["game_name"] = value
            rows, coverage = validate_languages_for_schema(str(meta["schema_file"]), list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            if kind != "outdated":
                record_change("game name", previous_name, meta["game_name"])
        elif command == "store":
            previous_store_url = str(meta.get("store_url") or "")
            validate_store_url(str(meta["game_id"]), value)
            meta["store_url"] = value
            rows, coverage = validate_languages_for_schema(str(meta["schema_file"]), list(meta["languages"]))
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            if kind != "outdated":
                record_change("Steam store URL", previous_store_url, meta["store_url"])
        elif command == "languages":
            previous_languages = list(meta.get("languages") or [])
            languages = split_languages(value)
            rows, coverage = validate_languages_for_schema(str(meta["schema_file"]), languages)
            meta["languages"] = languages
            previous_hash = str(meta.get("sha256") or "")
            update_diff = None
            record_change("supported languages", previous_languages, meta["languages"])
        elif command == "summary":
            if not value:
                raise ValueError("`/update summary` 后面必须填写更新摘要。")
            previous_summary = str(meta.get("update_summary") or "")
            meta["update_summary"] = value
            rows, coverage = validate_languages_for_schema(str(meta["schema_file"]), list(meta["languages"]))
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
    actor = str(((event.get("comment") or {}).get("user") or {}).get("login") or "")
    if is_bot(actor):
        return
    remove_issue_label(repo, token, int(issue["number"]), WAIT_FOR_UPDATE_LABEL)


def handle_comment(repo: str, token: str, event: dict[str, Any]) -> None:
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
        schema_path = ROOT / str(entry.get("schema_file") or "")
        if not schema_path.is_file():
            raise RuntimeError(f"merged PR schema file is missing from main: {entry.get('schema_file') or '<empty>'}")
        data, nodes = load_schema(schema_path)
        if sha256(data) != str(entry.get("sha256") or ""):
            raise RuntimeError(f"merged PR schema SHA-256 does not match PR metadata for {entry.get('schema_file')}")
        entry["achievement_count"] = len(achievement_rows(nodes, list(entry.get("languages", []))))
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
