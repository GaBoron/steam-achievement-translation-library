"""Version 2 display-only translations, independent of a client BIN."""
from __future__ import annotations

import json
import re
from typing import Any

from steam_schema import require_language_coverage


MAX_BYTES = 32 * 1024 * 1024
LANGUAGE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
VARIANT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def translation_rows(payload: dict[str, Any], languages: list[str]) -> list[dict[str, str]]:
    rows = []
    for index, (api_name, achievement) in enumerate(payload["achievements"].items(), 1):
        row = {"index": str(index), "api_name": api_name, "node_key": api_name}
        for language in sorted(set(languages) | {"english"}):
            fields = achievement["translations"].get(language, {})
            for field in ("name", "description"):
                row[f"{language}_{field}"] = fields.get(field, "")
        rows.append(row)
    return rows


def _fields(value: Any, location: str) -> None:
    if not isinstance(value, dict) or set(value) != {"name", "description"}:
        raise ValueError(f"{location} must contain name and description only")
    for field, text in value.items():
        if not isinstance(text, str) or "\x00" in text or len(text) > 65536:
            raise ValueError(f"{location}.{field} must be text without NUL (at most 65536 characters)")


def validate_translation(payload: Any, *, app_id: str | None = None, variant_id: str | None = None,
                         allow_incomplete: bool = False) -> dict[str, Any]:
    required = {"version", "app_id", "variant_id", "languages", "achievements"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("Standalone translation requires version, app_id, variant_id, languages and achievements only")
    if type(payload["version"]) is not int or payload["version"] != 2:
        raise ValueError("Standalone JSON requires format version 2; version 1 requires its source BIN")
    game_id, variant = payload["app_id"], payload["variant_id"]
    if not isinstance(game_id, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", game_id) or int(game_id) > 4294967295:
        raise ValueError("Invalid Steam app ID")
    if not isinstance(variant, str) or not VARIANT_RE.fullmatch(variant):
        raise ValueError("Invalid variant ID")
    if (app_id is not None and game_id != app_id) or (variant_id is not None and variant != variant_id):
        raise ValueError("Translation IDs do not match the requested app/variant")
    languages = payload["languages"]
    if (not isinstance(languages, list) or not languages or len(languages) > 64
            or any(not isinstance(value, str) or not LANGUAGE_RE.fullmatch(value) for value in languages)
            or languages != sorted(set(languages))):
        raise ValueError("languages must be a nonempty, sorted, unique list of Steam language codes")
    achievements = payload["achievements"]
    if not isinstance(achievements, dict) or not 1 <= len(achievements) <= 10000:
        raise ValueError("Translation must contain 1 to 10000 achievements")
    for api_name, achievement in achievements.items():
        if not isinstance(api_name, str) or not api_name.strip() or len(api_name) > 512 or any(ord(c) < 32 for c in api_name):
            raise ValueError("Invalid achievement API name")
        if not isinstance(achievement, dict) or set(achievement) != {"translations"}:
            raise ValueError(f"{api_name} must contain translations only")
        translations = achievement["translations"]
        if not isinstance(translations, dict) or set(translations) != set(languages):
            raise ValueError(f"{api_name}: translation languages do not match languages")
        for language, fields in translations.items():
            _fields(fields, f"{api_name}.{language}")
    if not allow_incomplete:
        require_language_coverage(translation_rows(payload, languages), languages)
    if len(canonical_text(payload).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Translation exceeds 32 MiB")
    return payload


def decode_translation(data: bytes, **kwargs: Any) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise ValueError("Translation exceeds 32 MiB")
    try:
        payload = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"Invalid UTF-8 JSON: {exc}") from exc
    return validate_translation(payload, **kwargs)
