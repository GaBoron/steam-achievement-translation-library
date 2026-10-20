"""Version 2 display-only translations, independent of a client BIN."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

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
                         allow_draft: bool = False) -> dict[str, Any]:
    required = {"version", "app_id", "variant_id", "languages", "target_languages", "source", "achievements"}
    if not isinstance(payload, dict) or set(payload) - required - {"draft"} or required - set(payload):
        raise ValueError("Standalone translation must contain the documented version 2 fields")
    if type(payload["version"]) is not int or payload["version"] != 2:
        raise ValueError("Standalone JSON requires format version 2; version 1 requires its source BIN")
    game_id, variant = payload["app_id"], payload["variant_id"]
    if not isinstance(game_id, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", game_id) or int(game_id) > 4294967295:
        raise ValueError("Invalid Steam app ID")
    if not isinstance(variant, str) or not VARIANT_RE.fullmatch(variant):
        raise ValueError("Invalid variant ID")
    if (app_id is not None and game_id != app_id) or (variant_id is not None and variant != variant_id):
        raise ValueError("Translation IDs do not match the requested app/variant")
    for field in ("languages", "target_languages"):
        values = payload[field]
        if (not isinstance(values, list) or not values or len(values) > 64
                or any(not isinstance(value, str) or not LANGUAGE_RE.fullmatch(value) for value in values)
                or values != sorted(set(values))):
            raise ValueError(f"{field} must be a nonempty, sorted, unique list of Steam language codes")
    if not set(payload["target_languages"]) <= set(payload["languages"]):
        raise ValueError("Target languages must be declared in languages")
    source = payload["source"]
    if not isinstance(source, dict) or set(source) != {"kind", "url", "retrieved_at", "language", "achievements"}:
        raise ValueError("source requires kind, url, retrieved_at, language and original achievements")
    if not isinstance(source["kind"], str) or source["kind"] not in {"steam-public", "contributor-json"}:
        raise ValueError("Unknown translation source kind")
    if not isinstance(source["url"], str) or len(source["url"]) > 2048:
        raise ValueError("source.url must be an HTTPS reference")
    url = urlsplit(source["url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("source.url must be an HTTPS reference without credentials or fragment")
    if source["kind"] == "steam-public" and (url.hostname != "steamcommunity.com"
            or url.path.rstrip("/") != f"/stats/{game_id}/achievements"):
        raise ValueError("Steam public source must reference this app's achievement page")
    try:
        timestamp = datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("missing timezone")
    except (TypeError, AttributeError, ValueError) as exc:
        raise ValueError("source.retrieved_at requires an ISO 8601 timestamp with timezone") from exc
    source_language = source["language"]
    if source_language not in payload["languages"] or source_language in payload["target_languages"]:
        raise ValueError("Source language must be declared and separate from target languages")
    achievements, originals = payload["achievements"], source["achievements"]
    if not isinstance(achievements, dict) or not 1 <= len(achievements) <= 10000:
        raise ValueError("Translation must contain 1 to 10000 achievements")
    if not isinstance(originals, dict) or set(originals) != set(achievements):
        raise ValueError("Original and translated API names must match exactly")
    for api_name, achievement in achievements.items():
        if not isinstance(api_name, str) or not api_name.strip() or len(api_name) > 512 or any(ord(c) < 32 for c in api_name):
            raise ValueError("Invalid achievement API name")
        _fields(originals[api_name], f"source.{api_name}")
        if not isinstance(achievement, dict) or set(achievement) != {"translations"}:
            raise ValueError(f"{api_name} must contain translations only")
        translations = achievement["translations"]
        if not isinstance(translations, dict) or set(translations) != set(payload["languages"]):
            raise ValueError(f"{api_name}: translation languages do not match languages")
        for language, fields in translations.items():
            _fields(fields, f"{api_name}.{language}")
        if translations[source_language] != originals[api_name]:
            raise ValueError(f"{api_name}: original language differs from the recorded source")
    if "draft" in payload and type(payload["draft"]) is not bool:
        raise ValueError("draft must be a boolean")
    if payload.get("draft") and not allow_draft:
        raise ValueError("Candidate is a draft; complete and review translations, then remove draft or set it false")
    if not (allow_draft and payload.get("draft")):
        require_language_coverage(translation_rows(payload, payload["languages"]), payload["languages"])
        for language in payload["target_languages"]:
            if all(value["translations"][language] == originals[key] for key, value in achievements.items()):
                raise ValueError(f"{language}: unchanged source text is not a completed translation")
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
