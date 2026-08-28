"""Git and schema-file mutations for translation pull requests."""
from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from github_repository import github_request
from library_index import (
    entry_schema_variants,
    existing_entry,
    load_index,
    repository_path,
    schema_file_size_bytes,
    schema_variant_relative_path,
    upsert_index_entry,
    validated_entry_schema_variants,
    write_human_index,
    write_index,
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
    run(["git", "fetch", "origin", "main"], check=False)
    run(["git", "fetch", "origin", branch], check=False)
    run(["git", "checkout", "-B", branch, f"origin/{branch}"])
    run(["git", "rebase", "origin/main"])
    return branch


def remove_index_entries(game_ids: set[str]) -> dict[str, Any]:
    index = load_index()
    index["entries"] = [entry for entry in index.get("entries", []) if str(entry.get("game_id")) not in game_ids]
    write_index(index)
    write_human_index(index)
    return index


def upsert_entry_for_pr(old_game_id: str, entry: dict[str, Any]) -> None:
    if old_game_id and old_game_id != str(entry.get("game_id")):
        remove_index_entries({old_game_id, str(entry.get("game_id"))})
    upsert_index_entry(entry)


def rename_schema_variants(
    old_game_id: str,
    new_game_id: str,
    meta: dict[str, Any],
) -> tuple[str, list[dict[str, Any]] | None]:
    if old_game_id == new_game_id:
        return str(meta["schema_file"]), meta.get("schema_files")
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
        updated = dict(record)
        updated["schema_file"] = destination_relative
        moves.append((source, destination, updated))
    for source, destination, _record in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    old_root = (FILES_ROOT / old_game_id).resolve()
    for directory in sorted({source.parent for source, _destination, _record in moves}, key=lambda path: len(path.parts), reverse=True):
        current = directory
        while current != old_root.parent and current.is_relative_to(old_root):
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
    updated_records = [record for _source, _destination, record in moves]
    updated_records.sort(key=lambda record: (not bool(record.get("primary")), str(record.get("variant_id"))))
    primary = next(record for record in updated_records if record.get("primary"))
    keep_records = updated_records if schema_files is not None else None
    return str(primary["schema_file"]), keep_records


def commit_and_push(branch: str, message: str, add_paths: list[str] | None = None) -> bool:
    configure_git_identity()
    run(["git", "add", *(add_paths or ["files", "index.json", "index-v2.json", "INDEX.md", "INDEX_EN.md"])])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return False
    run(["git", "commit", "-m", message])
    push_branch(branch)
    return True


def push_branch(branch: str) -> None:
    run(["git", "fetch", "origin", branch], check=False)
    push = run(["git", "push", "--force-with-lease", "--set-upstream", "origin", branch], check=False)
    if push.returncode != 0:
        run(["git", "fetch", "origin", branch], check=False)
        run(["git", "push", "--force-with-lease", "--set-upstream", "origin", branch])


def push_main_with_retry() -> None:
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode == 0:
        return
    run(["git", "fetch", "origin", "main"])
    run(["git", "rebase", "origin/main"])
    run(["git", "push", "origin", "HEAD:main"])


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
