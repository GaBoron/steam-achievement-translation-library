#!/usr/bin/env python3
"""Synchronize generated index files after a direct index.json edit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "index.json"
FILES_ROOT = ROOT / "files"
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def load_index(path: Path) -> dict[str, Any]:
    index = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(index, dict) or not isinstance(index.get("entries"), list):
        raise ValueError(f"{path.name} must contain an object with an entries array")
    return index


def index_at_ref(ref: str, *, root: Path = ROOT) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{ref}:index.json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    index = json.loads(result.stdout)
    if not isinstance(index, dict) or not isinstance(index.get("entries"), list):
        raise ValueError(f"index.json at {ref} must contain an object with an entries array")
    return index


def entries_by_game_id(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for raw_entry in index.get("entries", []):
        if not isinstance(raw_entry, dict):
            raise ValueError("index.json contains a non-object entry")
        game_id = str(raw_entry.get("game_id") or "")
        if not game_id.isdigit():
            raise ValueError(f"entry has an invalid Steam app ID: {game_id!r}")
        if game_id in entries:
            raise ValueError(f"duplicate Steam app ID: {game_id}")
        entries[game_id] = raw_entry
    return entries


def _validated_schema_path(game_id: str, value: Any, *, multi_file: bool) -> str:
    raw_path = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw_path)
    expected_name = f"UserGameStatsSchema_{game_id}.bin"
    if (
        not raw_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(path.parts) not in ({3, 4} if multi_file else {3})
        or path.parts[:2] != ("files", game_id)
        or path.name != expected_name
    ):
        raise ValueError(f"unsafe or non-canonical schema path for {game_id}: {raw_path!r}")
    if len(path.parts) == 4 and not VARIANT_ID_RE.fullmatch(path.parts[2]):
        raise ValueError(f"invalid schema variant directory for {game_id}: {path.parts[2]!r}")
    return path.as_posix()


def entry_schema_files(entry: dict[str, Any]) -> tuple[str, ...]:
    """Return canonical files for legacy single-file and explicit multi-file entries."""
    game_id = str(entry.get("game_id") or "")
    if not game_id.isdigit():
        raise ValueError(f"entry has an invalid Steam app ID: {game_id!r}")
    primary_file = _validated_schema_path(game_id, entry.get("schema_file"), multi_file=False)
    raw_variants = entry.get("schema_files")
    if not isinstance(raw_variants, list) or not raw_variants:
        return (primary_file,)

    paths: list[str] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise ValueError(f"schema_files for {game_id} contains a non-object variant")
        path = _validated_schema_path(
            game_id,
            raw_variant.get("schema_file") or raw_variant.get("path"),
            multi_file=True,
        )
        if path in paths:
            raise ValueError(f"schema_files for {game_id} contains duplicate path {path}")
        paths.append(path)
    if primary_file not in paths:
        raise ValueError(f"schema_files for {game_id} does not contain primary file {primary_file}")
    return tuple(paths)


def removed_entry_files(previous_index: dict[str, Any], current_index: dict[str, Any]) -> tuple[str, ...]:
    previous = entries_by_game_id(previous_index)
    current = entries_by_game_id(current_index)
    current_files = {
        schema_file
        for entry in current.values()
        for schema_file in entry_schema_files(entry)
    }
    removed: list[str] = []
    for game_id in sorted(set(previous) - set(current), key=int):
        for schema_file in entry_schema_files(previous[game_id]):
            if schema_file in current_files:
                raise ValueError(f"removed entry {game_id} still shares schema path {schema_file}")
            removed.append(schema_file)
    return tuple(removed)


def remove_deleted_entry_files(
    root: Path,
    previous_index: dict[str, Any],
    current_index: dict[str, Any],
) -> tuple[str, ...]:
    removed: list[str] = []
    files_root = (root / "files").resolve()
    affected_game_roots: set[Path] = set()
    for relative_path in removed_entry_files(previous_index, current_index):
        parts = PurePosixPath(relative_path).parts
        game_root = (files_root / parts[1]).resolve()
        target = (root / Path(*parts)).resolve()
        target.relative_to(game_root)
        affected_game_roots.add(game_root)
        if target.exists() and not target.is_file():
            raise ValueError(f"indexed schema path is not a file: {relative_path}")
        if target.is_file():
            target.unlink()
            removed.append(relative_path)
        parent = target.parent
        while parent != files_root and parent.is_relative_to(files_root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    for game_root in sorted(affected_game_roots):
        if game_root.exists():
            leftovers = sorted(
                path.relative_to(root).as_posix()
                for path in game_root.rglob("*")
                if path.is_file()
            )
            if leftovers:
                raise RuntimeError(
                    f"removed index entry left undeclared files under {game_root.relative_to(root).as_posix()}: "
                    + ", ".join(leftovers)
                )
    return tuple(removed)


def synchronize(previous_ref: str, *, root: Path = ROOT) -> tuple[str, ...]:
    current_index = load_index(root / "index.json")
    previous_index = index_at_ref(previous_ref, root=root)
    removed = remove_deleted_entry_files(root, previous_index, current_index)

    # Import at the composition boundary so deletion planning remains independently testable.
    import library_submission_bot as library

    library.write_index(current_index)
    library.write_human_index(current_index)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-ref", required=True, help="Git ref containing index.json before the edit.")
    args = parser.parse_args()
    removed = synchronize(args.previous_ref)
    if removed:
        print("Removed schema files for deleted index entries:")
        for path in removed:
            print(f"- {path}")
    else:
        print("No indexed schema files needed removal.")
    print("Synchronized index.json, INDEX.md, and INDEX_EN.md.")


if __name__ == "__main__":
    main()
