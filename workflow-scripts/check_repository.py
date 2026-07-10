#!/usr/bin/env python3
"""Validate translation data and generated indexes without modifying the repository."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from library_submission_bot import (
    FILES_ROOT,
    HUMAN_INDEX_EN_PATH,
    HUMAN_INDEX_PATH,
    INDEX_PATH,
    LANGUAGE_RE,
    achievement_rows,
    language_coverage,
    load_schema,
    render_human_index,
    repository_path,
    sha256,
    sort_entries,
    steam_store_id,
    validate_schema_structure,
    validated_entry_schema_variants,
)


@dataclass
class CheckReport:
    checked_entries: int = 0
    checked_files: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _check_schema_path(
    report: CheckReport,
    game_id: str,
    variant: dict[str, Any],
    expected_paths: set[Path],
) -> tuple[bytes, list[Any]] | None:
    schema_file = str(variant.get("schema_file") or "")
    try:
        path = repository_path(schema_file)
        path.relative_to(FILES_ROOT.resolve())
    except ValueError as exc:
        report.error(f"{game_id}: invalid schema path {schema_file!r}: {exc}")
        return None
    expected_paths.add(path)
    if not path.is_file():
        report.error(f"{game_id}: indexed schema is missing: {schema_file}")
        return None
    actual_size = path.stat().st_size
    expected_size = _integer(variant.get("file_size_bytes"))
    if expected_size is None:
        report.error(f"{game_id}: file_size_bytes is missing or invalid for {schema_file}")
    elif expected_size != actual_size:
        report.error(f"{game_id}: file size mismatch for {schema_file}: index={expected_size}, actual={actual_size}")
    try:
        data, nodes = load_schema(path)
        validate_schema_structure(data, nodes)
    except (OSError, UnicodeError, EOFError, ValueError, NotImplementedError) as exc:
        report.error(f"{game_id}: invalid schema {schema_file}: {exc}")
        return None
    report.checked_files += 1
    expected_hash = str(variant.get("sha256") or "")
    if not expected_hash:
        report.error(f"{game_id}: SHA-256 is missing for variant {variant.get('variant_id')}")
    elif sha256(data) != expected_hash:
        report.error(f"{game_id}: SHA-256 mismatch for variant {variant.get('variant_id')}")
    rows = achievement_rows(nodes, [])
    expected_count = _integer(variant.get("achievement_count"))
    if expected_count is None or expected_count != len(rows):
        report.error(
            f"{game_id}: achievement_count mismatch for variant {variant.get('variant_id')}: "
            f"index={variant.get('achievement_count')!r}, actual={len(rows)}"
        )
    return data, nodes


def check_repository(*, strict_language_coverage: bool = False) -> CheckReport:
    report = CheckReport()
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.error(f"cannot read index.json: {exc}")
        return report
    if not isinstance(index, dict) or not isinstance(index.get("entries"), list):
        report.error("index.json must contain an object with an entries array")
        return report

    entries = index["entries"]
    if all(isinstance(entry, dict) for entry in entries) and entries != sort_entries(entries):
        report.error("index.json entries are not in canonical game-name/app-ID order")

    seen_ids: set[str] = set()
    expected_paths: set[Path] = set()
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            report.error("index.json contains a non-object entry")
            continue
        report.checked_entries += 1
        game_id = str(raw_entry.get("game_id") or "")
        if not game_id.isdigit():
            report.error(f"entry has an invalid Steam app ID: {game_id!r}")
        elif game_id in seen_ids:
            report.error(f"duplicate Steam app ID: {game_id}")
        seen_ids.add(game_id)

        if not str(raw_entry.get("game_name") or "").strip():
            report.error(f"{game_id}: game_name is empty")
        if steam_store_id(str(raw_entry.get("store_url") or "")) != game_id:
            report.error(f"{game_id}: store_url does not match the Steam app ID")

        languages = raw_entry.get("languages")
        if not isinstance(languages, list) or not languages:
            report.error(f"{game_id}: languages must be a non-empty array")
            languages = []
        normalized_languages = [str(language) for language in languages]
        invalid_languages = [language for language in normalized_languages if not LANGUAGE_RE.fullmatch(language)]
        if invalid_languages:
            report.error(f"{game_id}: invalid language codes: {', '.join(invalid_languages)}")
        if len(normalized_languages) != len(set(normalized_languages)):
            report.error(f"{game_id}: duplicate language codes")

        try:
            variants = validated_entry_schema_variants(raw_entry, require_metadata=True)
        except ValueError as exc:
            report.error(f"{game_id}: invalid schema variant metadata: {exc}")
            continue
        primary_result: tuple[bytes, list[Any]] | None = None
        variant_hashes: dict[str, str] = {}
        for variant in variants:
            schema_file = str(variant.get("schema_file") or "")
            result = _check_schema_path(report, game_id, variant, expected_paths)
            if variant.get("primary"):
                primary_result = result
            if result is not None:
                variant_data, variant_nodes = result
                digest = sha256(variant_data)
                duplicate_id = variant_hashes.get(digest)
                if duplicate_id is not None:
                    report.error(
                        f"{game_id}: variants {duplicate_id} and {variant.get('variant_id')} have identical files"
                    )
                variant_hashes[digest] = str(variant.get("variant_id"))
                variant_rows = achievement_rows(variant_nodes, normalized_languages)
                _coverage, missing = language_coverage(variant_rows, normalized_languages)
                for language, missing_ids in missing.items():
                    if not missing_ids:
                        continue
                    message = (
                        f"{game_id}/{variant.get('variant_id')}: {language} is incomplete for "
                        f"{len(missing_ids)} achievements ({', '.join(missing_ids[:5])})"
                    )
                    if strict_language_coverage:
                        report.error(message)
                    else:
                        report.warn(message)
        if primary_result is None:
            continue

        data, nodes = primary_result
        if sha256(data) != str(raw_entry.get("sha256") or ""):
            report.error(f"{game_id}: primary schema SHA-256 does not match index.json")
        rows = achievement_rows(nodes, normalized_languages)
        expected_count = _integer(raw_entry.get("achievement_count"))
        if expected_count is None or expected_count != len(rows):
            report.error(f"{game_id}: achievement_count mismatch: index={raw_entry.get('achievement_count')!r}, actual={len(rows)}")

    actual_paths = {path.resolve() for path in FILES_ROOT.rglob("*.bin") if path.is_file()}
    for path in sorted(actual_paths - expected_paths):
        report.error(f"unindexed schema file: {path.relative_to(FILES_ROOT.parent).as_posix()}")

    try:
        expected_zh, expected_en = render_human_index(index)
        if HUMAN_INDEX_PATH.read_text(encoding="utf-8") != expected_zh:
            report.error("INDEX.md is out of sync with index.json")
        if HUMAN_INDEX_EN_PATH.read_text(encoding="utf-8") != expected_en:
            report.error("INDEX_EN.md is out of sync with index.json")
    except (OSError, UnicodeError, TypeError, ValueError, AttributeError) as exc:
        report.error(f"cannot verify generated Markdown indexes: {exc}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate every indexed schema and generated library index.")
    parser.add_argument(
        "--strict-language-coverage",
        action="store_true",
        help="Treat legacy incomplete language fields as errors instead of warnings.",
    )
    args = parser.parse_args()
    report = check_repository(strict_language_coverage=args.strict_language_coverage)
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")
    print(
        f"Checked {report.checked_entries} entries and {report.checked_files} schema files: "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)."
    )
    if report.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
