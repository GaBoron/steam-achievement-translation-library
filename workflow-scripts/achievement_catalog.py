"""Generate human-readable achievement catalogs from Binary KeyValues schemas."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import catalog_v2
from steam_schema import achievement_rows, load_schema, validate_schema_structure


LANGUAGE_TITLES = {
    "arabic": "العربية",
    "brazilian": "Português do Brasil",
    "bulgarian": "Български",
    "czech": "Čeština",
    "danish": "Dansk",
    "dutch": "Nederlands",
    "english": "English",
    "finnish": "Suomi",
    "french": "Français",
    "german": "Deutsch",
    "greek": "Ελληνικά",
    "hungarian": "Magyar",
    "indonesian": "Bahasa Indonesia",
    "italian": "Italiano",
    "japanese": "日本語",
    "koreana": "한국어",
    "latam": "Español (Latinoamérica)",
    "norwegian": "Norsk",
    "polish": "Polski",
    "portuguese": "Português",
    "romanian": "Română",
    "russian": "Русский",
    "schinese": "简体中文",
    "spanish": "Español",
    "swedish": "Svenska",
    "tchinese": "繁體中文",
    "thai": "ไทย",
    "turkish": "Türkçe",
    "ukrainian": "Українська",
    "vietnamese": "Tiếng Việt",
}


def escape_cell(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", "<br>").strip()


def render_achievement_catalog(schema_name: str, rows: list[dict[str, str]], languages: list[str]) -> str:
    lines = [
        "# Achievement Catalog",
        "",
        f"Generated from `{schema_name}`. Do not edit manually.",
    ]
    for language in languages:
        lines.extend([
            "",
            f"## {LANGUAGE_TITLES.get(language, language)} (`{language}`)",
            "",
            "| ID | Name | Description |",
            "| --- | --- | --- |",
        ])
        for row in rows:
            lines.append(
                f"| `{escape_cell(row.get('api_name'))}` | {escape_cell(row.get(f'{language}_name'))} | "
                f"{escape_cell(row.get(f'{language}_description'))} |"
            )
    return "\n".join(lines) + "\n"


def expected_catalog(game_id: str, variant_id: str, variant: dict[str, Any], *, root: Path) -> tuple[Path, str]:
    schema_relative = catalog_v2.schema_relative_path(game_id, variant_id)
    schema_path = root / Path(*PurePosixPath(schema_relative).parts)
    data, nodes = load_schema(schema_path)
    validate_schema_structure(data, nodes)
    languages = [str(value) for value in variant["languages"]]
    rows = achievement_rows(nodes, languages)
    output = root / Path(*PurePosixPath(catalog_v2.achievement_catalog_relative_path(game_id, variant_id)).parts)
    return output, render_achievement_catalog(schema_path.name, rows, languages)


def write_achievement_catalogs(catalog: dict[str, Any], *, root: Path = catalog_v2.REPO_ROOT) -> list[Path]:
    written: list[Path] = []
    for game_id, game in catalog["games"].items():
        for variant_id, variant in game["variants"].items():
            path, content = expected_catalog(game_id, variant_id, variant, root=root)
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)
    return written


def write_entry_achievement_catalogs(entry: dict[str, Any], *, root: Path = catalog_v2.REPO_ROOT) -> list[Path]:
    """Generate catalogs for an in-flight legacy-shaped PR entry."""
    from library_index import validated_entry_schema_variants

    game_id = str(entry["game_id"])
    written: list[Path] = []
    for variant in validated_entry_schema_variants(entry, require_metadata=True):
        variant_id = str(variant["variant_id"])
        path, content = expected_catalog(game_id, variant_id, variant, root=root)
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written
