#!/usr/bin/env python3
"""Post-merge maintenance for translation library pull requests."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from library_submission_bot import load_index, upsert_index_entry

ROOT = Path(__file__).resolve().parent.parent


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, text=True, capture_output=True)


def pr_labels(pr: dict[str, Any]) -> set[str]:
    return {str(label.get("name") or "") for label in pr.get("labels", []) if isinstance(label, dict)}


def mark_source_pr(event: dict[str, Any]) -> bool:
    pr = event.get("pull_request") or {}
    labels = pr_labels(pr)
    body = str(pr.get("body") or "")
    game_id = extract_body_field(body, "Steam app ID")
    if not game_id:
        return False

    index = load_index()
    entry = next((item for item in index.get("entries", []) if str(item.get("game_id")) == game_id), None)
    if not entry:
        return False

    pr_url = str(pr.get("html_url") or "")
    merged_at = str(pr.get("merged_at") or "")
    changed = False

    if "outdated" in labels:
        outdated = entry.get("outdated") if isinstance(entry.get("outdated"), dict) else {}
        if pr_url and outdated.get("source_pr") != pr_url:
            outdated["source_pr"] = pr_url
            entry["outdated"] = outdated
            changed = True
    else:
        if pr_url and entry.get("source_pr") != pr_url:
            entry["source_pr"] = pr_url
            changed = True
        if merged_at and entry.get("updated_at") != merged_at:
            entry["updated_at"] = merged_at
            changed = True

    if not changed:
        return False
    upsert_index_entry(entry)
    return commit_and_push(pr_number=int(pr.get("number") or 0))


def extract_body_field(body: str, label: str) -> str:
    prefix = f"- {label}:"
    for line in body.splitlines():
        if line.startswith(prefix):
            value = line.removeprefix(prefix).strip()
            if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
                return value[1:-1].strip()
            return value
    return ""


def commit_and_push(pr_number: int) -> bool:
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run(["git", "add", "index.json", "INDEX.md", "INDEX_EN.md"])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False
    run(["git", "commit", "-m", f"data: record source PR for translation entry #{pr_number}"])
    run(["git", "push", "origin", "main"])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain index metadata after translation PR merges.")
    parser.add_argument("--event", type=Path, required=True, help="GitHub event JSON path")
    parser.add_argument("--mark-source-pr", action="store_true")
    args = parser.parse_args()

    event = json.loads(args.event.read_text(encoding="utf-8"))
    if args.mark_source_pr:
        mark_source_pr(event)


if __name__ == "__main__":
    main()
