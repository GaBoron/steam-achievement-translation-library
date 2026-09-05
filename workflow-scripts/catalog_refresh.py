#!/usr/bin/env python3
"""Refresh every Catalog V2 derivative in one deterministic operation."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import achievement_catalog
import catalog_v2
from generate_statistics_svg import build_statistics, render_svg, write_if_changed
from library_index import render_human_index, sort_entries
from steam_schema import achievement_rows, load_schema, schema_languages, sha256, validate_schema_structure


ROOT = Path(__file__).resolve().parent.parent
HUMAN_INDEX_PATH = ROOT / "INDEX.md"
HUMAN_INDEX_EN_PATH = ROOT / "INDEX_EN.md"
STATISTICS_PATH = ROOT / "docs" / "statistics" / "library-statistics.svg"


def refresh_catalog(catalog: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    """Recalculate BIN-derived fields, then refresh every checked-in projection."""
    for game_id, game in catalog["games"].items():
        for variant_id, variant in game["variants"].items():
            relative = catalog_v2.schema_relative_path(game_id, variant_id)
            path = root / Path(*PurePosixPath(relative).parts)
            data, nodes = load_schema(path)
            rows = validate_schema_structure(data, nodes)
            variant["sha256"] = sha256(data)
            variant["size"] = len(data)
            variant["languages"] = schema_languages(nodes)
            variant["achievements"] = len(rows)
    catalog_v2.validate_catalog(catalog)
    catalog_v2.write_catalog(catalog, root=root)
    catalog_v2.write_legacy_index(catalog, root=root)
    achievement_catalog.write_achievement_catalogs(catalog, root=root)

    index = catalog_v2.legacy_index_from_catalog(catalog)
    index["entries"] = sort_entries(index["entries"])
    zh, en = render_human_index(index)
    (root / HUMAN_INDEX_PATH.name).write_text(zh, encoding="utf-8", newline="\n")
    (root / HUMAN_INDEX_EN_PATH.name).write_text(en, encoding="utf-8", newline="\n")
    statistics = build_statistics(index)
    write_if_changed(root / STATISTICS_PATH.relative_to(ROOT), render_svg(statistics))
    return catalog


def main() -> None:
    catalog = catalog_v2.load_catalog(root=ROOT)
    refresh_catalog(catalog, root=ROOT)
    print(
        "Refreshed index-v2.json, index.json, INDEX.md, INDEX_EN.md, "
        "achievements.md catalogs, and statistics SVG."
    )


if __name__ == "__main__":
    main()
