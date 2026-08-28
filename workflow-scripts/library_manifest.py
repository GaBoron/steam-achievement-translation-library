"""Authoritative per-game manifests and generated catalog projections."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = REPO_ROOT / "files"
LEGACY_INDEX_PATH = REPO_ROOT / "index.json"
RUNTIME_INDEX_PATH = REPO_ROOT / "index-v2.json"
MANIFEST_NAME = "manifest.json"
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GITHUB_ITEM_RE = re.compile(r"/(?:issues|pull)/(\d+)(?:[/?#]|$)")
GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/([^/]+/[^/]+)/(?:issues|pull)/(\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_VARIANTS = 16
REPOSITORY = "GaBoron/steam-achievement-translation-library"
DESCRIPTION = "Community-submitted Steam achievement schema translations."
STATES = {
    "current": {"label_zh": "可用", "label_en": "Current"},
    "possibly_ineffective": {"label_zh": "可能不生效", "label_en": "May not work"},
    "outdated": {"label_zh": "可能过期", "label_en": "Possibly outdated"},
}


def schema_relative_path(game_id: str, variant_id: str) -> str:
    return f"files/{game_id}/{variant_id}/UserGameStatsSchema_{game_id}.bin"


def v1_schema_relative_path(game_id: str, variant_id: str) -> str:
    if variant_id == "default":
        return f"files/{game_id}/UserGameStatsSchema_{game_id}.bin"
    return schema_relative_path(game_id, variant_id)


def manifest_relative_path(game_id: str) -> str:
    return f"files/{game_id}/{MANIFEST_NAME}"


def manifest_path(game_id: str, *, root: Path = REPO_ROOT) -> Path:
    return root / "files" / game_id / MANIFEST_NAME


def github_number(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    text = str(value or "").strip()
    if text.isdigit() and int(text) > 0:
        return int(text)
    match = GITHUB_ITEM_RE.search(text)
    return int(match.group(1)) if match else None


def github_repository(value: Any) -> str | None:
    match = GITHUB_URL_RE.match(str(value or "").strip())
    return match.group(1) if match else None


def github_url(kind: str, value: Any, *, repository: str | None = None) -> str:
    number = github_number(value)
    target_repository = repository or REPOSITORY
    return f"https://github.com/{target_repository}/{kind}/{number}" if number else ""


def _clean_string(value: Any, field: str, *, maximum: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty string")
    if maximum is not None and len(text) > maximum:
        raise ValueError(f"{field} must not exceed {maximum} characters")
    if any(ord(character) < 32 for character in text):
        raise ValueError(f"{field} must not contain control characters")
    return text


def _bilingual(value: Any, field: str, *, maximum: int) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must contain zh and en")
    return {
        "zh": _clean_string(value.get("zh"), f"{field}.zh", maximum=maximum),
        "en": _clean_string(value.get("en"), f"{field}.en", maximum=maximum),
    }


def validate_manifest(manifest: Any, *, expected_game_id: str | None = None) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    game_id = _clean_string(manifest.get("game_id"), "game_id")
    if not game_id.isdigit() or (expected_game_id is not None and game_id != expected_game_id):
        raise ValueError(f"manifest game_id does not match its directory: {game_id!r}")
    _clean_string(manifest.get("game_name"), f"{game_id}.game_name")
    status = str(manifest.get("status") or "current")
    if status not in STATES:
        raise ValueError(f"{game_id}.status is unknown: {status!r}")

    contributors = manifest.get("contributors")
    if not isinstance(contributors, list) or not contributors:
        raise ValueError(f"{game_id}.contributors must be a non-empty array")
    cleaned_contributors = [_clean_string(value, f"{game_id}.contributors") for value in contributors]
    if len(cleaned_contributors) != len(set(cleaned_contributors)):
        raise ValueError(f"{game_id}.contributors contains duplicates")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"{game_id}.source must be an object")
    repository = source.get("repository")
    if repository is not None and (
        not isinstance(repository, str) or not GITHUB_REPOSITORY_RE.fullmatch(repository)
    ):
        raise ValueError(f"{game_id}.source.repository must be an owner/repository name")
    for kind in ("issue", "pr"):
        value = source.get(kind)
        if value is not None and github_number(value) != value:
            raise ValueError(f"{game_id}.source.{kind} must be a positive integer")
    _clean_string(manifest.get("submitted_at"), f"{game_id}.submitted_at")
    _clean_string(manifest.get("updated_at"), f"{game_id}.updated_at")

    variants = manifest.get("variants")
    if not isinstance(variants, dict) or not 1 <= len(variants) <= MAX_VARIANTS:
        raise ValueError(f"{game_id}.variants must contain 1 to {MAX_VARIANTS} variants")
    if "default" not in variants:
        raise ValueError(f"{game_id}.variants must contain default")
    multiple = len(variants) > 1
    hashes: dict[str, str] = {}
    for variant_id, raw_variant in variants.items():
        if not isinstance(variant_id, str) or not VARIANT_ID_RE.fullmatch(variant_id):
            raise ValueError(f"{game_id} has an invalid variant ID: {variant_id!r}")
        if not isinstance(raw_variant, dict):
            raise ValueError(f"{game_id}/{variant_id} must be an object")
        if multiple or "label" in raw_variant:
            _bilingual(raw_variant.get("label"), f"{game_id}/{variant_id}.label", maximum=120)
        if "description" in raw_variant:
            _bilingual(raw_variant.get("description"), f"{game_id}/{variant_id}.description", maximum=1000)
        languages = raw_variant.get("languages")
        if not isinstance(languages, list) or not languages:
            raise ValueError(f"{game_id}/{variant_id}.languages must be a non-empty array")
        normalized_languages = [str(language) for language in languages]
        if normalized_languages != sorted(set(normalized_languages)):
            raise ValueError(f"{game_id}/{variant_id}.languages must be sorted and unique")
        if any(not LANGUAGE_RE.fullmatch(language) for language in normalized_languages):
            raise ValueError(f"{game_id}/{variant_id}.languages contains an invalid code")
        digest = str(raw_variant.get("sha256") or "")
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"{game_id}/{variant_id}.sha256 is invalid")
        duplicate = hashes.get(digest)
        if duplicate is not None:
            raise ValueError(f"{game_id} variants {duplicate} and {variant_id} have identical files")
        hashes[digest] = variant_id
        size = raw_variant.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_SCHEMA_BYTES:
            raise ValueError(f"{game_id}/{variant_id}.size is invalid")
        achievements = raw_variant.get("achievements")
        if not isinstance(achievements, int) or isinstance(achievements, bool) or achievements < 0:
            raise ValueError(f"{game_id}/{variant_id}.achievements is invalid")
    report = manifest.get("report")
    if report is not None and not isinstance(report, dict):
        raise ValueError(f"{game_id}.report must be an object")
    return manifest


def _variant_records(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("schema_files")
    if isinstance(raw, list) and raw:
        return [dict(value) for value in raw if isinstance(value, dict)]
    return [{
        "variant_id": "default",
        "primary": True,
        "schema_file": entry.get("schema_file"),
        "file_size_bytes": entry.get("file_size_bytes"),
        "sha256": entry.get("sha256"),
        "achievement_count": entry.get("achievement_count"),
    }]


def _manifest_report(report: Any) -> dict[str, Any] | None:
    if not isinstance(report, dict) or not report:
        return None
    result: dict[str, Any] = {}
    for key in ("type", "reported_at", "reason", "reference"):
        if key in report:
            result[key] = report.get(key)
    reporter = str(report.get("reporter") or report.get("reporter_id") or "").strip()
    if reporter:
        result["reporter"] = reporter
    source = {}
    issue = github_number(report.get("source_issue") or (report.get("source") or {}).get("issue"))
    pr = github_number(report.get("source_pr") or (report.get("source") or {}).get("pr"))
    repositories = {
        value
        for value in (
            github_repository(report.get("source_issue")),
            github_repository(report.get("source_pr")),
        )
        if value
    }
    if len(repositories) > 1:
        raise ValueError("report source Issue and PR must belong to the same repository")
    repository = next(iter(repositories), None)
    if repository and repository.casefold() != REPOSITORY.casefold():
        source["repository"] = repository
    if issue:
        source["issue"] = issue
    if pr:
        source["pr"] = pr
    if source:
        result["source"] = source
    return result or None


def manifest_from_legacy_entry(entry: dict[str, Any]) -> dict[str, Any]:
    game_id = str(entry.get("game_id") or "").strip()
    contributors = [str(value).strip() for value in entry.get("contributors", []) if str(value).strip()]
    legacy_contributor = str(entry.get("contributor_id") or "").strip()
    if legacy_contributor and legacy_contributor not in contributors:
        contributors.append(legacy_contributor)
    variants: dict[str, Any] = {}
    records = _variant_records(entry)
    for record in records:
        variant_id = str(record.get("variant_id") or ("default" if record.get("primary") else "")).lower()
        variant: dict[str, Any] = {}
        note_zh = str(record.get("note_zh") or "").strip().removeprefix("（").removesuffix("）")
        note_en = str(record.get("note_en") or "").strip().removeprefix("(").removesuffix(")")
        if note_zh or note_en or len(records) > 1:
            variant["label"] = {"zh": note_zh or variant_id, "en": note_en or variant_id}
        description_zh = str(record.get("description_zh") or "").strip()
        description_en = str(record.get("description_en") or "").strip()
        if description_zh or description_en:
            variant["description"] = {"zh": description_zh, "en": description_en}
        variant.update({
            "languages": sorted({
                str(value)
                for value in (record.get("languages") or entry.get("languages", []))
                if str(value)
            }),
            "sha256": str(record.get("sha256") or (entry.get("sha256") if variant_id == "default" else "")),
            "size": int(record.get("file_size_bytes") or (entry.get("file_size_bytes") if variant_id == "default" else 0)),
            "achievements": int(record.get("achievement_count") or (entry.get("achievement_count") if variant_id == "default" else 0)),
        })
        variants[variant_id] = variant
    source: dict[str, Any] = {}
    issue = github_number(entry.get("source_issue"))
    pr = github_number(entry.get("source_pr"))
    repositories = {
        value
        for value in (
            github_repository(entry.get("source_issue")),
            github_repository(entry.get("source_pr")),
        )
        if value
    }
    if len(repositories) > 1:
        raise ValueError(f"{game_id}: source Issue and PR must belong to the same repository")
    repository = next(iter(repositories), None)
    if repository and repository.casefold() != REPOSITORY.casefold():
        source["repository"] = repository
    if issue:
        source["issue"] = issue
    if pr:
        source["pr"] = pr
    manifest: dict[str, Any] = {
        "game_id": game_id,
        "game_name": str(entry.get("game_name") or "").strip(),
        "status": str(entry.get("status") or "current"),
        "contributors": sorted(set(contributors), key=str.casefold),
        "source": source,
        "submitted_at": str(entry.get("submitted_at") or entry.get("updated_at") or ""),
        "updated_at": str(entry.get("updated_at") or entry.get("submitted_at") or ""),
        "variants": variants,
    }
    report = _manifest_report(entry.get("report") or entry.get("outdated"))
    if report:
        manifest["report"] = report
    return validate_manifest(manifest, expected_game_id=game_id)


def _legacy_report(report: Any) -> dict[str, Any] | None:
    if not isinstance(report, dict) or not report:
        return None
    result = {key: value for key, value in report.items() if key != "source"}
    reporter = str(result.pop("reporter", "") or "")
    if reporter:
        result["reporter_id"] = reporter
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    repository = str(source.get("repository") or REPOSITORY)
    result["source_issue"] = github_url("issues", source.get("issue"), repository=repository)
    result["source_pr"] = github_url("pull", source.get("pr"), repository=repository) or None
    return result


def legacy_entry_from_manifest(
    manifest: dict[str, Any],
    *,
    v1_compatibility_paths: bool = False,
) -> dict[str, Any]:
    game_id = str(manifest["game_id"])
    variants = manifest["variants"]
    records: list[dict[str, Any]] = []
    for variant_id, variant in variants.items():
        label = variant.get("label") if isinstance(variant.get("label"), dict) else {}
        record = {
            "variant_id": variant_id,
            "primary": variant_id == "default",
            "schema_file": (
                v1_schema_relative_path(game_id, variant_id)
                if v1_compatibility_paths
                else schema_relative_path(game_id, variant_id)
            ),
            "note_zh": str(label.get("zh") or ""),
            "note_en": str(label.get("en") or ""),
            "file_size_bytes": variant["size"],
            "sha256": variant["sha256"],
            "achievement_count": variant["achievements"],
            "languages": list(variant["languages"]),
        }
        description = variant.get("description") if isinstance(variant.get("description"), dict) else {}
        if description:
            record["description_zh"] = str(description.get("zh") or "")
            record["description_en"] = str(description.get("en") or "")
        records.append(record)
    records.sort(key=lambda value: (value["variant_id"] != "default", value["variant_id"]))
    default = records[0]
    contributors = list(manifest["contributors"])
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    source_repository = str(source.get("repository") or REPOSITORY)
    entry: dict[str, Any] = {
        "game_name": manifest["game_name"],
        "game_id": game_id,
        "store_url": f"https://store.steampowered.com/app/{game_id}/",
        "languages": sorted({
            language
            for variant in variants.values()
            for language in variant["languages"]
        }),
        "schema_file": default["schema_file"],
        "file_size_bytes": default["file_size_bytes"],
        "sha256": default["sha256"],
            "achievement_count": default["achievement_count"],
        "contributor_id": contributors[0],
        "contributors": contributors,
        "source_issue": github_url("issues", source.get("issue"), repository=source_repository),
        "source_pr": github_url("pull", source.get("pr"), repository=source_repository) or None,
        "submitted_at": manifest["submitted_at"],
        "updated_at": manifest["updated_at"],
        "status": manifest.get("status") or "current",
    }
    if len(records) > 1:
        entry["schema_files"] = records
    report = _legacy_report(manifest.get("report"))
    if report:
        entry["report"] = report
    return entry


def legacy_index_from_manifests(
    manifests: Iterable[dict[str, Any]],
    *,
    v1_compatibility_paths: bool = False,
) -> dict[str, Any]:
    entries = [
        legacy_entry_from_manifest(
            manifest,
            v1_compatibility_paths=v1_compatibility_paths,
        )
        for manifest in manifests
    ]
    return {"version": 1, "description": DESCRIPTION, "states": STATES, "entries": entries}


def runtime_index_from_manifests(manifests: Iterable[dict[str, Any]]) -> dict[str, Any]:
    games: dict[str, Any] = {}
    for manifest in manifests:
        game: dict[str, Any] = {"name": manifest["game_name"]}
        if manifest.get("status") not in (None, "", "current"):
            game["status"] = manifest["status"]
        if manifest.get("contributors"):
            game["contributors"] = list(manifest["contributors"])
        variants: dict[str, Any] = {}
        for variant_id, manifest_variant in manifest["variants"].items():
            variant: dict[str, Any] = {"sha256": manifest_variant["sha256"]}
            if "label" in manifest_variant:
                variant["label"] = dict(manifest_variant["label"])
            variants[variant_id] = variant
        game["variants"] = variants
        games[str(manifest["game_id"])] = game
    return {"version": 2, "games": games}


def load_manifests(*, root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    files_root = root / "files"
    manifests: list[dict[str, Any]] = []
    for path in sorted(files_root.glob(f"*/{MANIFEST_NAME}"), key=lambda value: int(value.parent.name)):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read {path.relative_to(root).as_posix()}: {exc}") from exc
        manifests.append(validate_manifest(raw, expected_game_id=path.parent.name))
    return manifests


def has_manifests(*, root: Path = REPO_ROOT) -> bool:
    return any((root / "files").glob(f"*/{MANIFEST_NAME}"))


def _json_text(value: Any) -> str:
    lines = json.dumps(value, ensure_ascii=False, indent=2).splitlines()
    compacted: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.rstrip().endswith("["):
            end = index + 1
            scalars: list[str] = []
            while end < len(lines) and lines[end].strip() not in ("]", "],"):
                token = lines[end].strip().removesuffix(",")
                try:
                    parsed = json.loads(token)
                except json.JSONDecodeError:
                    break
                if isinstance(parsed, (dict, list)):
                    break
                scalars.append(token)
                end += 1
            if scalars and end < len(lines) and lines[end].strip() in ("]", "],"):
                suffix = "," if lines[end].strip() == "]," else ""
                compacted.append(f"{line.rstrip()} {', '.join(scalars)} ]{suffix}")
                index = end + 1
                continue
        compacted.append(line)
        index += 1
    return "\n".join(compacted) + "\n"


def _runtime_json_text(runtime: dict[str, Any]) -> str:
    games = runtime.get("games")
    if not isinstance(games, dict):
        raise ValueError("runtime catalog must contain a games object")
    lines = ["{", f'  "version": {int(runtime.get("version") or 0)},', '  "games": {']
    items = list(games.items())
    for position, (game_id, game) in enumerate(items):
        payload = json.dumps(game, ensure_ascii=False, separators=(",", ":"))
        suffix = "," if position + 1 < len(items) else ""
        lines.append(f"    {json.dumps(game_id)}: {payload}{suffix}")
    lines.extend(["  }", "}", ""])
    return "\n".join(lines)


def write_manifest(manifest: dict[str, Any], *, root: Path = REPO_ROOT) -> Path:
    game_id = str(manifest.get("game_id") or "")
    validate_manifest(manifest, expected_game_id=game_id)
    path = manifest_path(game_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(manifest), encoding="utf-8", newline="\n")
    return path


def write_manifests_from_legacy_index(index: dict[str, Any], *, root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise ValueError("legacy index must contain an entries array")
    manifests = [manifest_from_legacy_entry(entry) for entry in entries if isinstance(entry, dict)]
    retained_ids = {str(manifest["game_id"]) for manifest in manifests}
    for existing in (root / "files").glob(f"*/{MANIFEST_NAME}"):
        if existing.parent.name not in retained_ids:
            existing.unlink()
    for manifest in manifests:
        write_manifest(manifest, root=root)
    return manifests


def write_catalogs(manifests: Iterable[dict[str, Any]], *, root: Path = REPO_ROOT) -> tuple[Path, Path]:
    # Keep generated catalogs deterministic regardless of whether callers loaded
    # manifests from disk (App-ID order) or assembled them from an index
    # (usually game-name order).  This is the same canonical ordering used by
    # ``library_index.sort_entries`` without introducing a module cycle.
    manifest_list = sorted(
        manifests,
        key=lambda manifest: (
            str(manifest.get("game_name") or "").strip().casefold().encode("gb18030", errors="ignore"),
            str(manifest.get("game_name") or "").strip().casefold(),
            int(str(manifest.get("game_id") or "0")),
        ),
    )
    for manifest in manifest_list:
        game_id = str(manifest["game_id"])
        source = root / Path(*PurePosixPath(schema_relative_path(game_id, "default")).parts)
        destination = root / Path(*PurePosixPath(v1_schema_relative_path(game_id, "default")).parts)
        if not destination.is_file() or destination.read_bytes() != source.read_bytes():
            shutil.copyfile(source, destination)
    legacy_path = root / LEGACY_INDEX_PATH.name
    runtime_path = root / RUNTIME_INDEX_PATH.name
    legacy_path.write_text(
        _json_text(legacy_index_from_manifests(manifest_list, v1_compatibility_paths=True)),
        encoding="utf-8",
        newline="\n",
    )
    runtime_path.write_text(
        _runtime_json_text(runtime_index_from_manifests(manifest_list)),
        encoding="utf-8",
        newline="\n",
    )
    return legacy_path, runtime_path


def expected_schema_paths(manifest: dict[str, Any], *, root: Path = REPO_ROOT) -> dict[str, Path]:
    game_id = str(manifest["game_id"])
    return {
        variant_id: root / Path(*PurePosixPath(schema_relative_path(game_id, variant_id)).parts)
        for variant_id in manifest["variants"]
    }
