"""Keep V1 default BIN downloads without duplicating V2 translation JSON."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from recycle_bin import recycle_path


def _default_schema_paths(game_id: str, root: Path) -> tuple[Path, Path]:
    if not re.fullmatch(r"[1-9][0-9]*", game_id):
        raise ValueError(f"Invalid compatibility app ID: {game_id!r}")
    boundary = root.resolve(strict=True)
    source = boundary / "files" / game_id / "default" / f"UserGameStatsSchema_{game_id}.bin"
    destination = source.parent.parent / source.name
    for path in (source, destination, destination.with_suffix(".json")):
        if path.is_symlink() or not path.resolve().is_relative_to(boundary):
            raise ValueError(f"Compatibility path escapes its repository: {path}")
    return source, destination


def recycle_legacy_translation_json(game_id: str, *, root: Path) -> None:
    _source, destination = _default_schema_paths(game_id, root)
    legacy_json = destination.with_suffix(".json")
    if legacy_json.exists():
        if not legacy_json.is_file():
            raise ValueError(f"Legacy JSON path is not a file: {legacy_json}")
        recycle_path(legacy_json, boundary=legacy_json.parent)


def synchronize_default_schema(game_id: str, *, root: Path) -> None:
    source, destination = _default_schema_paths(game_id, root)
    if not source.is_file():
        raise FileNotFoundError(f"Missing canonical schema artifact: {source}")
    recycle_legacy_translation_json(game_id, root=root)
    if not destination.is_file() or destination.read_bytes() != source.read_bytes():
        shutil.copyfile(source, destination)
