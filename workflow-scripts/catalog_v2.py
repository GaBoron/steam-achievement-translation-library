"""Authoritative Catalog V2 validation, projection, and serialization."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = REPO_ROOT / "files"
CATALOG_PATH = REPO_ROOT / "index-v2.json"
LEGACY_INDEX_PATH = REPO_ROOT / "index.json"
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_VARIANTS = 16
DESCRIPTION = "Community-submitted Steam achievement schema translations."
STATES = {
    "current": {"label_zh": "可用", "label_en": "Current"},
    "possibly_ineffective": {"label_zh": "可能不生效", "label_en": "May not work"},
    "outdated": {"label_zh": "可能过期", "label_en": "Possibly outdated"},
}
FORBIDDEN_TRACKING_FIELDS = {
    "source",
    "source_issue",
    "source_pr",
    "report",
    "outdated",
}


def schema_relative_path(game_id: str, variant_id: str) -> str:
    return f"files/{game_id}/{variant_id}/UserGameStatsSchema_{game_id}.bin"


def v1_schema_relative_path(game_id: str) -> str:
    return f"files/{game_id}/UserGameStatsSchema_{game_id}.bin"


def achievement_catalog_relative_path(game_id: str, variant_id: str) -> str:
    return f"files/{game_id}/{variant_id}/achievements.md"


def _text(value: Any, field: str, *, maximum: int | None = None) -> str:
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
        "zh": _text(value.get("zh"), f"{field}.zh", maximum=maximum),
        "en": _text(value.get("en"), f"{field}.en", maximum=maximum),
    }


def validate_catalog(catalog: Any) -> dict[str, Any]:
    if not isinstance(catalog, dict) or catalog.get("version") != 2:
        raise ValueError("index-v2.json must be a version 2 object")
    games = catalog.get("games")
    if not isinstance(games, dict) or not games:
        raise ValueError("index-v2.json games must be a non-empty object")
    for game_id, game in games.items():
        if not isinstance(game_id, str) or not game_id.isdigit() or not isinstance(game, dict):
            raise ValueError(f"invalid Catalog V2 game entry: {game_id!r}")
        legacy_fields = FORBIDDEN_TRACKING_FIELDS & set(game)
        if legacy_fields:
            raise ValueError(f"{game_id} contains removed tracking fields: {', '.join(sorted(legacy_fields))}")
        _text(game.get("name"), f"{game_id}.name")
        status = str(game.get("status") or "current")
        if status not in STATES:
            raise ValueError(f"{game_id}.status is unknown: {status!r}")
        contributors = game.get("contributors")
        if not isinstance(contributors, list) or not contributors:
            raise ValueError(f"{game_id}.contributors must be a non-empty array")
        cleaned = [_text(value, f"{game_id}.contributors") for value in contributors]
        if cleaned != sorted(set(cleaned), key=str.casefold):
            raise ValueError(f"{game_id}.contributors must be sorted and unique")
        _text(game.get("submitted_at"), f"{game_id}.submitted_at")
        _text(game.get("updated_at"), f"{game_id}.updated_at")
        variants = game.get("variants")
        if not isinstance(variants, dict) or not 1 <= len(variants) <= MAX_VARIANTS:
            raise ValueError(f"{game_id}.variants must contain 1 to {MAX_VARIANTS} variants")
        if "default" not in variants:
            raise ValueError(f"{game_id}.variants must contain default")
        hashes: dict[str, str] = {}
        for variant_id, variant in variants.items():
            if not isinstance(variant_id, str) or not VARIANT_ID_RE.fullmatch(variant_id):
                raise ValueError(f"{game_id} has an invalid variant ID: {variant_id!r}")
            if not isinstance(variant, dict):
                raise ValueError(f"{game_id}/{variant_id} must be an object")
            if len(variants) > 1 or "label" in variant:
                _bilingual(variant.get("label"), f"{game_id}/{variant_id}.label", maximum=120)
            if "description" in variant:
                _bilingual(variant.get("description"), f"{game_id}/{variant_id}.description", maximum=1000)
            languages = variant.get("languages")
            if not isinstance(languages, list) or not languages:
                raise ValueError(f"{game_id}/{variant_id}.languages must be a non-empty array")
            normalized = [str(language) for language in languages]
            if normalized != sorted(set(normalized)) or any(not LANGUAGE_RE.fullmatch(value) for value in normalized):
                raise ValueError(f"{game_id}/{variant_id}.languages must be valid, sorted, and unique")
            digest = str(variant.get("sha256") or "")
            if not SHA256_RE.fullmatch(digest):
                raise ValueError(f"{game_id}/{variant_id}.sha256 is invalid")
            if digest in hashes:
                raise ValueError(f"{game_id} variants {hashes[digest]} and {variant_id} have identical files")
            hashes[digest] = variant_id
            size = variant.get("size")
            if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_SCHEMA_BYTES:
                raise ValueError(f"{game_id}/{variant_id}.size is invalid")
            count = variant.get("achievements")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError(f"{game_id}/{variant_id}.achievements is invalid")
    return catalog


def load_catalog(*, root: Path = REPO_ROOT) -> dict[str, Any]:
    path = root / CATALOG_PATH.name
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    return validate_catalog(catalog)


def _variant_record(game_id: str, variant_id: str, variant: dict[str, Any], *, v1: bool) -> dict[str, Any]:
    label = variant.get("label") if isinstance(variant.get("label"), dict) else {}
    record: dict[str, Any] = {
        "variant_id": variant_id,
        "primary": variant_id == "default",
        "schema_file": v1_schema_relative_path(game_id) if v1 and variant_id == "default" else schema_relative_path(game_id, variant_id),
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
    return record


def legacy_index_from_catalog(catalog: dict[str, Any], *, v1_compatibility_paths: bool = False) -> dict[str, Any]:
    validate_catalog(catalog)
    entries: list[dict[str, Any]] = []
    for game_id, game in catalog["games"].items():
        records = [
            _variant_record(game_id, variant_id, variant, v1=v1_compatibility_paths)
            for variant_id, variant in game["variants"].items()
        ]
        records.sort(key=lambda value: (value["variant_id"] != "default", value["variant_id"]))
        primary = records[0]
        entry: dict[str, Any] = {
            "game_name": game["name"],
            "game_id": game_id,
            "store_url": f"https://store.steampowered.com/app/{game_id}/",
            "languages": sorted({language for variant in game["variants"].values() for language in variant["languages"]}),
            "schema_file": primary["schema_file"],
            "file_size_bytes": primary["file_size_bytes"],
            "sha256": primary["sha256"],
            "achievement_count": primary["achievement_count"],
            "contributor_id": game["contributors"][0],
            "contributors": list(game["contributors"]),
            "submitted_at": game["submitted_at"],
            "updated_at": game["updated_at"],
            "status": game.get("status") or "current",
        }
        if len(records) > 1:
            entry["schema_files"] = records
        entries.append(entry)
    return {"version": 1, "description": DESCRIPTION, "states": STATES, "entries": entries}


def _records(entry: dict[str, Any]) -> list[dict[str, Any]]:
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
        "languages": entry.get("languages"),
    }]


def catalog_from_legacy_index(index: dict[str, Any]) -> dict[str, Any]:
    entries = index.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("legacy index must contain a non-empty entries array")
    games: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("legacy index contains a non-object entry")
        game_id = str(entry.get("game_id") or "")
        variants: dict[str, Any] = {}
        for record in _records(entry):
            variant_id = str(record.get("variant_id") or ("default" if record.get("primary") else ""))
            label_zh = str(record.get("note_zh") or "").strip().removeprefix("（").removesuffix("）")
            label_en = str(record.get("note_en") or "").strip().removeprefix("(").removesuffix(")")
            variant: dict[str, Any] = {
                "sha256": str(record.get("sha256") or (entry.get("sha256") if variant_id == "default" else "")),
                "languages": sorted({str(value) for value in (record.get("languages") or entry.get("languages", [])) if str(value)}),
                "achievements": int(record.get("achievement_count") or (entry.get("achievement_count") if variant_id == "default" else 0)),
                "size": int(record.get("file_size_bytes") or (entry.get("file_size_bytes") if variant_id == "default" else 0)),
            }
            if len(_records(entry)) > 1 or label_zh or label_en:
                variant["label"] = {"zh": label_zh or variant_id, "en": label_en or variant_id}
            description_zh = str(record.get("description_zh") or "").strip()
            description_en = str(record.get("description_en") or "").strip()
            if description_zh or description_en:
                variant["description"] = {"zh": description_zh, "en": description_en}
            variants[variant_id] = variant
        contributors = sorted({str(value).strip() for value in entry.get("contributors", []) if str(value).strip()}, key=str.casefold)
        legacy_contributor = str(entry.get("contributor_id") or "").strip()
        if legacy_contributor and legacy_contributor not in contributors:
            contributors = sorted([*contributors, legacy_contributor], key=str.casefold)
        games[game_id] = {
            "name": str(entry.get("game_name") or "").strip(),
            "submitted_at": str(entry.get("submitted_at") or entry.get("updated_at") or ""),
            "updated_at": str(entry.get("updated_at") or entry.get("submitted_at") or ""),
            "contributors": contributors,
            "variants": variants,
        }
        status = str(entry.get("status") or "current")
        if status != "current":
            games[game_id]["status"] = status
    return validate_catalog({"version": 2, "games": games})


def catalog_from_manifests(manifests: Iterable[dict[str, Any]]) -> dict[str, Any]:
    games: dict[str, Any] = {}
    for manifest in manifests:
        game_id = str(manifest["game_id"])
        game: dict[str, Any] = {
            "name": manifest["game_name"],
            "submitted_at": manifest["submitted_at"],
            "updated_at": manifest["updated_at"],
            "contributors": sorted(set(manifest["contributors"]), key=str.casefold),
            "variants": {},
        }
        if manifest.get("status") not in (None, "", "current"):
            game["status"] = manifest["status"]
        for variant_id, raw in manifest["variants"].items():
            variant = {
                key: raw[key]
                for key in ("sha256", "languages", "achievements", "size", "label", "description")
                if key in raw
            }
            game["variants"][variant_id] = variant
        games[game_id] = game
    return validate_catalog({"version": 2, "games": games})


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def canonical_catalog_text(catalog: dict[str, Any]) -> str:
    """Serialize Catalog V2 with one compact line per game entry."""
    lines = ["{", '  "version": 2,', '  "games": {']
    items = list(catalog["games"].items())
    for position, (game_id, game) in enumerate(items):
        suffix = "," if position + 1 < len(items) else ""
        lines.append(f"    {json.dumps(game_id)}: {json.dumps(game, ensure_ascii=False, separators=(',', ':'))}{suffix}")
    lines.extend(["  }", "}", ""])
    return "\n".join(lines)


def _game_sort_key(game_id: str, game: dict[str, Any]) -> tuple[bytes, str, int]:
    name = str(game.get("name") or "").strip().casefold()
    return name.encode("gb18030", errors="ignore"), name, int(game_id)


def write_catalog(catalog: dict[str, Any], *, root: Path = REPO_ROOT) -> Path:
    validate_catalog(catalog)
    catalog["games"] = dict(sorted(catalog["games"].items(), key=lambda item: _game_sort_key(*item)))
    path = root / CATALOG_PATH.name
    path.write_text(canonical_catalog_text(catalog), encoding="utf-8", newline="\n")
    return path


def write_legacy_index(catalog: dict[str, Any], *, root: Path = REPO_ROOT) -> Path:
    for game_id in catalog["games"]:
        source = root / Path(*PurePosixPath(schema_relative_path(game_id, "default")).parts)
        destination = root / Path(*PurePosixPath(v1_schema_relative_path(game_id)).parts)
        if not destination.is_file() or destination.read_bytes() != source.read_bytes():
            shutil.copyfile(source, destination)
    index = legacy_index_from_catalog(catalog, v1_compatibility_paths=True)
    index["entries"].sort(key=lambda entry: _game_sort_key(str(entry["game_id"]), {"name": entry["game_name"]}))
    path = root / LEGACY_INDEX_PATH.name
    path.write_text(
        _json_text(index),
        encoding="utf-8",
        newline="\n",
    )
    return path
