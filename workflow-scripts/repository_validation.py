"""Catalog V2, schema, and generated-artifact repository validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import catalog_v2
import translation_json
from pr_submission_data import with_submissions
from generate_statistics_svg import build_statistics, render_svg
from steam_schema import achievement_rows, language_coverage, load_schema, schema_languages, sha256, validate_schema_structure


ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = ROOT / "files"
STATISTICS_PATH = ROOT / "docs" / "statistics" / "library-statistics.svg"


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


def _metadata_mismatch(report: CheckReport, message: str, *, allowed: bool) -> None:
    if allowed:
        report.warn(f"stale Catalog V2 metadata allowed for translation PR: {message}")
    else:
        report.error(message)


def _check_schema(
    report: CheckReport,
    game_id: str,
    variant_id: str,
    variant: dict,
    expected_paths: set[Path],
    *,
    allow_stale_index_metadata: bool,
    strict_language_coverage: bool,
) -> None:
    relative = catalog_v2.schema_relative_path(game_id, variant_id)
    path = ROOT / Path(*PurePosixPath(relative).parts)
    expected_paths.add(path.resolve())
    if not path.is_file():
        report.error(f"{game_id}: indexed schema is missing: {relative}")
        return
    try:
        data, nodes = load_schema(path)
        rows = validate_schema_structure(data, nodes)
    except (OSError, UnicodeError, EOFError, ValueError, NotImplementedError) as exc:
        report.error(f"{game_id}: invalid schema {relative}: {exc}")
        return
    report.checked_files += 1
    derived_languages = schema_languages(nodes)
    comparisons = {
        "size": (variant.get("size"), len(data)),
        "SHA-256": (variant.get("sha256"), sha256(data)),
        "achievement count": (variant.get("achievements"), len(rows)),
        "languages": (variant.get("languages"), derived_languages),
    }
    for label, (indexed, actual) in comparisons.items():
        if indexed != actual:
            _metadata_mismatch(
                report,
                f"{game_id}/{variant_id}: {label} mismatch: index={indexed!r}, actual={actual!r}",
                allowed=allow_stale_index_metadata,
            )
    checked_rows = achievement_rows(nodes, derived_languages)
    _coverage, missing = language_coverage(checked_rows, derived_languages)
    for language, missing_ids in missing.items():
        if not missing_ids:
            continue
        message = (
            f"{game_id}/{variant_id}: {language} is incomplete for {len(missing_ids)} achievements "
            f"({', '.join(missing_ids[:5])})"
        )
        report.error(message) if strict_language_coverage else report.warn(message)
    expected_json = translation_json.render_translation(game_id, variant_id, data, nodes)
    json_error = translation_json.check_translation(path, expected_json)
    if json_error:
        report.error(f"{game_id}/{variant_id}: {json_error}")
    expected_metadata = {"version": 1, "size": len(expected_json.encode("utf-8"))}
    if variant.get("json") != expected_metadata:
        _metadata_mismatch(report, f"{game_id}/{variant_id}: JSON metadata mismatch", allowed=allow_stale_index_metadata)


def _check_unindexed_schemas(report: CheckReport, paths: set[Path], *, allowed: bool) -> None:
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        if not allowed:
            report.error(f"unindexed schema file: {relative}")
            continue
        game_id = path.stem.removeprefix("UserGameStatsSchema_")
        try:
            data, nodes = load_schema(path)
            validate_schema_structure(data, nodes)
        except (OSError, UnicodeError, EOFError, ValueError, NotImplementedError) as exc:
            report.error(f"invalid unindexed schema {relative}: {exc}")
            continue
        report.checked_files += 1
        # Contribution PRs generate their own JSON before the catalog refresh.
        variant_id = path.parent.name
        expected_json = translation_json.render_translation(game_id, variant_id, data, nodes)
        json_error = translation_json.check_translation(path, expected_json)
        if json_error:
            report.error(f"{relative}: {json_error}")


def check_repository(
    *,
    strict_language_coverage: bool = False,
    allow_unindexed_schema_files: bool = False,
    allow_stale_index_metadata: bool = False,
    allow_stale_derived_artifacts: bool = False,
    allow_pending_submissions: bool = False,
    strict_game_ids: set[str] | None = None,
) -> CheckReport:
    report = CheckReport()

    def derived_mismatch(message: str) -> None:
        if allow_stale_derived_artifacts or allow_pending_submissions:
            report.warn(f"stale derived catalog artifact allowed for translation PR: {message}")
        else:
            report.error(message)
    manifests = sorted(FILES_ROOT.glob("*/manifest.json"))
    if manifests:
        report.error(f"per-game manifest.json files are no longer allowed ({len(manifests)} found)")
    try:
        catalog = catalog_v2.load_catalog(root=ROOT)
    except (OSError, UnicodeError, ValueError) as exc:
        report.error(f"cannot read authoritative index-v2.json: {exc}")
        return report
    try:
        actual_catalog_text = (ROOT / "index-v2.json").read_text(encoding="utf-8")
        if actual_catalog_text != catalog_v2.canonical_catalog_text(catalog):
            report.error("index-v2.json is not in canonical one-game-per-line format")
    except (OSError, UnicodeError) as exc:
        report.error(f"cannot verify index-v2.json formatting: {exc}")

    try:
        effective = with_submissions(catalog, root=ROOT)
        if effective != catalog:
            derived_mismatch("index-v2.json has unpublished game-local submissions")
        catalog = effective
    except (OSError, UnicodeError, ValueError) as exc:
        report.error(f"invalid game-local submission: {exc}")
        return report

    if (ROOT / "index.json").exists():
        report.error("Removed V1 index.json must not be reintroduced")

    expected_paths: set[Path] = set()
    for game_id, game in catalog["games"].items():
        report.checked_entries += 1
        for variant_id, variant in game["variants"].items():
            _check_schema(
                report,
                game_id,
                variant_id,
                variant,
                expected_paths,
                allow_stale_index_metadata=allow_stale_index_metadata,
                strict_language_coverage=strict_language_coverage or game_id in (strict_game_ids or set()),
            )

    actual_schemas = {path.resolve() for path in FILES_ROOT.rglob("*.bin") if path.is_file()}
    _check_unindexed_schemas(report, actual_schemas - expected_paths, allowed=allow_unindexed_schema_files)
    for path in FILES_ROOT.rglob("UserGameStatsSchema_*.json"):
        if len(path.relative_to(FILES_ROOT).parts) == 2:
            report.error(f"Translation JSON must be inside a variant directory: {path.relative_to(ROOT).as_posix()}")
        elif not path.with_suffix(".bin").is_file():
            report.error(f"orphan translation JSON: {path.relative_to(ROOT).as_posix()}")
    for path in FILES_ROOT.rglob("*.md"):
        report.error(f"Review Markdown does not belong in translation data: {path.relative_to(ROOT).as_posix()}")

    try:
        if STATISTICS_PATH.read_text(encoding="utf-8") != render_svg(build_statistics(catalog)):
            derived_mismatch("library-statistics.svg is out of sync with index-v2.json")
    except (OSError, UnicodeError, TypeError, ValueError, AttributeError) as exc:
        report.error(f"cannot verify generated catalog projections: {exc}")
    return report
