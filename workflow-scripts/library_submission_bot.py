#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.json"
HUMAN_INDEX_PATH = REPO_ROOT / "README.md"
HUMAN_INDEX_EN_PATH = REPO_ROOT / "README_EN.md"
FILES_ROOT = REPO_ROOT / "files"
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
SCHEMA_NAME_RE = re.compile(r"^UserGameStatsSchema_(\d+)\.bin$", re.I)
ZIP_NAME_RE = re.compile(r"^UserGameStatsSchema_(\d+)\.zip$", re.I)
ATTACHMENT_RE = re.compile(r"\[([^\]]+)\]\((https://github\.com/user-attachments/[^\s)]+)\)|(?P<url>https://github\.com/user-attachments/[^\s)]+)")


def parse_issue_form(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    chunks: list[str] = []
    for line in body.splitlines():
        if line.startswith("### "):
            if current is not None:
                fields[current] = "\n".join(chunks).strip()
            current = line.removeprefix("### ").strip()
            chunks = []
        elif current is not None:
            chunks.append(line)
    if current is not None:
        fields[current] = "\n".join(chunks).strip()
    return fields


def first_line(value: str) -> str:
    for line in value.splitlines():
        text = line.strip()
        if text and text != "_No response_":
            return text
    return ""


def field_value(fields: dict[str, str], names: list[str]) -> str:
    return next((fields[name] for name in names if name in fields), "")


def parse_languages(value: str, extra: str) -> list[str]:
    languages = [m.group(1).lower() for m in re.finditer(r"- \[[xX]\]\s*([a-z][a-z0-9_]*)\b", value)]
    extra_text = first_line(extra).lower()
    if extra_text and extra_text not in {"none", "n/a", "na", "no"}:
        languages.extend(part.strip() for part in re.split(r"[,;\s]+", extra_text) if part.strip())
    return sorted(set(languages))


def extract_attachment(value: str) -> tuple[str, str, bool] | None:
    matches = list(ATTACHMENT_RE.finditer(value))
    if len(matches) != 1:
        return None
    match = matches[0]
    url = match.group(2) or match.group("url")
    filename_from_url = not bool(match.group(1))
    filename = match.group(1) or Path(urllib.parse.urlparse(url).path).name
    return urllib.parse.unquote(filename.strip()), url, filename_from_url


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        return {"version": 1, "description": "Community-submitted Steam achievement schema translations.", "entries": []}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def write_index(index: dict[str, Any]) -> None:
    index["entries"] = sorted(index.get("entries", []), key=lambda e: (str(e.get("game_name", "")).casefold(), str(e.get("game_id", ""))))
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def schema_download_url(schema_file: str) -> str:
    path = urllib.parse.quote(schema_file.replace("\\", "/").lstrip("/"), safe="/")
    repo = os.environ.get("GITHUB_REPOSITORY", "GaBoron/steam-achievement-translation-library")
    return f"https://raw.githubusercontent.com/{repo}/main/{path}"


def contributor_link(contributor: str) -> str:
    return f"[@{escape_table(contributor)}](https://github.com/{urllib.parse.quote(contributor, safe='')})" if contributor else ""


def write_human_indexes(index: dict[str, Any]) -> None:
    entries = index.get("entries", [])
    zh = ["# Steam 成就翻译库", "", "简体中文 | [English](README_EN.md)", "", "本仓库专门维护 Steam 成就翻译数据，不包含 Codex skill 本体。", "", "## 游戏列表", ""]
    en = ["# Steam Achievement Translation Library", "", "[简体中文](README.md) | English", "", "This repository hosts Steam achievement translation data only; it does not include the Codex skill runtime.", "", "## Games", ""]
    if entries:
        header = ["| Steam app ID | 游戏 / Game | 贡献者 / Contributor | 支持语言 / Languages | 成就数 / Achievements | 成就文件 / Schema file | 商店 / Store |", "| --- | --- | --- | --- | ---: | --- | --- |"]
        zh.extend(header)
        en.extend(header)
        for entry in entries:
            schema_file = str(entry.get("schema_file", ""))
            schema_name = PurePosixPath(schema_file).name
            row = f"| `{entry.get('game_id', '')}` | {escape_table(str(entry.get('game_name', '')))} | {contributor_link(str(entry.get('contributor_id', '')))} | {escape_table(', '.join(entry.get('languages', [])))} | {entry.get('achievement_count', '')} | [`{schema_name}`]({schema_download_url(schema_file)}) | [Steam]({entry.get('store_url', '')}) |"
            zh.append(row)
            en.append(row)
    else:
        zh.append("暂无已收录游戏。")
        en.append("No accepted games yet.")
    HUMAN_INDEX_PATH.write_text("\n".join(zh) + "\n", encoding="utf-8")
    HUMAN_INDEX_EN_PATH.write_text("\n".join(en) + "\n", encoding="utf-8")


def fail(errors: list[str]) -> None:
    Path("submission_result.json").write_text(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1)


def validate_and_update(event: dict[str, Any], token: str | None) -> dict[str, Any]:
    issue = event["issue"]
    fields = parse_issue_form(issue.get("body") or "")
    game_name = first_line(field_value(fields, ["Game name", "游戏名"]))
    game_id = first_line(field_value(fields, ["Steam app ID"]))
    store_url = first_line(field_value(fields, ["Steam store URL", "Steam 商店地址"]))
    languages = parse_languages(field_value(fields, ["Languages included in the uploaded file", "上传文件包含的语言"]), field_value(fields, ["Additional Steam language codes", "其他 Steam 语言代码"]))
    attachment = extract_attachment(field_value(fields, ["Achievement schema ZIP", "Achievement schema file", "成就 schema ZIP", "成就 schema 文件"]))
    errors: list[str] = []
    if not game_name: errors.append("Game name is required.")
    if not re.fullmatch(r"\d+", game_id): errors.append("Steam app ID must be numeric.")
    if not re.search(r"store\.steampowered\.com/app/" + re.escape(game_id), store_url): errors.append("Steam store URL must match the submitted app ID.")
    if not languages or any(not LANGUAGE_RE.fullmatch(language) for language in languages): errors.append("At least one valid Steam language code is required.")
    if not attachment: errors.append("Attach exactly one UserGameStatsSchema_<app_id>.zip file.")
    if errors: fail(errors)
    filename, url, filename_from_url = attachment  # type: ignore[misc]
    if not filename_from_url and not (ZIP_NAME_RE.fullmatch(filename) or SCHEMA_NAME_RE.fullmatch(filename)):
        fail([f"Uploaded file must be UserGameStatsSchema_{game_id}.zip or .bin; got {filename}."])
    with tempfile.TemporaryDirectory() as tmp:
        downloaded = Path(tmp) / filename
        request = urllib.request.Request(url, headers={"User-Agent": "steam-achievement-translation-library-bot"})
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=45) as response:
            downloaded.write_bytes(response.read())
        schema_path = downloaded
        if zipfile.is_zipfile(downloaded):
            with zipfile.ZipFile(downloaded) as archive:
                files = [info for info in archive.infolist() if not info.is_dir()]
                if len(files) != 1:
                    fail(["ZIP upload must contain exactly one schema file."])
                member = files[0]
                if Path(member.filename).name != f"UserGameStatsSchema_{game_id}.bin":
                    fail([f"ZIP upload must contain UserGameStatsSchema_{game_id}.bin."])
                schema_path = Path(tmp) / f"UserGameStatsSchema_{game_id}.bin"
                schema_path.write_bytes(archive.read(member))
        target_dir = FILES_ROOT / game_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"UserGameStatsSchema_{game_id}.bin"
        shutil.copy2(schema_path, target_file)
    index = load_index()
    entry = {"game_name": game_name, "game_id": game_id, "store_url": store_url, "languages": languages, "schema_file": str(target_file.relative_to(REPO_ROOT)).replace("\\", "/"), "achievement_count": None, "source_issue": issue.get("html_url"), "contributor_id": (issue.get("user") or {}).get("login", "")}
    index["entries"] = [e for e in index.get("entries", []) if str(e.get("game_id")) != game_id] + [entry]
    write_index(index)
    write_human_indexes(index)
    result = {"ok": True, "branch": f"translation-library/issue-{issue['number']}", "pr_title": f"添加 {game_name} ({game_id}) 成就翻译", "game_id": game_id}
    Path("submission_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("pr_title.txt").write_text(result["pr_title"] + "\n", encoding="utf-8")
    Path("pr_body.md").write_text(f"## 翻译投稿\n\n- 游戏：{game_name}\n- Steam app ID：`{game_id}`\n- 语言：{', '.join(languages)}\n- 来源 issue：{issue.get('html_url')}\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()
    validate_and_update(json.loads(args.event.read_text(encoding="utf-8")), args.token)


if __name__ == "__main__":
    main()
