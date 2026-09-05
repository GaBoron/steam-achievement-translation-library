"""Catalog V2, schema, and generated-artifact repository validation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import achievement_catalog
import catalog_v2
from generate_statistics_svg import build_statistics, render_svg
from library_index import HUMAN_INDEX_EN_PATH, HUMAN_INDEX_PATH, render_human_index, sort_entries
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


def _check_achievement_catalog(report: CheckReport, schema_path: Path, expected: str) -> None:
    path = schema_path.with_name("achievements.md")
    if not path.is_file():
        report.error(f"missing achievement catalog: {path.relative_to(ROOT).as_posix()}")
        return
    try:
        actual = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        report.error(f"cannot read {path.relative_to(ROOT).as_posix()}: {exc}")
        return
    if actual != expected:
        report.error(f"achievement catalog is out of sync: {path.relative_to(ROOT).as_posix()}")


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
    _check_achievement_catalog(
        report,
        path,
        achievement_catalog.render_achievement_catalog(path.name, checked_rows, derived_languages),
    )


def _check_unindexed_schemas(report: CheckReport, paths: set[Path], *, allowed: bool) -> None:
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        if not allowed:
            report.error(f"unindexed schema file: {relative}")
            continue
        try:
            data, nodes = load_schema(path)
            validate_schema_structure(data, nodes)
            languages = schema_languages(nodes)
            expected = achievement_catalog.render_achievement_catalog(
                path.name,
                achievement_rows(nodes, languages),
                languages,
            )
        except (OSError, UnicodeError, EOFError, ValueError, NotImplementedError) as exc:
            report.error(f"invalid unindexed schema {relative}: {exc}")
            continue
        report.checked_files += 1
        _check_achievement_catalog(report, path, expected)


def check_repository(
    *,
    strict_language_coverage: bool = False,
    allow_unindexed_schema_files: bool = False,
    allow_stale_index_metadata: bool = False,
    allow_stale_derived_artifacts: bool = False,
) -> CheckReport:
    report = CheckReport()

    def derived_mismatch(message: str) -> None:
        if allow_stale_derived_artifacts:
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

    index = catalog_v2.legacy_index_from_catalog(catalog)
    index["entries"] = sort_entries(index["entries"])
    expected_v1 = catalog_v2.legacy_index_from_catalog(catalog, v1_compatibility_paths=True)
    expected_v1["entries"] = sort_entries(expected_v1["entries"])
    try:
        actual_v1 = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
        if actual_v1 != expected_v1:
            derived_mismatch("index.json is out of sync with index-v2.json")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.error(f"cannot read generated index.json: {exc}")

    expected_paths: set[Path] = set()
    for game_id, game in catalog["games"].items():
        report.checked_entries += 1
        compatibility = ROOT / Path(*PurePosixPath(catalog_v2.v1_schema_relative_path(game_id)).parts)
        expected_paths.add(compatibility.resolve())
        default_path = ROOT / Path(*PurePosixPath(catalog_v2.schema_relative_path(game_id, "default")).parts)
        if not compatibility.is_file():
            report.error(f"{game_id}: missing v1 compatibility schema")
        elif default_path.is_file() and compatibility.read_bytes() != default_path.read_bytes():
            report.error(f"{game_id}: v1 compatibility schema does not match default variant")
        for variant_id, variant in game["variants"].items():
            _check_schema(
                report,
                game_id,
                variant_id,
                variant,
                expected_paths,
                allow_stale_index_metadata=allow_stale_index_metadata,
                strict_language_coverage=strict_language_coverage,
            )

    actual_schemas = {path.resolve() for path in FILES_ROOT.rglob("*.bin") if path.is_file()}
    _check_unindexed_schemas(report, actual_schemas - expected_paths, allowed=allow_unindexed_schema_files)
    actual_catalogs = {path.resolve() for path in FILES_ROOT.rglob("achievements.md") if path.is_file()}
    expected_catalogs = {
        (ROOT / Path(*PurePosixPath(catalog_v2.achievement_catalog_relative_path(game_id, variant_id)).parts)).resolve()
        for game_id, game in catalog["games"].items()
        for variant_id in game["variants"]
    }
    if not allow_unindexed_schema_files:
        for path in sorted(actual_catalogs - expected_catalogs):
            report.error(f"orphan achievement catalog: {path.relative_to(ROOT).as_posix()}")

    try:
        expected_zh, expected_en = render_human_index(index)
        if HUMAN_INDEX_PATH.read_text(encoding="utf-8") != expected_zh:
            derived_mismatch("INDEX.md is out of sync with index-v2.json")
        if HUMAN_INDEX_EN_PATH.read_text(encoding="utf-8") != expected_en:
            derived_mismatch("INDEX_EN.md is out of sync with index-v2.json")
        if STATISTICS_PATH.read_text(encoding="utf-8") != render_svg(build_statistics(index)):
            derived_mismatch("library-statistics.svg is out of sync with index-v2.json")
    except (OSError, UnicodeError, TypeError, ValueError, AttributeError) as exc:
        report.error(f"cannot verify generated catalog projections: {exc}")
    return report
