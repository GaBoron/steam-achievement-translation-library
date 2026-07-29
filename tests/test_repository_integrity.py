from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow-scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_repository  # noqa: E402
import library_submission_bot as bot  # noqa: E402
import library_index  # noqa: E402
import schema_package  # noqa: E402
import submission_inputs  # noqa: E402
from library_test_support import achievement_node, schema_nodes, string_node  # noqa: E402


class RepositoryIntegrityTests(unittest.TestCase):
    def test_possibly_ineffective_state_is_rendered(self) -> None:
        index = {
            "states": {
                "current": {"label_zh": "可用", "label_en": "Current"},
                "possibly_ineffective": {"label_zh": "可能不生效", "label_en": "May not work"},
                "outdated": {"label_zh": "可能过期", "label_en": "Possibly outdated"},
            },
            "entries": [{
                "game_name": "Example Game",
                "game_id": "123",
                "store_url": "https://store.steampowered.com/app/123/",
                "languages": ["schinese"],
                "schema_file": "files/123/UserGameStatsSchema_123.bin",
                "file_size_bytes": 42,
                "achievement_count": 1,
                "contributors": ["translator"],
                "updated_at": "2026-07-21T00:00:00Z",
                "status": "possibly_ineffective",
            }],
        }

        zh_index, en_index = bot.render_human_index(index)

        self.assertIn("| 可能不生效 |", zh_index)
        self.assertIn("| May not work |", en_index)

    def test_unknown_index_state_is_rejected(self) -> None:
        states = {
            "current": {"zh": "可用", "en": "Current"},
            "possibly_ineffective": {"zh": "可能不生效", "en": "May not work"},
            "outdated": {"zh": "可能过期", "en": "Possibly outdated"},
        }

        with self.assertRaisesRegex(ValueError, "unknown index state"):
            bot.status_text({"game_id": "123", "status": "unknown"}, "zh", states)

    def test_current_repository_has_no_integrity_errors(self) -> None:
        translation_pr_mode = os.environ.get("ALLOW_UNINDEXED_SCHEMA_FILES", "").lower() == "true"
        error_report_pr_mode = os.environ.get("ALLOW_STALE_HUMAN_INDEXES", "").lower() == "true"
        report = check_repository.check_repository(
            allow_unindexed_schema_files=translation_pr_mode,
            allow_stale_index_metadata=translation_pr_mode,
            allow_stale_human_indexes=error_report_pr_mode,
        )

        self.assertEqual([], report.errors)
        self.assertGreater(report.checked_entries, 0)
        self.assertGreaterEqual(report.checked_files, report.checked_entries)

    def test_stale_human_indexes_are_allowed_only_in_error_report_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "index.json"
            files_root = root / "files"
            human_index = root / "INDEX.md"
            human_index_en = root / "INDEX_EN.md"
            files_root.mkdir()
            index_path.write_text('{"entries": []}\n', encoding="utf-8")
            human_index.write_text("stale zh\n", encoding="utf-8")
            human_index_en.write_text("stale en\n", encoding="utf-8")

            with (
                mock.patch.object(check_repository, "INDEX_PATH", index_path),
                mock.patch.object(check_repository, "FILES_ROOT", files_root),
                mock.patch.object(check_repository, "HUMAN_INDEX_PATH", human_index),
                mock.patch.object(check_repository, "HUMAN_INDEX_EN_PATH", human_index_en),
                mock.patch.object(check_repository, "render_human_index", return_value=("expected zh\n", "expected en\n")),
            ):
                strict = check_repository.check_repository()
                allowed = check_repository.check_repository(allow_stale_human_indexes=True)

            self.assertEqual(
                ["INDEX.md is out of sync with index.json", "INDEX_EN.md is out of sync with index.json"],
                strict.errors,
            )
            self.assertEqual([], allowed.errors)
            self.assertEqual(2, len(allowed.warnings))

    def test_unindexed_schema_is_rejected_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files_root = Path(tmp) / "files"
            schema_path = files_root / "123" / "UserGameStatsSchema_123.bin"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_bytes(bot.serialize(schema_nodes(achievement_node())))
            report = check_repository.CheckReport()

            with mock.patch.object(check_repository, "FILES_ROOT", files_root):
                check_repository.check_unindexed_schema_files(
                    report,
                    {schema_path.resolve()},
                    allow_unindexed_schema_files=False,
                )

        self.assertEqual(["unindexed schema file: files/123/UserGameStatsSchema_123.bin"], report.errors)
        self.assertEqual(0, report.checked_files)

    def test_valid_unindexed_schema_is_checked_in_translation_pr_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files_root = Path(tmp) / "files"
            schema_path = files_root / "123" / "UserGameStatsSchema_123.bin"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_bytes(bot.serialize(schema_nodes(achievement_node())))
            report = check_repository.CheckReport()

            with mock.patch.object(check_repository, "FILES_ROOT", files_root):
                check_repository.check_unindexed_schema_files(
                    report,
                    {schema_path.resolve()},
                    allow_unindexed_schema_files=True,
                )

        self.assertEqual([], report.errors)
        self.assertEqual(1, report.checked_files)

    def test_invalid_unindexed_schema_still_fails_in_translation_pr_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files_root = Path(tmp) / "files"
            schema_path = files_root / "123" / "UserGameStatsSchema_123.bin"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_bytes(b"not a Binary KeyValues schema")
            report = check_repository.CheckReport()

            with mock.patch.object(check_repository, "FILES_ROOT", files_root):
                check_repository.check_unindexed_schema_files(
                    report,
                    {schema_path.resolve()},
                    allow_unindexed_schema_files=True,
                )

        self.assertEqual(1, len(report.errors))
        self.assertIn("invalid unindexed schema files/123/UserGameStatsSchema_123.bin", report.errors[0])
        self.assertEqual(0, report.checked_files)

    def test_stale_index_metadata_is_allowed_only_in_translation_pr_mode(self) -> None:
        data = bot.serialize(schema_nodes(achievement_node()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files_root = root / "files"
            schema_path = files_root / "123" / "UserGameStatsSchema_123.bin"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_bytes(data)
            variant = {
                "variant_id": "default",
                "primary": True,
                "schema_file": "files/123/UserGameStatsSchema_123.bin",
                "file_size_bytes": len(data) + 1,
                "sha256": "0" * 64,
                "achievement_count": 2,
            }

            with mock.patch.object(library_index, "REPO_ROOT", root), mock.patch.object(
                check_repository, "FILES_ROOT", files_root
            ):
                strict_report = check_repository.CheckReport()
                check_repository._check_schema_path(
                    strict_report,
                    "123",
                    variant,
                    set(),
                    allow_stale_index_metadata=False,
                )
                translation_pr_report = check_repository.CheckReport()
                check_repository._check_schema_path(
                    translation_pr_report,
                    "123",
                    variant,
                    set(),
                    allow_stale_index_metadata=True,
                )

        self.assertEqual(3, len(strict_report.errors))
        self.assertEqual([], strict_report.warnings)
        self.assertEqual([], translation_pr_report.errors)
        self.assertEqual(3, len(translation_pr_report.warnings))
        self.assertTrue(
            all(
                warning.startswith("stale index metadata allowed for translation PR: 123:")
                for warning in translation_pr_report.warnings
            )
        )
