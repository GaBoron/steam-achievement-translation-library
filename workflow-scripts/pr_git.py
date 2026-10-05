"""Git and schema-file mutations for translation pull requests."""
from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from github_repository import github_request
import catalog_v2
from catalog_v2 import v1_schema_relative_path
from schema_compatibility import recycle_legacy_translation_json
from library_index import (
    entry_schema_variants,
    existing_entry,
    load_index,
    repository_path,
    schema_file_size_bytes,
    schema_variant_relative_path,
    validated_entry_schema_variants,
)


ROOT = Path(__file__).resolve().parent.parent
FILES_ROOT = ROOT / "files"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        command = " ".join(args)
        print(f"Command failed: {command}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        result.check_returncode()
    return result


def configure_git_identity() -> None:
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])


def checkout_pr_branch(pr: dict[str, Any]) -> str:
    branch = str((pr.get("head") or {}).get("ref") or "")
    if not branch.startswith("translation-library/"):
        raise RuntimeError("Only translation-library PR branches can be updated by automation.")
    configure_git_identity()
    run(["git", "fetch", "origin", "main", branch])
    expected_head = str((pr.get("head") or {}).get("sha") or "")
    actual_head = run(["git", "rev-parse", f"origin/{branch}"]).stdout.strip()
    if expected_head and actual_head != expected_head:
        raise RuntimeError("The PR changed while its command was being processed; retry against its current head.")
    run(["git", "checkout", "-b", branch, f"origin/{branch}"])
    run(["git", "merge", "--no-commit", "--no-ff", "origin/main"])
    return branch


def rename_schema_variants(
    old_game_id: str,
    new_game_id: str,
    meta: dict[str, Any],
) -> tuple[str, list[dict[str, Any]] | None]:
    if old_game_id == new_game_id:
        return str(meta["schema_file"]), meta.get("schema_files")
    published = catalog_v2.load_catalog(root=ROOT)["games"]
    if old_game_id in published or new_game_id in published:
        raise ValueError("只能修正尚未入库的新游戏 App ID；不能移动或覆盖已收录的游戏。")
    schema_files = meta.get("schema_files")
    if schema_files is None:
        indexed = existing_entry(load_index(), old_game_id)
        if indexed and isinstance(indexed.get("schema_files"), list):
            schema_files = entry_schema_variants(indexed)
            for record in schema_files:
                if record.get("primary"):
                    record.update({
                        "schema_file": meta.get("schema_file"),
                        "file_size_bytes": schema_file_size_bytes(str(meta.get("schema_file") or "")),
                        "sha256": meta.get("sha256"),
                        "achievement_count": int(str(meta.get("achievement_count") or 0)),
                    })
    entry = {
        "schema_file": meta.get("schema_file"),
        "schema_files": schema_files,
        "file_size_bytes": 0,
        "sha256": meta.get("sha256"),
        "achievement_count": meta.get("achievement_count"),
    }
    records = validated_entry_schema_variants(entry)
    if not records:
        raise ValueError("当前 PR 没有可重命名的 schema 文件。")
    moves: list[tuple[Path, Path, dict[str, Any]]] = []
    for record in records:
        source = repository_path(str(record["schema_file"]))
        if not source.is_file():
            raise ValueError(f"当前 schema 文件不存在：{record['schema_file']}")
        destination_relative = schema_variant_relative_path(
            new_game_id,
            str(record["variant_id"]),
            bool(record.get("primary")),
        )
        destination = repository_path(destination_relative)
        if destination.exists() and destination != source:
            raise ValueError(f"目标 schema 文件已存在：{destination_relative}")
        for companion in (destination.with_name("achievements.md"), destination.with_suffix(".json")):
            if companion.exists() and companion.parent != source.parent:
                raise ValueError(f"目标派生文件已存在：{companion.relative_to(FILES_ROOT.parent).as_posix()}")
        updated = dict(record)
        updated["schema_file"] = destination_relative
        moves.append((source, destination, updated))
    compatibility_moves: list[tuple[Path, Path]] = []
    legacy_source = repository_path(v1_schema_relative_path(old_game_id))
    legacy_destination = repository_path(v1_schema_relative_path(new_game_id))
    if legacy_source.is_file():
        if legacy_destination.exists():
            raise ValueError(f"目标兼容文件已存在：{legacy_destination.relative_to(FILES_ROOT.parent).as_posix()}")
        compatibility_moves.append((legacy_source, legacy_destination))
    recycle_legacy_translation_json(old_game_id, root=ROOT)
    for source, destination, _record in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        source_catalog = source.with_name("achievements.md")
        destination_catalog = destination.with_name("achievements.md")
        if source_catalog.is_file():
            source_catalog.replace(destination_catalog)
        source_json = source.with_suffix(".json")
        if source_json.is_file():
            source_json.replace(destination.with_suffix(".json"))
    for source, destination in compatibility_moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    # Empty old directories may remain; Git does not track them.
    updated_records = [record for _source, _destination, record in moves]
    updated_records.sort(key=lambda record: (not bool(record.get("primary")), str(record.get("variant_id"))))
    primary = next(record for record in updated_records if record.get("primary"))
    keep_records = updated_records if schema_files is not None else None
    return str(primary["schema_file"]), keep_records


def commit_and_push(branch: str, message: str, add_paths: list[str] | None = None) -> bool:
    configure_git_identity()
    if not add_paths:
        raise ValueError("PR commits require explicit game-local paths.")
    run(["git", "add", "-A", "--", *add_paths])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False
    run(["git", "commit", "-m", message])
    push_branch(branch)
    return True


def push_branch(branch: str) -> None:
    from translation_pr_validation import check_translation_pr
    report = check_translation_pr("origin/main", "HEAD")
    if report.errors:
        raise ValueError("PR validation failed: " + "; ".join(report.errors))
    run(["git", "push", "--set-upstream", "origin", branch])


def delete_pr_branch(repo: str, token: str, pr: dict[str, Any]) -> None:
    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
    if str(head_repo.get("full_name") or "") != repo:
        return
    branch = str(head.get("ref") or "")
    if not branch.startswith("translation-library/"):
        return
    encoded = urllib.parse.quote(branch, safe="/")
    github_request("DELETE", repo, token, f"/git/refs/heads/{encoded}", allow_404=True, allow_422=True)
