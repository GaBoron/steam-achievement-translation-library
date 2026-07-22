#!/usr/bin/env python3
"""Commit validated issue changes, push/update the translation branch, and open a PR."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translation_pr_maintenance import ensure_label, github_request  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ADD_PATHS = ["files", ".github/translation-reports", "index.json", "INDEX.md", "INDEX_EN.md"]


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode != 0:
        command = " ".join(args)
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stdout}{result.stderr}")
    return result


def changed_paths() -> list[str]:
    result = run(["git", "status", "--porcelain", "--"] + ADD_PATHS)
    return [line for line in result.stdout.splitlines() if line.strip()]


def existing_pr(repo: str, token: str, branch: str) -> dict[str, Any] | None:
    owner = repo.split("/", 1)[0]
    query = f"state=open&head={owner}:{branch}&base=main"
    prs = github_request("GET", repo, token, f"/pulls?{query}") or []
    return prs[0] if prs else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--result", default="submission_result.json")
    parser.add_argument("--body", default="pr_body.md")
    parser.add_argument("--reviewer", default="GaBoron")
    args = parser.parse_args()

    result = json.loads((ROOT / args.result).read_text(encoding="utf-8"))
    branch = str(result["branch"])
    labels = [label.strip() for label in str(result.get("pr_labels") or "").split(",") if label.strip()]
    for label in labels:
        ensure_label(args.repo, args.token, label)

    if not changed_paths():
        raise RuntimeError("Validation succeeded but did not produce any PR changes.")

    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run(["git", "checkout", "-B", branch])
    run(["git", "add"] + ADD_PATHS)
    run(["git", "commit", "-m", str(result["commit_message"])])
    run(["git", "remote", "set-url", "origin", f"https://x-access-token:{args.token}@github.com/{args.repo}.git"])
    run(["git", "push", "--force", "origin", f"HEAD:{branch}"])

    body = (ROOT / args.body).read_text(encoding="utf-8")
    pr = existing_pr(args.repo, args.token, branch)
    if pr:
        pr_number = int(pr["number"])
        pr = github_request("PATCH", args.repo, args.token, f"/pulls/{pr_number}", {"title": result["pr_title"], "body": body})
    else:
        pr = github_request("POST", args.repo, args.token, "/pulls", {"title": result["pr_title"], "head": branch, "base": "main", "body": body, "maintainer_can_modify": True})
        pr_number = int(pr["number"])

    if labels:
        github_request("POST", args.repo, args.token, f"/issues/{pr_number}/labels", {"labels": labels})
    if args.reviewer:
        try:
            github_request("POST", args.repo, args.token, f"/pulls/{pr_number}/requested_reviewers", {"reviewers": [args.reviewer]}, allow_422=True)
        except (RuntimeError, urllib.error.URLError) as exc:
            print(f"warning: could not request reviewer {args.reviewer}: {exc}", file=sys.stderr)

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"pull-request-url={pr['html_url']}\n")
            handle.write(f"pull-request-number={pr_number}\n")
    print(pr["html_url"])


if __name__ == "__main__":
    main()
