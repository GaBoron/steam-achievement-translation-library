#!/usr/bin/env python3
"""Migrate the legacy v1 library layout to authoritative per-game manifests."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import library_index
import library_manifest


ROOT = Path(__file__).resolve().parent.parent


def _legacy_variant_sources(entry: dict[str, Any]) -> list[tuple[str, Path]]:
    game_id = str(entry.get("game_id") or "")
    raw_variants = entry.get("schema_files")
    if isinstance(raw_variants, list) and raw_variants:
        records = raw_variants
    else:
        records = [{"variant_id": "default", "schema_file": entry.get("schema_file")}]
    result: list[tuple[str, Path]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{game_id}: schema_files contains a non-object")
        variant_id = str(record.get("variant_id") or "").strip().lower()
        source = str(record.get("schema_file") or record.get("path") or "").replace("\\", "/")
        if not library_manifest.VARIANT_ID_RE.fullmatch(variant_id):
            raise ValueError(f"{game_id}: invalid variant ID {variant_id!r}")
        pure = PurePosixPath(source)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"{game_id}: unsafe schema path {source!r}")
        result.append((variant_id, ROOT / Path(*pure.parts)))
    return result


def migration_moves(index: dict[str, Any]) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []
    for entry in index.get("entries", []):
        if not isinstance(entry, dict):
            continue
        game_id = str(entry.get("game_id") or "")
        for variant_id, source in _legacy_variant_sources(entry):
            destination = ROOT / Path(*PurePosixPath(
                library_manifest.schema_relative_path(game_id, variant_id)
            ).parts)
            if source.resolve() == destination.resolve():
                continue
            if destination.is_file() and source.is_file():
                if destination.read_bytes() == source.read_bytes():
                    continue
                raise FileExistsError(f"migration destination differs: {destination.relative_to(ROOT)}")
            if destination.is_file() and not source.exists():
                continue
            if not source.is_file():
                raise FileNotFoundError(f"missing source schema: {source.relative_to(ROOT)}")
            if destination.exists():
                raise FileExistsError(f"migration destination already exists: {destination.relative_to(ROOT)}")
            moves.append((source, destination))
    return moves


def load_legacy_index(source_ref: str | None) -> dict[str, Any]:
    if source_ref:
        payload = subprocess.check_output(
            ["git", "show", source_ref],
            cwd=ROOT,
        )
        index = json.loads(payload)
    else:
        index = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or not isinstance(index.get("entries"), list):
        raise ValueError("index.json must contain an entries array")
    return index


def migrate(*, apply: bool, source_ref: str | None = None) -> tuple[list[tuple[Path, Path]], int]:
    index = load_legacy_index(source_ref)
    moves = migration_moves(index)
    if not apply:
        return moves, len(index["entries"])
    for source, destination in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    index["entries"] = library_index.sort_entries(index["entries"])
    manifests = library_manifest.write_manifests_from_legacy_index(index, root=ROOT)
    library_manifest.write_catalogs(manifests, root=ROOT)
    manifest_index = library_manifest.legacy_index_from_manifests(manifests)
    manifest_index["entries"] = library_index.sort_entries(manifest_index["entries"])
    library_index.write_human_index(manifest_index)
    return moves, len(index["entries"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Move schemas and write manifests/generated catalogs.")
    parser.add_argument(
        "--source-ref",
        help="Read the legacy index from a Git object such as HEAD:index.json.",
    )
    args = parser.parse_args()
    moves, manifest_count = migrate(apply=args.apply, source_ref=args.source_ref)
    action = "Migrated" if args.apply else "Would migrate"
    print(f"{action} {len(moves)} schema path(s) and {manifest_count} game manifest(s).")
    if not args.apply:
        print("Run again with --apply after reviewing the migration plan.")


if __name__ == "__main__":
    main()
