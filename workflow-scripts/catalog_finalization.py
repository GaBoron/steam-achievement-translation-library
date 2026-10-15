"""Publish all merged game proposals, regenerating from main on push races."""
from __future__ import annotations

import sys
import time
from typing import Any

import catalog_v2
from catalog_refresh import refresh_catalog
from pr_git import configure_git_identity, run
from pr_submission_data import recycle_published_submissions


ROOT = catalog_v2.REPO_ROOT
PUBLICATION_PATHS = [
    "files", "index-v2.json",
    "docs/statistics/library-statistics.svg",
]
PUBLICATION_ATTEMPTS = 8


def refresh_merged_pr_catalog(event: dict[str, Any], repo: str, token: str) -> bool:
    pr = event.get("pull_request") or {}
    if not pr.get("merged") or (pr.get("base") or {}).get("ref") != "main":
        return False
    configure_git_identity()
    for attempt in range(PUBLICATION_ATTEMPTS):
        # New PRs carry immutable, game-local proposals. Every retry consumes
        # all proposals currently merged, regardless of which event woke us.
        catalog = refresh_catalog(catalog_v2.load_catalog(root=ROOT), root=ROOT)
        recycle_published_submissions(catalog, root=ROOT)
        run([sys.executable, "workflow-scripts/check_repository.py"])
        run(["git", "add", "-A", "--", *PUBLICATION_PATHS])
        if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
            return False
        run(["git", "commit", "-m", "chore: publish merged game submissions"])
        push = run(["git", "push", "origin", "HEAD:main"], check=False)
        if push.returncode == 0:
            return True
        if attempt == PUBLICATION_ATTEMPTS - 1:
            raise RuntimeError(
                f"Could not publish catalog after {PUBLICATION_ATTEMPTS} attempts: {push.stderr.strip()}"
            )
        time.sleep(min(2 ** (attempt + 1), 15))
        run(["git", "fetch", "origin", "main"])
        # The failed commit contains generated projections only. Start a new
        # publication from the latest main instead of rebasing stale indexes.
        run(["git", "checkout", "--detach", "origin/main"])
    return False
