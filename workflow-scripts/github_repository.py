"""Narrow GitHub repository API adapter used by automation workflows."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


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


def close_issue(repo: str, token: str, issue_number: int) -> None:
    github_request(
        "PATCH",
        repo,
        token,
        f"/issues/{issue_number}",
        {"state": "closed", "state_reason": "completed"},
    )


def close_pull_request(repo: str, token: str, pr_number: int) -> None:
    github_request("PATCH", repo, token, f"/pulls/{pr_number}", {"state": "closed"})


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
            raise RuntimeError("GitHub PR comments API 返回了无效数据")
        comments.extend(comment for comment in batch if isinstance(comment, dict))
        if len(batch) < 100:
            return comments
    raise RuntimeError("PR 评论数量超过自动检查上限")
