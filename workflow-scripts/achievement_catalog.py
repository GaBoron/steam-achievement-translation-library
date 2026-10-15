"""Generate temporary achievement Markdown for translation PR review."""
from __future__ import annotations

import argparse
from pathlib import Path
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


def write_review_catalogs(game_id: str, *, output: Path, root: Path = catalog_v2.REPO_ROOT) -> list[Path]:
    from pr_submission_data import load_submission_catalog

    root = root.resolve()
    output = output.resolve()
    if output == root or output in root.parents or output.is_relative_to(root):
        raise ValueError("Review artifacts must be generated outside the repository.")
    if output.exists() and (not output.is_dir() or next(output.iterdir(), None) is not None):
        raise ValueError(f"Review output must be empty: {output}")
    catalog = load_submission_catalog(root=root)
    game = catalog["games"][game_id]
    written = []
    for variant_id, variant in game["variants"].items():
        schema_path = root / catalog_v2.schema_relative_path(game_id, variant_id)
        data, nodes = load_schema(schema_path)
        validate_schema_structure(data, nodes)
        languages = variant["languages"]
        content = render_achievement_catalog(schema_path.name, achievement_rows(nodes, languages), languages)
        path = output / game_id / variant_id / "achievements.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main() -> None:
    from translation_pr_validation import changed_game

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    game_id, _ = changed_game(args.base_ref, args.head_ref)
    written = write_review_catalogs(game_id, output=args.output)
    print(f"Generated {len(written)} review catalog(s) for {game_id}.")


if __name__ == "__main__":
    main()
