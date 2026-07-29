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


class PullRequestBodyTests(unittest.TestCase):
    def build_body(
        self,
        contributor_notes: str = "",
        rows_by_variant: dict[str, list[dict[str, str]]] | None = None,
    ) -> str:
        entry = {
            "game_name": "Example Game",
            "game_id": "123",
            "store_url": "https://store.steampowered.com/app/123/",
            "languages": ["schinese"],
            "schema_file": "files/123/UserGameStatsSchema_123.bin",
            "file_size_bytes": 42,
            "achievement_count": 1,
            "sha256": "abc123",
            "contributor_id": "translator",
            "contributors": ["translator"],
            "submitted_at": "2026-07-13T00:00:00Z",
            "updated_at": "2026-07-13T00:00:00Z",
        }
        rows = [{
            "index": "1",
            "api_name": "ACH_ONE",
            "english_name": "Name",
            "english_description": "Description",
            "schinese_name": "名称",
            "schinese_description": "描述",
        }]
        return bot.build_submission_pr_body(
            kind="translation-contribution",
            entry=entry,
            coverage={"schinese": 1},
            rows=rows,
            languages=["schinese"],
            issue_url="https://github.com/example/repo/issues/1",
            contributor_notes=contributor_notes,
            rows_by_variant=rows_by_variant,
        )

    def test_multiline_issue_notes_are_transferred_to_pr_body(self) -> None:
        fields = bot.parse_issue_form("### 备注\n\n翻译来源：官方文本\n\n已在 Steam 中测试。")
        notes = bot.optional_field_value(fields, ["Notes", "备注"])

        body = self.build_body(notes)

        self.assertIn("## Contributor Notes\n\n翻译来源：官方文本\n\n已在 Steam 中测试。", body)

    def test_no_response_placeholder_does_not_create_notes_section(self) -> None:
        fields = bot.parse_issue_form("### Notes\n\n_No response_")
        notes = bot.optional_field_value(fields, ["Notes", "备注"])

        body = self.build_body(notes)

        self.assertEqual("", notes)
        self.assertNotIn("## Contributor Notes", body)

    def test_multi_version_body_lists_achievement_text_for_every_variant(self) -> None:
        default_rows = [{
            "api_name": "ACH_ONE",
            "schinese_name": "原文版名称",
            "schinese_description": "原文版描述",
        }]
        clean_rows = [{
            "api_name": "ACH_ONE",
            "schinese_name": "和谐版名称",
            "schinese_description": "和谐版描述",
        }]

        body = self.build_body(rows_by_variant={
            "default": default_rows,
            "clean": clean_rows,
        })

        self.assertIn("## Achievement Text (`default`)", body)
        self.assertIn("原文版名称", body)
        self.assertIn("## Achievement Text (`clean`)", body)
        self.assertIn("和谐版名称", body)

    def test_single_version_body_keeps_one_achievement_text_section(self) -> None:
        body = self.build_body()

        self.assertEqual(1, body.count("## Achievement Text ("))
