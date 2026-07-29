"""Post-merge notifications and cleanup for translation pull requests."""
from __future__ import annotations

import urllib.parse
from typing import Any

from github_repository import close_issue, comment_issue_once, github_request, lock_issue
from pr_git import delete_pr_branch
from pr_metadata import (
    fulfilled_petition_comment,
    merged_thanks_comment,
    parse_pr_metadata,
    pr_kind,
    pr_labels,
    translation_petition_game_id,
)


TRANSLATION_PETITION_LABEL = "翻译请愿"
TRANSLATION_PETITION_FULFILLED_MARKER = "translation-library-petition-fulfilled"


def open_translation_petitions(repo: str, token: str) -> list[dict[str, Any]]:
    petitions: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "state": "open",
            "labels": TRANSLATION_PETITION_LABEL,
            "per_page": "100",
            "page": str(page),
        })
        batch = github_request("GET", repo, token, f"/issues?{query}") or []
        petitions.extend(
            issue for issue in batch
            if not issue.get("pull_request") and TRANSLATION_PETITION_LABEL in pr_labels(issue)
        )
        if len(batch) < 100:
            break
        page += 1
    return petitions


def notify_fulfilled_translation_petitions(pr: dict[str, Any], repo: str, token: str) -> int:
    if pr_kind(pr) != "translation-contribution":
        return 0
    meta = parse_pr_metadata(pr)
    game_id = str(meta.get("game_id") or "")
    if not game_id:
        return 0
    body = fulfilled_petition_comment(meta, repo)
    notified = 0
    for petition in open_translation_petitions(repo, token):
        if translation_petition_game_id(petition) != game_id:
            continue
        issue_number = int(petition["number"])
        comment_issue_once(
            repo,
            token,
            issue_number,
            body,
            TRANSLATION_PETITION_FULFILLED_MARKER,
        )
        close_issue(repo, token, issue_number)
        notified += 1
    return notified


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
    notify_fulfilled_translation_petitions(pr, repo, token)
    delete_pr_branch(repo, token, pr)
    lock_issue(repo, token, pr_number)
