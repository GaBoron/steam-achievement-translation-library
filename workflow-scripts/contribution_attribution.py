"""Attribute submission commits and merges to verified GitHub accounts."""
from __future__ import annotations

import re
from typing import Any

from github_repository import github_request


GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
SOURCE_BRANCH = re.compile(r"translation-library/(?:issue|update|report)-([1-9][0-9]*)")


def github_commit_author(user: dict[str, Any] | None) -> str:
    if not user or user.get("type") != "User":
        return ""
    login = user.get("login")
    user_id = user.get("id")
    if (
        not isinstance(login, str)
        or not GITHUB_LOGIN.fullmatch(login)
        or login.casefold() == "ghost"
        or type(user_id) is not int
        or user_id <= 0
    ):
        return ""
    return f"{login} <{user_id}+{login}@users.noreply.github.com>"


def merge_commit_body(repo: str, token: str, event: dict[str, Any]) -> str:
    pr = event["pull_request"]
    reviewer = event["review"]["user"]["login"]
    authors: dict[int, str] = {}

    def remember(user: dict[str, Any] | None) -> None:
        if user and (author := github_commit_author(user)):
            authors.setdefault(user["id"], author)

    # The branch identifies the source Issue even if the PR body was edited.
    source = SOURCE_BRANCH.fullmatch(pr["head"]["ref"])
    if source:
        issue = github_request("GET", repo, token, f"/issues/{source[1]}", allow_404=True)
        if issue and not issue.get("pull_request"):
            remember(issue.get("user"))

    # Include people who supplied accepted revisions to this PR. Catalog credits
    # for older versions and merge commits that only sync main do not belong here.
    # GitHub's pull request commits endpoint returns at most 250 commits.
    for page in range(1, 4):
        path = f"/pulls/{int(pr['number'])}/commits?per_page=100&page={page}"
        commits = github_request("GET", repo, token, path) or []
        for commit in commits:
            if len(commit.get("parents", [])) == 1:
                remember(commit.get("author"))
        if len(commits) < 100:
            break

    body = f"Automatically merged after approval by @{reviewer}."
    if authors:
        body += "\n\n" + "\n".join(f"Co-authored-by: {author}" for author in authors.values())
    return body
