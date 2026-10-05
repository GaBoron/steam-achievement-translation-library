"""Game-local proposals awaiting publication to the authoritative Catalog V2."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import catalog_v2
from recycle_bin import recycle_path


ROOT = catalog_v2.REPO_ROOT


def submission_path(game_id: str, *, root: Path = ROOT) -> Path:
    if not game_id.isascii() or not game_id.isdigit():
        raise ValueError(f"Invalid submission app ID: {game_id!r}")
    return root / "files" / game_id / "submission.json"


def load_submissions(*, root: Path = ROOT) -> dict[str, dict[str, Any]]:
    games: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "files").glob("*/submission.json")):
        game_id = path.parent.name
        if path.is_symlink() or not path.resolve().is_relative_to((root / "files").resolve()):
            raise ValueError(f"Submission must be a regular game-local file: {path}")
        if path != submission_path(game_id, root=root):
            raise ValueError(f"Invalid submission path: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"version", "games"}:
            raise ValueError(f"Invalid submission envelope: {path}")
        catalog_v2.validate_catalog(value)
        if set(value["games"]) != {game_id}:
            raise ValueError(f"Submission must describe only app ID {game_id}: {path}")
        if path.read_text(encoding="utf-8") != submission_text(game_id, value["games"][game_id]):
            raise ValueError(f"Submission is not canonical: {path}")
        games[game_id] = value["games"][game_id]
    return games


def submission_text(game_id: str, game: dict[str, Any]) -> str:
    value = {"version": 2, "games": {game_id: game}}
    catalog_v2.validate_catalog(value)
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def with_submissions(catalog: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    result = copy.deepcopy(catalog)
    result["games"].update(load_submissions(root=root))
    return catalog_v2.validate_catalog(result)


def load_submission_catalog(*, root: Path = ROOT) -> dict[str, Any]:
    return with_submissions(catalog_v2.load_catalog(root=root), root=root)


def write_submission_entry(entry: dict[str, Any], *, previous_game_id: str = "", root: Path = ROOT) -> None:
    game_id = str(entry.get("game_id") or "")
    path = submission_path(game_id, root=root)
    if previous_game_id and previous_game_id != game_id:
        published = catalog_v2.load_catalog(root=root)["games"]
        if previous_game_id in published or game_id in published:
            raise ValueError("App ID changes are only allowed for a new, unpublished game.")
    game = catalog_v2.catalog_from_legacy_index({"entries": [entry]})["games"][game_id]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(submission_text(game_id, game), encoding="utf-8", newline="\n")
    if previous_game_id and previous_game_id != game_id:
        old_path = submission_path(previous_game_id, root=root)
        if old_path.is_file():
            recycle_path(old_path, boundary=root / "files")


def recycle_published_submissions(catalog: dict[str, Any], *, root: Path = ROOT) -> None:
    for game_id, game in load_submissions(root=root).items():
        if catalog["games"].get(game_id) != game:
            raise ValueError(f"Refusing to consume unpublished submission: {game_id}")
        recycle_path(submission_path(game_id, root=root), boundary=root / "files")
