#!/usr/bin/env python3
"""Command routing for translation PR maintenance and finalization."""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

from catalog_finalization import publish_pending_catalog
from contribution_attribution import merge_commit_body
from github_repository import github_request
from pr_comment_workflow import handle_comment, mark_wait_for_update
from pr_finalization import finalize_merged_pr
from pr_metadata import is_translation_pr


def finalize_pr_number(repo: str, token: str, pr_number: int) -> None:
    pr = github_request("GET", repo, token, f"/pulls/{pr_number}")
    if not pr:
        raise RuntimeError(f"Pull request #{pr_number} was not found.")
    if not pr.get("merged"):
        raise RuntimeError(f"Pull request #{pr_number} is not merged.")
    if not is_translation_pr(pr, repo):
        raise RuntimeError(f"Pull request #{pr_number} is not a translation PR for this repository's main branch.")
    publish_pending_catalog()
    finalize_merged_pr(pr, repo, token)


def finalize_head_branch(repo: str, token: str, head_branch: str) -> None:
    if not head_branch.startswith("translation-library/"):
        raise ValueError("The head branch must start with translation-library/.")
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
        if pr.get("merged_at") and is_translation_pr(pr, repo)
    ]
    if not merged_numbers:
        raise RuntimeError(f"No merged translation PR was found for {head_branch}.")
    for number in sorted(set(merged_numbers)):
        finalize_pr_number(repo, token, number)


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain translation PR metadata, comments, and labels.")
    parser.add_argument("--event", type=Path, help="GitHub event JSON path")
    parser.add_argument("--repo", default="", help="owner/repo")
    parser.add_argument("--token", default="", help="GitHub token")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mark-wait-for-update", action="store_true")
    mode.add_argument("--handle-comment", action="store_true")
    mode.add_argument("--merge-commit-body", action="store_true", help="Print the merge message with contribution credits")
    mode.add_argument("--finalize-pr", type=int, help="Fetch and finalize a merged PR by number")
    mode.add_argument("--finalize-head-branch", help="Find and finalize merged PRs from a head branch")
    args = parser.parse_args()

    if not args.repo or not args.token:
        parser.error("--repo and --token are required")
    if args.finalize_pr is not None:
        if args.finalize_pr < 1:
            parser.error("--finalize-pr requires a positive PR number")
        finalize_pr_number(args.repo, args.token, args.finalize_pr)
        return
    if args.finalize_head_branch is not None:
        finalize_head_branch(args.repo, args.token, args.finalize_head_branch)
        return
    if args.event is None:
        parser.error("--event is required for comment and review handlers")
    event = json.loads(args.event.read_text(encoding="utf-8"))
    if args.mark_wait_for_update:
        mark_wait_for_update(args.repo, args.token, event)
    elif args.merge_commit_body:
        print(merge_commit_body(args.repo, args.token, event))
    else:
        handle_comment(args.repo, args.token, event)


if __name__ == "__main__":
    main()
