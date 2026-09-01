#!/usr/bin/env python3
"""Refresh the issue payload before submission review."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from github_repository import github_request


def with_latest_issue(event: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(event)
    refreshed["issue"] = issue
    return refreshed


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh a GitHub issue event before review.")
    parser.add_argument("--event", type=Path, required=True, help="Original GitHub event JSON path")
    parser.add_argument("--output", type=Path, required=True, help="Refreshed event JSON path")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/repo")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    args = parser.parse_args()

    if not args.repo or not args.token:
        raise SystemExit("Both --repo and --token are required.")
    event = json.loads(args.event.read_text(encoding="utf-8"))
    issue_number = int((event.get("issue") or {}).get("number") or 0)
    if not issue_number:
        raise SystemExit("The event does not contain an issue number.")
    issue = github_request("GET", args.repo, args.token, f"/issues/{issue_number}")
    if not isinstance(issue, dict):
        raise SystemExit(f"GitHub did not return issue #{issue_number}.")
    args.output.write_text(
        json.dumps(with_latest_issue(event, issue), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
