"""Publish all merged game proposals, regenerating from main on push races."""
from __future__ import annotations

import sys
from typing import Any

import catalog_v2
from achievement_catalog import write_entry_achievement_catalogs
from catalog_refresh import refresh_catalog
from legacy_pr_schema import normalize_legacy_pr_schema_paths
from pr_git import configure_git_identity, run
from pr_metadata import entry_from_metadata, parse_pr_metadata
from pr_submission_data import load_submissions, recycle_published_submissions, write_submission_entry


ROOT = catalog_v2.REPO_ROOT
PUBLICATION_PATHS = [
    "files", "index.json", "index-v2.json", "INDEX.md", "INDEX_EN.md",
    "docs/statistics/library-statistics.svg",
]


def _recover_legacy_submission(pr: dict[str, Any]) -> None:
    """Recover only an absent historical game; never replay an older PR over main."""
    meta = parse_pr_metadata(pr)
    game_id = str(meta.get("game_id") or "")
    if not game_id or game_id in catalog_v2.load_catalog(root=ROOT)["games"] or game_id in load_submissions(root=ROOT):
        return
    if meta.get("kind") == "outdated":
        raise ValueError(f"Reported game is absent from main: {game_id}")
    entry = entry_from_metadata(meta)
    normalize_legacy_pr_schema_paths(entry, context="merged PR")
    write_entry_achievement_catalogs(entry)
    write_submission_entry(entry, root=ROOT)


def refresh_merged_pr_catalog(event: dict[str, Any], repo: str, token: str) -> bool:
    pr = event.get("pull_request") or {}
    if not pr.get("merged") or (pr.get("base") or {}).get("ref") != "main":
        return False
    configure_git_identity()
    for attempt in range(3):
        # New PRs carry immutable, game-local proposals. Every retry consumes
        # all proposals currently merged, regardless of which event woke us.
        _recover_legacy_submission(pr)
        catalog = refresh_catalog(catalog_v2.load_catalog(root=ROOT), root=ROOT)
        run([sys.executable, "workflow-scripts/check_repository.py"])
        recycle_published_submissions(catalog, root=ROOT)
        run(["git", "add", "-A", "--", *PUBLICATION_PATHS])
        if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
            return False
        run(["git", "commit", "-m", "chore: publish merged game submissions"])
        push = run(["git", "push", "origin", "HEAD:main"], check=False)
        if push.returncode == 0:
            return True
        if attempt == 2:
            raise RuntimeError(f"Could not publish catalog after three attempts: {push.stderr.strip()}")
        run(["git", "fetch", "origin", "main"])
        # The failed commit contains generated projections only. Start a new
        # publication from the latest main instead of rebasing stale indexes.
        run(["git", "checkout", "--detach", "origin/main"])
    return False
