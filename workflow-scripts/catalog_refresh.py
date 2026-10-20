#!/usr/bin/env python3
"""Refresh every Catalog V2 derivative in one deterministic operation."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import catalog_v2
import translation_json
from generate_statistics_svg import build_statistics, render_svg, write_if_changed
from pr_submission_data import with_submissions
from steam_schema import load_schema, schema_languages, sha256, validate_schema_structure
from standalone_translation import canonical_text, decode_translation


ROOT = Path(__file__).resolve().parent.parent
STATISTICS_PATH = ROOT / "docs" / "statistics" / "library-statistics.svg"


def refresh_catalog(catalog: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    """Recalculate artifact metadata, then refresh every checked-in projection."""
    catalog = with_submissions(catalog, root=root)
    games = catalog_v2.all_games(catalog)
    for game_id, game in games.items():
        for variant_id, variant in game["variants"].items():
            if variant.get("format") == "json":
                path = root / catalog_v2.translation_json_relative_path(game_id, variant_id)
                payload = decode_translation(path.read_bytes(), app_id=game_id, variant_id=variant_id)
                content = canonical_text(payload)
                path.write_text(content, encoding="utf-8", newline="\n")
                variant["json"] = {"version": 2, "size": len(content.encode("utf-8")), "sha256": sha256(content.encode("utf-8"))}
                variant["languages"] = payload["languages"]
                variant["achievements"] = len(payload["achievements"])
                continue
            relative = catalog_v2.schema_relative_path(game_id, variant_id)
            path = root / Path(*PurePosixPath(relative).parts)
            data, nodes = load_schema(path)
            rows = validate_schema_structure(data, nodes)
            variant["sha256"] = sha256(data)
            variant["size"] = len(data)
            variant["languages"] = schema_languages(nodes)
            variant["achievements"] = len(rows)
            variant["json"] = translation_json.write_translation(path, game_id, variant_id)
    catalog = catalog_v2.catalog_from_games(games)
    catalog_v2.validate_catalog(catalog)
    catalog_v2.write_catalog(catalog, root=root)

    statistics = build_statistics(catalog)
    write_if_changed(root / STATISTICS_PATH.relative_to(ROOT), render_svg(statistics))
    return catalog


def main() -> None:
    catalog = catalog_v2.load_catalog(root=ROOT)
    refresh_catalog(catalog, root=ROOT)
    print(
        "Refreshed index-v2.json, "
        "translation JSON sidecars, and statistics SVG."
    )


if __name__ == "__main__":
    main()
