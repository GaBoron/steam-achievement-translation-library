#!/usr/bin/env python3
"""Command routing for translation PR maintenance and finalization."""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

from catalog_finalization import refresh_merged_pr_catalog
from github_repository import github_request
from pr_comment_workflow import handle_comment, mark_wait_for_update
from pr_finalization import finalize_merged_pr


def finalize_pr_number(repo: str, token: str, pr_number: int) -> None:
    pr = github_request("GET", repo, token, f"/pulls/{pr_number}")
    if not pr:
        raise RuntimeError(f"Pull request #{pr_number} was not found.")
    if not pr.get("merged"):
        raise RuntimeError(f"Pull request #{pr_number} is not merged.")
    event = {"pull_request": pr}
    refresh_merged_pr_catalog(event, repo, token)
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
    parser.add_argument("--refresh-merged-pr", action="store_true")
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
    if args.refresh_merged_pr:
        if not args.repo or not args.token:
            raise SystemExit("--repo and --token are required")
        refresh_merged_pr_catalog(event, args.repo, args.token)
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
