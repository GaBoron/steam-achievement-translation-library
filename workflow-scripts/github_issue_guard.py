#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

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
}

KIND_LABELS = {
    "translation-contribution": "翻译投稿",
    "update": "更新文件",
    "outdated": "报告过期",
}
LEGACY_LABELS = {
    "translation-contribution": "translation-contribution",
    "update": "update",
    "outdated": "outdated",
}


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
    if "### 成就 schema ZIP" in text or "### Achievement schema ZIP" in text:
        return "translation-contribution"
    return None


def add_issue_labels(repo: str, token: str, issue_number: int, labels: list[str]) -> None:
    for label in labels:
        ensure_label(repo, token, label)
    github_request("POST", repo, token, f"/issues/{issue_number}/labels", {"labels": labels})


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate translation library automation labels.")
    parser.add_argument("--event", type=Path, required=True, help="GitHub event JSON path")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/repo")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    args = parser.parse_args()

    if not args.repo or not args.token:
        raise SystemExit("Both --repo and --token are required.")
    event = json.loads(args.event.read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    labels = issue_labels(issue)
    for label in LABELS:
        ensure_label(args.repo, args.token, label)
    kind = infer_issue_kind(issue)
    if not kind:
        raise SystemExit("This workflow only handles translation submission, file update, or outdated report issues.")
    expected = KIND_LABELS[kind]
    if expected not in labels:
        add_issue_labels(args.repo, args.token, int(issue["number"]), [expected])
        labels.add(expected)
    active = sorted(label for label in KIND_LABELS.values() if label in labels)
    if len(active) > 1:
        raise SystemExit("每个 issue 只能使用一个自动化标签: " + ", ".join(active))


if __name__ == "__main__":
    main()
