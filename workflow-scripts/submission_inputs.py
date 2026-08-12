"""Issue-form parsing, attachment download, and submission lookup inputs."""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
ATTACHMENT_RE = re.compile(
    r"\[([^\]]+)\]\((https://github\.com/user-attachments/[^\s)]+)\)|(?<!\()(?P<url>https://github\.com/user-attachments/[^\s)]+)"
)
PR_GAME_ID_RE = re.compile(r"(?mi)^-\s*Steam app ID:\s*`?(\d+)`?\s*$")


@dataclass
class Attachment:
    filename: str
    url: str
    filename_from_url: bool = False


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    for name in names:
        if name in fields:
            return fields[name]
    return ""


def optional_field_value(fields: dict[str, str], names: list[str]) -> str:
    value = field_value(fields, names).strip()
    return "" if value == "_No response_" else value


def parse_comma_language_list(value: str) -> list[str]:
    text = first_line(value).lower()
    if not text or text in {"none", "n/a", "na", "no", "无"}:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def extract_attachment(value: str) -> Attachment | None:
    matches = list(ATTACHMENT_RE.finditer(value))
    if len(matches) != 1:
        return None
    match = matches[0]
    url = match.group(2) or match.group("url")
    filename_from_url = not bool(match.group(1))
    filename = match.group(1) or Path(urllib.parse.urlparse(url).path).name
    return Attachment(filename=urllib.parse.unquote(filename.strip()), url=url, filename_from_url=filename_from_url)


def download_attachment(attachment: Attachment, token: str | None, destination: Path) -> None:
    request = urllib.request.Request(attachment.url, headers={"User-Agent": "steam-achievement-translation-library-bot"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=45) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("上传文件超过 32 MiB 检查上限")
        total = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("上传文件超过 32 MiB 检查上限")
                handle.write(chunk)


def github_api_get(repo: str, token: str, path: str) -> Any:
    if not token:
        raise RuntimeError("缺少 GitHub token")
    encoded_repo = urllib.parse.quote(repo, safe="/")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{encoded_repo}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "steam-achievement-translation-library-bot",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pull_request_game_id(pull_request: dict[str, Any]) -> str:
    match = PR_GAME_ID_RE.search(str(pull_request.get("body") or ""))
    return match.group(1) if match else ""


def find_open_translation_pr(repo: str, token: str, game_id: str) -> dict[str, Any] | None:
    for page in range(1, 11):
        pulls = github_api_get(repo, token, f"/pulls?state=open&base=main&per_page=100&page={page}")
        if not isinstance(pulls, list):
            raise RuntimeError("GitHub open PR API 返回了无效数据")
        for pull_request in pulls:
            if not isinstance(pull_request, dict):
                continue
            head = pull_request.get("head") if isinstance(pull_request.get("head"), dict) else {}
            if not str(head.get("ref") or "").startswith("translation-library/"):
                continue
            if pull_request_game_id(pull_request) == game_id:
                return pull_request
        if len(pulls) < 100:
            return None
    raise RuntimeError("open PR 数量超过自动检查上限")
