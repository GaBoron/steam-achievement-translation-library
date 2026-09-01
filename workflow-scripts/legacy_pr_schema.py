"""Compatibility promotion for pull requests created before Catalog V2."""
from __future__ import annotations

import shutil
from typing import Any

from library_index import repository_path, schema_variant_relative_path


def normalize_legacy_pr_schema_paths(entry: dict[str, Any], *, context: str = "PR") -> bool:
    """Copy a pre-V2 default schema into its canonical variant path.

    The legacy root file remains in place as the V1 compatibility artifact.
    Returns whether legacy metadata was detected and normalized.
    """
    game_id = str(entry.get("game_id") or "").strip()
    legacy_path = f"files/{game_id}/UserGameStatsSchema_{game_id}.bin"
    canonical_path = schema_variant_relative_path(game_id, "default", True)
    records = entry.get("schema_files")
    legacy_seen = str(entry.get("schema_file") or "") == legacy_path
    if isinstance(records, list):
        legacy_seen = legacy_seen or any(
            isinstance(record, dict) and str(record.get("schema_file") or record.get("path") or "") == legacy_path
            for record in records
        )
    if not legacy_seen:
        return False

    source = repository_path(legacy_path)
    destination = repository_path(canonical_path)
    if not source.is_file():
        raise RuntimeError(f"{context} legacy schema file is missing: {legacy_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)

    if str(entry.get("schema_file") or "") == legacy_path:
        entry["schema_file"] = canonical_path
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict) and str(record.get("schema_file") or record.get("path") or "") == legacy_path:
                record["schema_file"] = canonical_path
    return True
