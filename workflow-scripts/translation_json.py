"""Deterministic, BIN-derived JSON for clients that only replace achievement text."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import catalog_v2
from steam_schema import achievement_rows, load_schema, schema_languages, sha256, validate_schema_structure


FORMAT_VERSION = 1
MAX_JSON_BYTES = 32 * 1024 * 1024


def render_translation(game_id: str, variant_id: str, data: bytes, nodes: list) -> str:
    validate_schema_structure(data, nodes)
    languages = schema_languages(nodes)
    achievements = {
        row["api_name"]: {
            "translations": {
                language: {
                    "name": row[f"{language}_name"],
                    "description": row[f"{language}_description"],
                }
                for language in languages
            }
        }
        for row in achievement_rows(nodes, languages)
    }
    payload = {
        "version": FORMAT_VERSION,
        "app_id": game_id,
        "variant_id": variant_id,
        "source_sha256": sha256(data),
        "languages": languages,
        "achievements": achievements,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError(f"{game_id}/{variant_id}: JSON exceeds the 32 MiB limit")
    return text


def expected_translation(path: Path, game_id: str, variant_id: str) -> tuple[Path, str]:
    data, nodes = load_schema(path)
    return path.with_suffix(".json"), render_translation(game_id, variant_id, data, nodes)


def write_translation(path: Path, game_id: str, variant_id: str) -> dict[str, int]:
    output, text = expected_translation(path, game_id, variant_id)
    if not output.is_file() or output.read_text(encoding="utf-8") != text:
        output.write_text(text, encoding="utf-8", newline="\n")
    return {"version": FORMAT_VERSION, "size": len(text.encode("utf-8"))}


def check_translation(path: Path, expected: str) -> str | None:
    output = path.with_suffix(".json")
    if not output.is_file():
        return f"missing translation JSON: {output.name}"
    try:
        if output.read_text(encoding="utf-8") != expected:
            return f"translation JSON is out of sync: {output.name}"
    except (OSError, UnicodeError) as exc:
        return f"cannot read translation JSON {output.name}: {exc}"
    return None


def write_entry_translation_json(entry: dict[str, Any], *, root: Path = catalog_v2.REPO_ROOT) -> list[Path]:
    """Generate translation JSON and attach its metadata to a submission entry."""
    from library_index import validated_entry_schema_variants

    game_id = str(entry["game_id"])
    written: list[Path] = []
    variants = validated_entry_schema_variants(entry, require_metadata=True)
    for variant in variants:
        variant_id = str(variant["variant_id"])
        schema_path = root / str(variant["schema_file"])
        if schema_path.suffix == ".json":
            from standalone_translation import canonical_text, decode_translation
            payload = decode_translation(schema_path.read_bytes(), app_id=game_id, variant_id=variant_id)
            text = canonical_text(payload)
            schema_path.write_text(text, encoding="utf-8", newline="\n")
            variant["json"] = {"version": 2, "size": len(text.encode("utf-8")), "sha256": sha256(text.encode("utf-8"))}
        else:
            variant["json"] = write_translation(schema_path, game_id, variant_id)
        written.append(schema_path.with_suffix(".json"))
        if variant_id == "default":
            entry["json"] = dict(variant["json"])
    if isinstance(entry.get("schema_files"), list):
        entry["schema_files"] = variants
    return written
