"""Keep legacy-default downloads beside the canonical BIN and its JSON sidecar."""
from __future__ import annotations

import re
import shutil
from pathlib import Path


def synchronize_default_schema(game_id: str, *, root: Path, include_json: bool = False) -> None:
    if not re.fullmatch(r"[1-9][0-9]*", game_id):
        raise ValueError(f"Invalid compatibility app ID: {game_id!r}")
    boundary = root.resolve(strict=True)
    source = boundary / "files" / game_id / "default" / f"UserGameStatsSchema_{game_id}.bin"
    destination = source.parent.parent / source.name
    pairs = [(source, destination)]
    if include_json:
        pairs.append((source.with_suffix(".json"), destination.with_suffix(".json")))
    for source_path, destination_path in pairs:
        if any(path.is_symlink() or not path.resolve().is_relative_to(boundary) for path in (source_path, destination_path)):
            raise ValueError(f"Compatibility path escapes its repository: {destination_path}")
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing canonical schema artifact: {source_path}")
    for source_path, destination_path in pairs:
        if not destination_path.is_file() or destination_path.read_bytes() != source_path.read_bytes():
            shutil.copyfile(source_path, destination_path)
