"""Internal entry adapters for submission forms and PR presentation."""
from __future__ import annotations

from typing import Any

import catalog_v2


def _variant_record(game_id: str, variant_id: str, variant: dict[str, Any]) -> dict[str, Any]:
    label = variant.get("label") if isinstance(variant.get("label"), dict) else {}
    record: dict[str, Any] = {
        "variant_id": variant_id,
        "primary": variant_id == "default",
        "schema_file": catalog_v2.artifact_relative_path(game_id, variant_id, variant),
        "note_zh": str(label.get("zh") or ""),
        "note_en": str(label.get("en") or ""),
        "file_size_bytes": (variant["json"] if variant.get("format") == "json" else variant)["size"],
        "sha256": (variant["json"] if variant.get("format") == "json" else variant)["sha256"],
        "achievement_count": variant["achievements"],
        "languages": list(variant["languages"]),
    }
    description = variant.get("description") if isinstance(variant.get("description"), dict) else {}
    if description:
        record["description_zh"] = str(description.get("zh") or "")
        record["description_en"] = str(description.get("en") or "")
    if "json" in variant:
        record["json"] = dict(variant["json"])
    return record


def entries_from_catalog(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    catalog_v2.validate_catalog(catalog)
    entries: list[dict[str, Any]] = []
    for game_id, game in catalog_v2.all_games(catalog).items():
        records = [
            _variant_record(game_id, variant_id, variant)
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
        if len(records) > 1 or primary["schema_file"].endswith(".json"):
            entry["schema_files"] = records
        if "json" in primary:
            entry["json"] = dict(primary["json"])
        entries.append(entry)
    return entries


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
        "json": entry.get("json"),
    }]


def catalog_from_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(entries, list) or not entries:
        raise ValueError("submission entries must be a non-empty array")
    games: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("submission entries contain a non-object entry")
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
            if isinstance(record.get("json"), dict):
                variant["json"] = dict(record["json"])
            if str(record.get("schema_file") or "").endswith(".json"):
                variant["format"] = "json"
                variant.pop("sha256")
                variant.pop("size")
            if len(_records(entry)) > 1 or label_zh or label_en:
                variant["label"] = {"zh": label_zh or variant_id, "en": label_en or variant_id}
            description_zh = str(record.get("description_zh") or "").strip()
            description_en = str(record.get("description_en") or "").strip()
            if description_zh or description_en:
                variant["description"] = {"zh": description_zh, "en": description_en}
            variants[variant_id] = variant
        contributors = sorted({str(value).strip() for value in entry.get("contributors", []) if str(value).strip()}, key=str.casefold)
        primary_contributor = str(entry.get("contributor_id") or "").strip()
        if primary_contributor and primary_contributor not in contributors:
            contributors = sorted([*contributors, primary_contributor], key=str.casefold)
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
    return catalog_v2.validate_catalog(catalog_v2.catalog_from_games(games))
