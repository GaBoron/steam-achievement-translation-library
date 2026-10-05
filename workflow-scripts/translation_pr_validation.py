"""Enforce a single game's data-only diff before relaxing derived-index checks."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pr_submission_data import load_submissions
from repository_validation import CheckReport, ROOT, check_repository


def changed_game(base_ref: str, head_ref: str, *, root: Path = ROOT) -> tuple[str, bool]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base_ref}...{head_ref}"],
        cwd=root, check=True, capture_output=True,
    )
    paths = [value.decode("utf-8") for value in result.stdout.split(b"\0") if value]
    game_ids = set()
    has_schema_changes = False
    for path in paths:
        match = re.fullmatch(r"files/([0-9]+)/(.+)", path)
        if not match:
            raise ValueError(f"Translation PR cannot change a shared index or another repository file: {path}")
        game_id, local = match.groups()
        allowed = (
            local == "submission.json"
            or local == f"UserGameStatsSchema_{game_id}.bin"
            or re.fullmatch(
                rf"[a-z0-9][a-z0-9-]{{0,63}}/(?:achievements\.md|UserGameStatsSchema_{game_id}\.(?:bin|json))",
                local,
            )
        )
        if not allowed:
            raise ValueError(f"Unexpected translation PR file: {path}")
        game_ids.add(game_id)
        has_schema_changes |= path.endswith(".bin")
    if len(game_ids) != 1:
        raise ValueError("A translation PR must change exactly one game's directory.")
    game_id = next(iter(game_ids))
    if f"files/{game_id}/submission.json" not in paths:
        raise ValueError("Translation PR must include its game-local submission.json.")
    tree = subprocess.run(
        ["git", "ls-tree", "-r", "-z", head_ref, "--", f"files/{game_id}/"],
        cwd=root, check=True, capture_output=True,
    )
    for record in tree.stdout.split(b"\0"):
        if record and not record.startswith(b"100644 blob "):
            raise ValueError("Translation game data must contain only regular, non-executable files.")
    return game_id, has_schema_changes


def check_translation_pr(base_ref: str, head_ref: str) -> CheckReport:
    try:
        game_id, has_schema_changes = changed_game(base_ref, head_ref)
        if game_id not in load_submissions():
            raise ValueError(f"Missing submission metadata for {game_id}.")
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as exc:
        return CheckReport(errors=[str(exc)])
    return check_repository(
        allow_pending_submissions=True,
        strict_game_ids={game_id} if has_schema_changes else set(),
    )
