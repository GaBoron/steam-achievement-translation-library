"""Translation PR metadata parsing, authorization, and user-facing text."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any

from library_index import (
    entry_file_size_label,
    entry_schema_variants,
    escape_table,
    existing_entry,
    load_index,
    repository_path,
    report_state,
    schema_file_size_bytes,
    validated_entry_schema_variants,
)
from steam_schema import achievement_rows, load_schema, require_language_coverage, validate_schema_structure
from submission_inputs import field_value, first_line, now_utc, parse_issue_form
from submission_presentation import parse_schema_variants_marker, steam_store_id, steam_store_url


BOT_USERS = {"github-actions[bot]"}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
UPDATE_LABELS = {"更新文件", "update"}
OUTDATED_LABELS = {"报告错误", "报告过期", "outdated"}
TRANSLATION_PETITION_FULFILLED_MARKER = "translation-library-petition-fulfilled"
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
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


def pr_labels(pr_or_issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name") or "") for label in pr_or_issue.get("labels", []) if isinstance(label, dict)}


def pr_kind(pr: dict[str, Any]) -> str:
    labels = pr_labels(pr)
    if labels & OUTDATED_LABELS:
        return "outdated"
    if labels & UPDATE_LABELS:
        return "update"
    body = str(pr.get("body") or "")
    if "## Achievement Translation Error Report" in body or "## Outdated Translation Report" in body:
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
    body = str(pr.get("body") or "")
    closes = re.search(r"(?mi)^\s*(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\s*$", body)
    if closes:
        return int(closes.group(1))
    try:
        source_issue = str(parse_pr_metadata(pr).get("source_issue") or "")
    except (TypeError, ValueError):
        return 0
    match = re.search(r"/issues/(\d+)(?:[/?#]|$)", source_issue)
    return int(match.group(1)) if match else 0


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
    return sorted({item.strip().strip("`") for item in text.split(",") if item.strip().strip("`")})


def linked_game_name(value: str) -> str:
    match = re.fullmatch(r"\[([^]]+)]\([^)]+\)", value.strip())
    return match.group(1).strip() if match else value.strip()


def parse_pr_metadata(pr: dict[str, Any]) -> dict[str, Any]:
    body = str(pr.get("body") or "")
    contributor_value = body_field(body, "Contributors")
    contributors = [item.strip().lstrip("@") for item in contributor_value.split(",") if item.strip()]
    languages = split_languages(body_field(body, "Languages") or body_field(body, "Supported languages"))
    schema_files = parse_schema_variants_marker(body)
    primary = next((item for item in schema_files or [] if item.get("primary")), {})
    game_id = body_field(body, "Steam app ID")
    closes_match = re.search(r"(?mi)^\s*(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\s*$", body)
    source_issue = body_field(body, "Source issue") or (f"#{closes_match.group(1)}" if closes_match else "")
    return {
        "kind": pr_kind(pr),
        "game_name": linked_game_name(body_field(body, "Game") or body_field(body, "Game name")),
        "game_id": game_id,
        "store_url": body_field(body, "Steam store URL") or steam_store_url(game_id),
        "contributors": contributors,
        "source_issue": source_issue,
        "reporter": body_field(body, "Reporter").lstrip("@"),
        "reported_at": body_field(body, "Reported at"),
        "languages": languages,
        "achievement_count": body_field(body, "Achievements") or body_field(body, "Achievement count") or primary.get("achievement_count"),
        "schema_file": body_field(body, "Schema file") or body_field(body, "Current schema file") or primary.get("schema_file"),
        "schema_files": schema_files,
        "file_size": body_field(body, "File size") or body_field(body, "Current file size"),
        "sha256": body_field(body, "SHA-256") or body_field(body, "Current SHA-256") or primary.get("sha256"),
        "submitted_at": body_field(body, "Submitted at"),
        "updated_at": body_field(body, "Updated at") or body_field(body, "Last library update"),
        "update_summary": body_field(body, "Contributor summary"),
        "contributor_notes": section_after_heading(body, "## Contributor Notes"),
        "reason": section_after_heading(body, "## Reason"),
        "reference": section_after_heading(body, "## Reference"),
        "report_type": body_field(body, "Report type"),
    }


def section_after_heading(body: str, heading: str) -> str:
    if heading not in body:
        return ""
    tail = body.split(heading, 1)[1].strip()
    match = re.search(r"\n##\s+", tail)
    if match:
        tail = tail[:match.start()].strip()
    tail = re.sub(
        r"(?mi)\n+\s*(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#\d+\s*$",
        "",
        tail,
    )
    return tail.strip()


def update_first_line(body: str) -> str:
    return body.strip().splitlines()[0].strip() if body.strip() else ""


def is_update_command(body: str) -> bool:
    first = update_first_line(body).lower()
    return first == "/update" or first.startswith("/update ")


def is_force_refresh_command(body: str) -> bool:
    return body.strip().lower() == "/force-refresh"


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
        variant_languages = [str(value) for value in variant.get("languages") or languages]
        result = validate_languages_for_schema(str(variant["schema_file"]), variant_languages)
        if variant.get("primary"):
            primary_result = result
    if primary_result is None:
        raise ValueError("PR 的 schema 版本元数据缺少主版本。")
    return primary_result


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
        "contributors": meta.get("contributors", []),
        "contributor_id": (meta.get("contributors") or [""])[0] if meta.get("contributors") else "",
        "submitted_at": meta.get("submitted_at") or index_entry.get("submitted_at") or now_utc(),
        "updated_at": meta.get("updated_at") or index_entry.get("updated_at") or now_utc(),
        "status": "current",
    })
    entry.pop("outdated", None)
    entry.pop("report", None)
    entry.pop("source_issue", None)
    entry.pop("source_pr", None)
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
    issue_match = re.search(r"(?:/issues/|#)(\d+)(?:[/?#]|$)", str(meta.get("source_issue") or ""))
    issue_number = int(issue_match.group(1)) if issue_match else 0
    closes = f"\n\nCloses #{issue_number}" if issue_number else ""
    return f"""## Achievement Translation Error Report

- Game: [{entry['game_name']}]({steam_store_url(str(entry['game_id']))})
- Steam app ID: `{entry['game_id']}`
- Current schema file: `{entry.get('schema_file', '')}`
- Current file size: {entry_file_size_label(entry)}
- Current SHA-256: `{entry.get('sha256', '')}`
- Last library update: {entry.get('updated_at', '')}
- Reporter: @{meta.get('reporter', '')}
- Reported at: {meta.get('reported_at', '')}
- Report type: `{meta.get('report_type', entry.get('status', 'outdated'))}`

## Reason

{meta.get('reason', '')}

## Reference

{meta.get('reference', '') or 'No external reference provided.'}{closes}
"""


def reported_entry_from_metadata(
    existing: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Apply an approved report to the latest indexed entry."""
    entry = dict(existing)
    state = report_state(str(meta.get("report_type") or entry.get("status") or ""))
    if meta.get("game_name"):
        entry["game_name"] = str(meta["game_name"])
    if meta.get("store_url"):
        entry["store_url"] = str(meta["store_url"])
    entry["status"] = state
    entry.pop("report", None)
    entry.pop("outdated", None)
    entry.pop("source_issue", None)
    entry.pop("source_pr", None)
    return entry


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


def merged_thanks_comment(pr: dict[str, Any]) -> str:
    meta = parse_pr_metadata(pr)
    kind = pr_kind(pr)
    contributor_ids = [str(contributor) for contributor in meta.get("contributors", []) if contributor]
    if not contributor_ids and kind == "outdated" and meta.get("reporter"):
        contributor_ids = [str(meta["reporter"])]
    contributors = [f"@{contributor}" for contributor in contributor_ids]
    contributor_text = "、".join(contributors) if contributors else "本次贡献者"
    game_name = str(meta.get("game_name") or "该游戏")
    game_id = str(meta.get("game_id") or "")
    game_text = f"{game_name}（{game_id}）" if game_id else game_name
    source_issue = str(meta.get("source_issue") or "")

    if kind == "outdated":
        state_text = "可能不生效" if report_state(str(meta.get("report_type") or "")) == "possibly_ineffective" else "可能过期"
        action_text = f"已将 {game_text} 标记为{state_text}，并同步到翻译库索引。"
        follow_up = "如果之后准备好了新版成就文件，可以直接提交“更新已有 Steam 成就翻译”issue。"
    elif kind == "update":
        action_text = f"已合并 {game_text} 的成就翻译更新，并同步到翻译库索引。"
        follow_up = "后续如果游戏再次更新或发现翻译需要修正，可以继续提交更新 issue。"
    else:
        action_text = f"已收录 {game_text} 的 Steam 成就翻译文件，并同步到翻译库索引。"
        follow_up = "后续如果文件过期或替换后不生效，可以提交“更新已有 Steam 成就翻译”或“报告成就文件错误”。"

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
