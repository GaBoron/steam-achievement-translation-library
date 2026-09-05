#!/usr/bin/env python3
"""Command entry point for repository validation."""
from __future__ import annotations

import argparse

from repository_validation import CheckReport, check_repository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-language-coverage", action="store_true")
    parser.add_argument("--allow-unindexed-schema-files", action="store_true")
    parser.add_argument("--allow-stale-index-metadata", action="store_true")
    parser.add_argument("--allow-stale-derived-artifacts", action="store_true")
    args = parser.parse_args()
    report = check_repository(
        strict_language_coverage=args.strict_language_coverage,
        allow_unindexed_schema_files=args.allow_unindexed_schema_files,
        allow_stale_index_metadata=args.allow_stale_index_metadata,
        allow_stale_derived_artifacts=args.allow_stale_derived_artifacts,
    )
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


__all__ = ["CheckReport", "check_repository", "main"]
