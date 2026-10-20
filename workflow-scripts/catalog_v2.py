"""Authoritative Catalog V2 validation, projection, and serialization."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = REPO_ROOT / "files"
CATALOG_PATH = REPO_ROOT / "index-v2.json"
VARIANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_VARIANTS = 16
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


def translation_json_relative_path(game_id: str, variant_id: str) -> str:
    return f"files/{game_id}/{variant_id}/UserGameStatsSchema_{game_id}.json"


def all_games(catalog: dict[str, Any]) -> dict[str, Any]:
    """Text-aware readers overlay complete games on the legacy BIN projection."""
    return {**catalog["games"], **catalog.get("text_games", {})}


def catalog_from_games(games: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(games, dict):
        raise ValueError("Catalog games must be an object")
    legacy, text = {}, {}
    for game_id, game in games.items():
        if not isinstance(game, dict) or not isinstance(game.get("variants"), dict):
            raise ValueError(f"{game_id}: game must contain a variants object")
        if any(not isinstance(variant, dict) for variant in game["variants"].values()):
            raise ValueError(f"{game_id}: variant must be an object")
        binary = {key: value for key, value in game["variants"].items() if value.get("format", "bin") == "bin"}
        if len(binary) == len(game["variants"]):
            legacy[game_id] = game
        else:
            text[game_id] = game
            if "default" in binary:
                legacy[game_id] = {**game, "variants": binary}
    result = {"version": 2, "games": legacy}
    if text:
        result["text_games"] = text
    return result


def artifact_relative_path(game_id: str, variant_id: str, variant: dict[str, Any]) -> str:
    return (translation_json_relative_path if variant.get("format") == "json" else schema_relative_path)(game_id, variant_id)


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
    if not isinstance(catalog.get("games"), dict) or not isinstance(catalog.get("text_games", {}), dict):
        raise ValueError("Catalog games and text_games must be objects")
    games = all_games(catalog)
    if not games:
        raise ValueError("Catalog must contain at least one game")
    for game_id, game in games.items():
        if not isinstance(game_id, str) or not game_id.isdigit() or not isinstance(game, dict):
            raise ValueError(f"invalid Catalog V2 game entry: {game_id!r}")
        removed_fields = FORBIDDEN_TRACKING_FIELDS & set(game)
        if removed_fields:
            raise ValueError(f"{game_id} contains removed tracking fields: {', '.join(sorted(removed_fields))}")
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
            format_name = variant.get("format", "bin")
            if not isinstance(format_name, str) or format_name not in {"bin", "json"}:
                raise ValueError(f"{game_id}/{variant_id}: unknown artifact format")
            standalone = format_name == "json"
            if standalone and ({"sha256", "size"} & set(variant)):
                raise ValueError(f"{game_id}/{variant_id}: JSON-only must not declare BIN hash or size")
            artifact = variant.get("json") if standalone else variant
            if not isinstance(artifact, dict):
                raise ValueError(f"{game_id}/{variant_id}: missing artifact metadata")
            digest = str(artifact.get("sha256") or "")
            if not SHA256_RE.fullmatch(digest):
                raise ValueError(f"{game_id}/{variant_id}.sha256 is invalid")
            if digest in hashes:
                raise ValueError(f"{game_id} variants {hashes[digest]} and {variant_id} have identical files")
            hashes[digest] = variant_id
            size = artifact.get("size")
            if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_SCHEMA_BYTES:
                raise ValueError(f"{game_id}/{variant_id}.size is invalid")
            count = variant.get("achievements")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError(f"{game_id}/{variant_id}.achievements is invalid")
            if "json" in variant:
                metadata = variant["json"]
                if not isinstance(metadata, dict) or type(metadata.get("version")) is not int or metadata["version"] != (2 if standalone else 1):
                    raise ValueError(f"{game_id}/{variant_id}.json has an incompatible format version")
                json_size = metadata.get("size")
                if not isinstance(json_size, int) or isinstance(json_size, bool) or not 0 < json_size <= MAX_SCHEMA_BYTES:
                    raise ValueError(f"{game_id}/{variant_id}.json.size is invalid")
    if catalog_from_games(games) != catalog:
        raise ValueError("Catalog games must be the BIN-compatible projection; text_games contains complete mixed/JSON games")
    return catalog


def load_catalog(*, root: Path = REPO_ROOT) -> dict[str, Any]:
    path = root / CATALOG_PATH.name
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    return validate_catalog(catalog)


def canonical_catalog_text(catalog: dict[str, Any]) -> str:
    """Serialize Catalog V2 with one compact line per game entry."""
    lines = ["{", '  "version": 2,']
    groups = ["games"] + (["text_games"] if catalog.get("text_games") else [])
    for group_index, group in enumerate(groups):
        lines.append(f'  "{group}": {{')
        items = list(catalog[group].items())
        for position, (game_id, game) in enumerate(items):
            suffix = "," if position + 1 < len(items) else ""
            lines.append(f"    {json.dumps(game_id)}: {json.dumps(game, ensure_ascii=False, separators=(',', ':'))}{suffix}")
        lines.append("  }" + ("," if group_index + 1 < len(groups) else ""))
    lines.extend(["}", ""])
    return "\n".join(lines)


def _game_sort_key(game_id: str, game: dict[str, Any]) -> tuple[bytes, str, int]:
    name = str(game.get("name") or "").strip().casefold()
    return name.encode("gb18030", errors="ignore"), name, int(game_id)


def write_catalog(catalog: dict[str, Any], *, root: Path = REPO_ROOT) -> Path:
    validate_catalog(catalog)
    for group in ("games", "text_games"):
        if group in catalog:
            catalog[group] = dict(sorted(catalog[group].items(), key=lambda item: _game_sort_key(*item)))
    path = root / CATALOG_PATH.name
    path.write_text(canonical_catalog_text(catalog), encoding="utf-8", newline="\n")
    return path
