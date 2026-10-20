"""Deterministic, field-oriented Markdown kept only in translation review PRs."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from translation_artifacts import load_artifact

import catalog_v2
from recycle_bin import recycle_path
from translation_json import render_translation
from steam_schema import sha256


def _inline(value: str | None) -> str:
    if value is None:
        return "(absent)"
    text = json.dumps(value, ensure_ascii=False)
    width = max((len(run) for run in re.findall(r"`+", text)), default=0) + 1
    fence = "`" * width
    return f"{fence}{text}{fence}"


def render_achievement_review(
    schema_name: str,
    source_sha256: str,
    current: dict[str, Any],
    previous: dict[str, Any],
) -> str:
    """Keep one field per source line and neighboring languages together."""
    changes = []
    for api_name in dict.fromkeys([*current, *previous]):
        before, after = previous.get(api_name), current.get(api_name)
        if before == after:
            continue
        kind = "Added" if before is None else "Removed" if after is None else "Changed"
        changes.append((api_name, kind, before, after))
    counts = {kind: sum(item[1] == kind for item in changes) for kind in ("Added", "Changed", "Removed")}
    lines = [
        "# Achievement review", "",
        f"Schema: {_inline(schema_name)}",
        f"Source SHA-256: {_inline(source_sha256)}",
        f"Added: {counts['Added']}; Changed: {counts['Changed']}; Removed: {counts['Removed']}",
    ]
    if not changes:
        lines.extend(["", "No achievement text changes."])
    for api_name, kind, before, after in changes:
        lines.extend(["", f"## {kind}: {_inline(api_name)}"])
        old = (before or {}).get("translations", {})
        new = (after or {}).get("translations", {})
        languages = sorted(set(old) | set(new))
        for field in ("name", "description"):
            lines.extend(["", f"### {field.title()}", ""])
            for language in languages:
                old_value = old.get(language, {}).get(field)
                new_value = new.get(language, {}).get(field)
                if kind == "Changed" and old_value != new_value:
                    lines.append(f"- **{language} / before:** {_inline(old_value)}")
                    lines.append(f"- **{language} / after:** {_inline(new_value)}")
                else:
                    value = old_value if after is None else new_value
                    lines.append(f"- **{language}:** {_inline(value)}")
    return "\n".join(lines) + "\n"


def _base_commit(base_ref: str, root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _previous_achievements(
    game_id: str, variant_id: str, *, base_ref: str, root: Path = catalog_v2.REPO_ROOT,
) -> dict[str, Any]:
    relative = catalog_v2.translation_json_relative_path(game_id, variant_id)
    base = _base_commit(base_ref, root)
    indexed = subprocess.run(
        ["git", "ls-tree", "-z", base, "--", relative],
        cwd=root, check=True, capture_output=True,
    )
    previous: dict[str, Any] = {}
    if indexed.stdout:
        original = subprocess.run(
            ["git", "show", f"{base}:{relative}"], cwd=root, check=True, capture_output=True,
        ).stdout
        previous = json.loads(original)["achievements"]
    return previous


def expected_review_catalog(
    game_id: str, variant_id: str, *, base_ref: str, root: Path = catalog_v2.REPO_ROOT,
) -> str:
    previous = _previous_achievements(game_id, variant_id, base_ref=base_ref, root=root)
    path = root / catalog_v2.schema_relative_path(game_id, variant_id)
    if not path.is_file():
        path = path.with_suffix(".json")
    data, content = load_artifact(path)
    current = content if isinstance(content, dict) else json.loads(render_translation(game_id, variant_id, data, content))
    review = render_achievement_review(path.name, sha256(data), current["achievements"], previous)
    if isinstance(content, dict):
        source = content["source"]
        review += (f"\n## Recorded source (contributor supplied)\n\n"
                   f"- Kind: {_inline(source['kind'])}\n- URL: {_inline(source['url'])}\n"
                   f"- Retrieved: {_inline(source['retrieved_at'])}\n"
                   "- Display text only; this does not verify a Steam client BIN.\n")
    return review


def write_entry_review_catalogs(
    entry: dict[str, Any], *, base_ref: str = "origin/main", root: Path = catalog_v2.REPO_ROOT,
) -> list[Path]:
    from library_index import validated_entry_schema_variants

    base = _base_commit(base_ref, root)
    game_id = str(entry["game_id"])
    written = []
    for record in validated_entry_schema_variants(entry):
        variant_id = str(record["variant_id"])
        path = (root / catalog_v2.schema_relative_path(game_id, variant_id)).with_name("achievements.md")
        text = expected_review_catalog(game_id, variant_id, base_ref=base, root=root)
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def recycle_review_catalogs(game_id: str, game: dict[str, Any], *, root: Path) -> None:
    for variant_id in game["variants"]:
        path = (root / catalog_v2.schema_relative_path(game_id, variant_id)).with_name("achievements.md")
        if path.exists():
            recycle_path(path, boundary=root / "files" / game_id)
