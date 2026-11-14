"""Fetch public Steam achievement identities without synthesizing a BIN."""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from standalone_translation import LANGUAGE_RE, canonical_text, unique_object, validate_translation


@dataclass(frozen=True)
class PublicAchievementDraft:
    translation: dict[str, Any]
    source_url: str
    retrieved_at: str
    source_language: str


class _SteamData(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.active = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("id") == "valve-ssr-data":
            self.active = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active:
            self.chunks.append(data)


def parse_public_page(html: str, app_id: str, language: str) -> dict[str, dict[str, str]]:
    parser = _SteamData()
    parser.feed(html)
    if not parser.chunks:
        raise ValueError("Steam public page contains no structured achievement data; original data is needed")
    root = json.loads("".join(parser.chunks), object_pairs_hook=unique_object)
    found: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if str(value.get("appid")) == app_id and value.get("language") == language and isinstance(value.get("groups"), list):
                found.append(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for loader in root.get("loaderData", []):
        visit(json.loads(loader, object_pairs_hook=unique_object) if isinstance(loader, str) else loader)
    query_data = root.get("renderContext", {}).get("queryData")
    if query_data is not None:
        visit(json.loads(query_data, object_pairs_hook=unique_object) if isinstance(query_data, str) else query_data)
    if len(found) != 1:
        raise ValueError("Steam public data is unavailable or has ambiguous app/language identity")
    rows: dict[str, dict[str, str]] = {}
    for group in found[0]["groups"]:
        if not isinstance(group, dict) or not isinstance(group.get("achievements"), list):
            raise ValueError("Incomplete public achievement group")
        for achievement in group["achievements"]:
            api_name = achievement.get("api_name") if isinstance(achievement, dict) else None
            if not isinstance(api_name, str) or not api_name.strip() or api_name in rows:
                raise ValueError("Public data contains missing or duplicate API names")
            name, description = achievement.get("name"), achievement.get("description")
            if not isinstance(name, str) or not name.strip() or not isinstance(description, str):
                raise ValueError(f"Public text is incomplete for {api_name}")
            rows[api_name] = {"name": name, "description": description}
    if not 1 <= len(rows) <= 10000:
        raise ValueError("Steam did not expose a usable achievement list")
    return rows


def generate_candidate(app_id: str, target_languages: list[str], *, language: str = "english") -> PublicAchievementDraft:
    if not re.fullmatch(r"[1-9][0-9]{0,9}", app_id) or int(app_id) > 4294967295:
        raise ValueError("Invalid Steam app ID")
    targets = sorted(set(target_languages))
    if not targets or any(not LANGUAGE_RE.fullmatch(value) for value in [language, *targets]) or language in targets:
        raise ValueError("Provide valid target languages distinct from the source language")
    url = f"https://steamcommunity.com/stats/{app_id}/achievements/?l={language}"
    request = urllib.request.Request(url, headers={"User-Agent": "steam-achievement-translation-library"})
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Steam public page exceeds 8 MiB")
    originals = parse_public_page(data.decode("utf-8"), app_id, language)
    languages = sorted({language, *targets})
    candidate = {
        "version": 2, "app_id": app_id, "variant_id": "default",
        "languages": languages,
        "achievements": {key: {"translations": {
            code: dict(fields) if code == language else {"name": "", "description": ""}
            for code in languages}} for key, fields in originals.items()},
    }
    return PublicAchievementDraft(
        validate_translation(candidate, allow_incomplete=True), url,
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"), language,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_id")
    parser.add_argument("--targets", required=True, help="Comma-separated Steam target languages")
    parser.add_argument("--language", default="english", help="Public source language")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        draft = generate_candidate(args.app_id, [value.strip() for value in args.targets.split(",")], language=args.language)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise SystemExit(f"Cannot generate a public achievement draft: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an existing contributor's translation.
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_text(draft.translation))
    print(f"Source ({draft.source_language}): {draft.source_url}")
    print(f"Retrieved: {draft.retrieved_at}")
    print(f"Wrote candidate with {len(draft.translation['achievements'])} publicly exposed achievements: {args.output}")


if __name__ == "__main__":
    main()
