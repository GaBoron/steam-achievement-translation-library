"""Read achievement text from either a real BIN or a standalone JSON."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import steam_schema
from standalone_translation import canonical_text, decode_translation, translation_rows, validate_translation


def load_artifact(path: Path) -> tuple[bytes, Any]:
    if path.suffix == ".json":
        payload = decode_translation(path.read_bytes())
        return canonical_text(payload).encode("utf-8"), payload
    return steam_schema.load_schema(path)


def artifact_rows(content: Any, languages: list[str]) -> list[dict[str, str]]:
    return translation_rows(content, languages) if isinstance(content, dict) else steam_schema.achievement_rows(content, languages)


def artifact_languages(content: Any) -> list[str]:
    return list(content["languages"]) if isinstance(content, dict) else steam_schema.schema_languages(content)


def validate_artifact(data: bytes, content: Any) -> list[dict[str, str]]:
    if isinstance(content, dict):
        validate_translation(content)
        return translation_rows(content, content["languages"])
    return steam_schema.validate_schema_structure(data, content)


def indexed_standalone(path: Path, app_id: str, variant_id: str, variant: dict[str, Any]) -> bytes:
    """Check canonical published bytes and all content metadata before use."""
    text = path.read_text(encoding="utf-8")
    data = text.encode("utf-8")
    payload = decode_translation(data, app_id=app_id, variant_id=variant_id)
    if text != canonical_text(payload):
        raise ValueError("Standalone JSON is not canonical UTF-8/LF JSON")
    expected = {"version": 2, "size": len(data), "sha256": steam_schema.sha256(data)}
    if variant.get("json") != expected or variant.get("languages") != payload["languages"] or variant.get("achievements") != len(payload["achievements"]):
        raise ValueError("Standalone JSON content does not match Catalog metadata")
    if path.with_suffix(".bin").exists():
        raise ValueError("JSON-only variant must not contain an unindexed BIN")
    return data


def validate_bin_upgrade(previous: Path, content: Any) -> None:
    """Do not lose accepted target text when adding a real schema to a variant."""
    payload = decode_translation(previous.read_bytes())
    rows = {row["api_name"]: row for row in artifact_rows(content, payload["target_languages"])}
    for api_name, achievement in payload["achievements"].items():
        for language in payload["target_languages"]:
            fields = achievement["translations"][language]
            if api_name not in rows or any(rows[api_name].get(f"{language}_{field}", "") != fields[field] for field in ("name", "description")):
                raise ValueError(f"BIN upgrade must preserve accepted {language} text for {api_name}")
