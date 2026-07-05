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
    "translation-contribution": {
        "color": "2da44e",
        "description": "New Steam achievement translation submission",
    },
    "update": {
        "color": "0969da",
        "description": "Update an existing achievement translation file",
    },
    "outdated": {
        "color": "bf8700",
        "description": "Report that an accepted translation file may be outdated",
    },
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
    active = sorted(labels & set(LABELS))
    for label in LABELS:
        ensure_label(args.repo, args.token, label)
    if not active:
        raise SystemExit("This workflow only handles issues labeled translation-contribution, update, or outdated.")
    if len(active) > 1:
        raise SystemExit("Use exactly one automation label per issue: " + ", ".join(active))


if __name__ == "__main__":
    main()
