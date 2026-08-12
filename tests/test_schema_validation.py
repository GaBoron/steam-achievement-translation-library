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
import submission_validation  # noqa: E402
from library_test_support import achievement_node, schema_nodes, string_node  # noqa: E402


class SchemaValidationTests(unittest.TestCase):
    def test_common_fields_derive_canonical_store_url_from_app_id(self) -> None:
        fields = {
            "游戏名": "示例游戏",
            "Steam app ID": "123",
        }

        game_name, game_id, store_url, errors = submission_validation.validate_common_fields(fields)

        self.assertEqual("示例游戏", game_name)
        self.assertEqual("123", game_id)
        self.assertEqual("https://store.steampowered.com/app/123/", store_url)
        self.assertEqual([], errors)

    def test_report_type_maps_to_index_states(self) -> None:
        self.assertEqual("outdated", bot.report_state("文件可能过期"))
        self.assertEqual("outdated", bot.report_state("File may be outdated"))
        self.assertEqual("possibly_ineffective", bot.report_state("文件可能不生效"))
        self.assertEqual("possibly_ineffective", bot.report_state("File may not work"))

    def test_error_report_marks_file_as_possibly_ineffective(self) -> None:
        event = {
            "issue": {
                "number": 42,
                "html_url": "https://github.com/example/repo/issues/42",
                "user": {"login": "reporter"},
                "body": """### 游戏名

示例游戏

### Steam app ID

123

### 错误类型

文件可能不生效

### 错误说明

替换并重启后仍显示英文。

### 参考来源

_No response_
""",
            },
        }
        existing = {
            "game_name": "示例游戏",
            "game_id": "123",
            "store_url": "https://store.steampowered.com/app/123/",
            "schema_file": "files/123/UserGameStatsSchema_123.bin",
            "file_size_bytes": 42,
            "sha256": "abc",
            "updated_at": "2026-07-21T00:00:00Z",
            "status": "current",
        }
        saved_entry: dict = {}

        def capture_entry(entry: dict, issue_number: int) -> str:
            saved_entry.update(entry)
            self.assertEqual(42, issue_number)
            return ".github/translation-reports/42.json"

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            bot, "load_index", return_value={"entries": [existing]}
        ), mock.patch.object(bot, "write_pending_report", side_effect=capture_entry), mock.patch.object(
            bot, "upsert_index_entry"
        ) as upsert_index:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                result = bot.validate_outdated_report(event)
                pr_body = Path("pr_body.md").read_text(encoding="utf-8")
            finally:
                os.chdir(old_cwd)

        self.assertEqual("possibly_ineffective", saved_entry["status"])
        self.assertEqual("https://store.steampowered.com/app/123/", saved_entry["store_url"])
        self.assertEqual("possibly_ineffective", saved_entry["report"]["type"])
        self.assertNotIn("outdated", saved_entry)
        self.assertEqual("报告错误", result["pr_labels"])
        self.assertEqual(".github/translation-reports/42.json", result["report_path"])
        upsert_index.assert_not_called()
        self.assertIn("## Achievement Translation Error Report", pr_body)
        self.assertIn("- Report type: `possibly_ineffective`", pr_body)

    def test_open_translation_pr_is_found_by_game_id(self) -> None:
        pulls = [{
            "number": 42,
            "html_url": "https://github.com/example/repo/pull/42",
            "body": "## Translation Library Submission\n\n- Steam app ID: `123`\n",
            "head": {"ref": "translation-library/issue-41"},
        }]

        with mock.patch.object(submission_inputs, "github_api_get", return_value=pulls):
            result = bot.find_open_translation_pr("example/repo", "token", "123")

        self.assertIsNotNone(result)
        self.assertEqual(42, result["number"])

    def test_unrelated_or_non_automation_pr_is_ignored(self) -> None:
        pulls = [
            {
                "number": 42,
                "body": "- Steam app ID: `456`",
                "head": {"ref": "translation-library/issue-41"},
            },
            {
                "number": 43,
                "body": "- Steam app ID: `123`",
                "head": {"ref": "feature/manual-change"},
            },
        ]

        with mock.patch.object(submission_inputs, "github_api_get", return_value=pulls):
            result = bot.find_open_translation_pr("example/repo", "token", "123")

        self.assertIsNone(result)

    def test_duplicate_open_pr_is_non_retryable(self) -> None:
        event = {
            "issue": {
                "number": 99,
                "html_url": "https://github.com/example/repo/issues/99",
                "body": """### 游戏名

示例游戏

### Steam app ID

123

### Steam 商店地址

https://store.steampowered.com/app/123/

### 上传文件包含的语言

schinese

### 成就 schema ZIP

[UserGameStatsSchema_123.zip](https://github.com/user-attachments/files/1/UserGameStatsSchema_123.zip)
""",
            },
            "repository": {"full_name": "example/repo"},
        }
        duplicate = {"number": 42, "html_url": "https://github.com/example/repo/pull/42"}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            bot, "load_index", return_value={"entries": []}
        ), mock.patch.object(bot, "find_open_translation_pr", return_value=duplicate):
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with self.assertRaises(SystemExit):
                    bot.validate_translation_or_update(event, "token", "translation-contribution")
                result = json.loads(Path("submission_result.json").read_text(encoding="utf-8"))
            finally:
                os.chdir(old_cwd)

        self.assertFalse(result["retry_allowed"])
        self.assertTrue(result["close_issue"])
        self.assertEqual(
            "Steam app ID 123 已有正在审核的投稿 PR：#42。请在该 PR 中继续处理，不要重复投稿。",
            result["errors"][0],
        )
        self.assertNotIn("https://github.com/example/repo/pull/42", result["errors"][0])

    def test_duplicate_index_entry_is_non_retryable(self) -> None:
        event = {
            "issue": {
                "number": 99,
                "body": "### Steam app ID\n\n123\n",
            },
        }

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            bot, "load_index", return_value={"entries": [{"game_id": "123"}]}
        ):
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with self.assertRaises(SystemExit):
                    bot.validate_translation_or_update(event, None, "translation-contribution")
                result = json.loads(Path("submission_result.json").read_text(encoding="utf-8"))
            finally:
                os.chdir(old_cwd)

        self.assertFalse(result["retry_allowed"])
        self.assertTrue(result["close_issue"])

    def test_schema_roundtrip_and_language_coverage(self) -> None:
        nodes = schema_nodes(achievement_node())
        data = bot.serialize(nodes)

        base_rows = bot.validate_schema_structure(data, nodes)
        rows = bot.achievement_rows(nodes, ["schinese"])

        self.assertEqual(["ACH_ONE"], [row["api_name"] for row in base_rows])
        self.assertEqual(["english", "schinese"], bot.schema_languages(nodes))
        self.assertEqual({"schinese": 1}, bot.require_language_coverage(rows, ["schinese"]))

    def test_language_detection_ignores_reserved_and_partial_nodes(self) -> None:
        first = achievement_node("FIRST")
        second = achievement_node("SECOND")
        first_name = bot.nested(first, "display", "name")
        first_desc = bot.nested(first, "display", "desc")
        assert first_name is not None and first_desc is not None
        first_name.children.extend([string_node("japanese", "名前"), string_node("token", "#NAME")])
        first_desc.children.extend([string_node("japanese", "説明"), string_node("token", "#DESC")])

        self.assertEqual(
            ["english", "schinese"],
            bot.schema_languages(schema_nodes(first, second)),
        )

    def test_language_detection_keeps_empty_complete_fields(self) -> None:
        achievement = achievement_node()
        display_desc = bot.nested(achievement, "display", "desc")
        assert display_desc is not None
        for child in display_desc.children:
            child.value = ""

        self.assertEqual(
            ["english", "schinese"],
            bot.schema_languages(schema_nodes(achievement)),
        )

    def test_names_and_descriptions_may_be_empty_in_every_language(self) -> None:
        rows = [{
            "api_name": "ACH",
            "english_name": "",
            "english_description": "",
            "schinese_name": "",
            "schinese_description": "",
        }]

        coverage, missing = bot.language_coverage(rows, ["english", "schinese"])

        self.assertEqual(1, coverage["english"])
        self.assertEqual([], missing["english"])
        self.assertEqual(1, coverage["schinese"])
        self.assertEqual([], missing["schinese"])

    def test_names_and_descriptions_are_checked_independently(self) -> None:
        rows = [{
            "api_name": "ACH",
            "english_name": "Achievement",
            "english_description": "",
            "schinese_name": "成就",
            "schinese_description": "",
        }]

        coverage, missing = bot.language_coverage(rows, ["english", "schinese"])

        self.assertEqual({"english": 1, "schinese": 1}, coverage)
        self.assertEqual({"english": [], "schinese": []}, missing)

    def test_description_must_exist_in_every_language_or_none(self) -> None:
        rows = [{
            "api_name": "ACH",
            "english_name": "Achievement",
            "english_description": "Original description",
            "schinese_name": "成就",
            "schinese_description": "",
        }]

        coverage, missing = bot.language_coverage(rows, ["english", "schinese"])

        self.assertEqual(1, coverage["english"])
        self.assertEqual(0, coverage["schinese"])
        self.assertEqual([], missing["english"])
        self.assertEqual(["ACH"], missing["schinese"])

    def test_name_must_exist_in_every_language_or_none(self) -> None:
        rows = [{
            "api_name": "ACH",
            "english_name": "Achievement",
            "english_description": "Description",
            "schinese_name": "",
            "schinese_description": "描述",
        }]

        coverage, missing = bot.language_coverage(rows, ["english", "schinese"])

        self.assertEqual(1, coverage["english"])
        self.assertEqual(0, coverage["schinese"])
        self.assertEqual([], missing["english"])
        self.assertEqual(["ACH"], missing["schinese"])

    def test_duplicate_achievement_ids_are_rejected(self) -> None:
        nodes = schema_nodes(achievement_node(), achievement_node())

        with self.assertRaisesRegex(ValueError, "API name 必须唯一"):
            bot.validate_schema_structure(bot.serialize(nodes), nodes)

    def test_repository_path_rejects_escape_attempts(self) -> None:
        for value in ("../index.json", "/tmp/schema.bin", "C:/schema.bin", "files/../index.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bot.repository_path(value)

    def test_attachment_label_is_never_used_as_temporary_path(self) -> None:
        attachment = bot.Attachment(filename="../../outside.zip", url="https://github.com/user-attachments/example")

        def fake_download(_attachment: bot.Attachment, _token: str | None, destination: Path) -> None:
            self.assertEqual("attachment.zip", destination.name)
            self.assertEqual(destination.parent, destination.resolve().parent)
            destination.write_bytes(b"not a zip")

        with mock.patch.object(submission_validation, "download_attachment", side_effect=fake_download):
            with self.assertRaisesRegex(ValueError, "上传文件名必须是"):
                bot.validate_schema_submission(attachment, None, "123")

    def test_zip_must_contain_only_safe_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / "upload.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../UserGameStatsSchema_123.bin", b"data")
            attachment = bot.Attachment("UserGameStatsSchema_123.zip", "https://github.com/user-attachments/example")

            with self.assertRaisesRegex(ValueError, "不安全"):
                bot.resolve_schema_upload(archive_path, attachment, "123", tmp_path)

    def test_multi_version_manifest_is_resolved_and_validated(self) -> None:
        schema_data = bot.serialize(schema_nodes(achievement_node()))
        manifest = {
            "version": 1,
            "variants": [
                {
                    "variant_id": "default",
                    "primary": True,
                    "file": "UserGameStatsSchema_123.bin",
                    "note_zh": "原版",
                    "note_en": "Original",
                },
                {
                    "variant_id": "with-unlock-conditions",
                    "primary": False,
                    "file": "with-unlock-conditions/UserGameStatsSchema_123.bin",
                    "note_zh": "含解锁条件",
                    "note_en": "With unlock conditions",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(bot.VARIANT_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
                archive.writestr("UserGameStatsSchema_123.bin", schema_data)
                archive.writestr("with-unlock-conditions/UserGameStatsSchema_123.bin", schema_data)
            attachment = bot.Attachment("UserGameStatsSchema_123.zip", "https://github.com/user-attachments/example")

            resolved, has_manifest = bot.resolve_schema_package(archive_path, attachment, "123", tmp_path / "out")

        self.assertTrue(has_manifest)
        self.assertEqual(["default", "with-unlock-conditions"], [variant.variant_id for variant in resolved])
        self.assertTrue(resolved[0].primary)
        self.assertEqual("With unlock conditions", resolved[1].note_en)

    def test_schema_package_detects_languages_without_form_input(self) -> None:
        schema_data = bot.serialize(schema_nodes(achievement_node()))
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("UserGameStatsSchema_123.bin", schema_data)
            attachment = bot.Attachment("UserGameStatsSchema_123.zip", "https://github.com/user-attachments/example")

            with mock.patch.object(
                submission_validation,
                "download_attachment",
                side_effect=lambda _attachment, _token, destination: destination.write_bytes(archive_path.read_bytes()),
            ):
                package = bot.validate_schema_package(attachment, None, "123")

        self.assertEqual(["english", "schinese"], package.languages)
        self.assertEqual({"english": 1, "schinese": 1}, package.variants[0].coverage)

    def test_multi_version_package_requires_same_detected_languages(self) -> None:
        default_nodes = schema_nodes(achievement_node())
        japanese_achievement = achievement_node()
        japanese_name = bot.nested(japanese_achievement, "display", "name")
        japanese_desc = bot.nested(japanese_achievement, "display", "desc")
        assert japanese_name is not None and japanese_desc is not None
        japanese_name.children.append(string_node("japanese", "名前"))
        japanese_desc.children.append(string_node("japanese", "説明"))
        manifest = {
            "version": 1,
            "variants": [
                {"variant_id": "default", "primary": True, "file": "UserGameStatsSchema_123.bin", "note_zh": "原版", "note_en": "Original"},
                {"variant_id": "japanese", "primary": False, "file": "japanese/UserGameStatsSchema_123.bin", "note_zh": "日文版", "note_en": "Japanese"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(bot.VARIANT_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
                archive.writestr("UserGameStatsSchema_123.bin", bot.serialize(default_nodes))
                archive.writestr("japanese/UserGameStatsSchema_123.bin", bot.serialize(schema_nodes(japanese_achievement)))
            attachment = bot.Attachment("UserGameStatsSchema_123.zip", "https://github.com/user-attachments/example")

            with mock.patch.object(
                submission_validation,
                "download_attachment",
                side_effect=lambda _attachment, _token, destination: destination.write_bytes(archive_path.read_bytes()),
            ), self.assertRaisesRegex(ValueError, "与主版本不一致"):
                bot.validate_schema_package(attachment, None, "123")

    def test_multi_version_manifest_rejects_undeclared_files(self) -> None:
        manifest = {
            "version": 1,
            "variants": [
                {"variant_id": "default", "primary": True, "file": "UserGameStatsSchema_123.bin", "note_zh": "原版", "note_en": "Original"},
                {"variant_id": "beta", "primary": False, "file": "beta/UserGameStatsSchema_123.bin", "note_zh": "测试版", "note_en": "Beta"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(bot.VARIANT_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
                archive.writestr("UserGameStatsSchema_123.bin", b"data")
                archive.writestr("beta/UserGameStatsSchema_123.bin", b"data")
                archive.writestr("extra.txt", b"unexpected")
            attachment = bot.Attachment("UserGameStatsSchema_123.zip", "https://github.com/user-attachments/example")

            with self.assertRaisesRegex(ValueError, "清单未声明"):
                bot.resolve_schema_package(archive_path, attachment, "123", tmp_path / "out")

    def test_every_manifest_variant_must_pass_language_coverage(self) -> None:
        good_nodes = schema_nodes(achievement_node())
        incomplete = achievement_node("INCOMPLETE")
        display_desc = bot.nested(incomplete, "display", "desc")
        assert display_desc is not None
        display_desc.children = [child for child in display_desc.children if child.name != "schinese"]
        bad_nodes = schema_nodes(incomplete)
        manifest = {
            "version": 1,
            "variants": [
                {"variant_id": "default", "primary": True, "file": "UserGameStatsSchema_123.bin", "note_zh": "原版", "note_en": "Original"},
                {"variant_id": "beta", "primary": False, "file": "beta/UserGameStatsSchema_123.bin", "note_zh": "测试版", "note_en": "Beta"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(bot.VARIANT_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
                archive.writestr("UserGameStatsSchema_123.bin", bot.serialize(good_nodes))
                archive.writestr("beta/UserGameStatsSchema_123.bin", bot.serialize(bad_nodes))
            attachment = bot.Attachment("UserGameStatsSchema_123.zip", "https://github.com/user-attachments/example")

            with mock.patch.object(
                submission_validation,
                "download_attachment",
                side_effect=lambda _attachment, _token, destination: destination.write_bytes(archive_path.read_bytes()),
            ), self.assertRaisesRegex(ValueError, "语言覆盖不完整"):
                bot.validate_schema_package(attachment, None, "123")

    def test_schema_variant_marker_roundtrip(self) -> None:
        records = [{
            "variant_id": "default",
            "primary": True,
            "schema_file": "files/123/UserGameStatsSchema_123.bin",
            "note_zh": "原版",
            "note_en": "Original",
            "file_size_bytes": 10,
            "sha256": "abc",
            "achievement_count": 1,
        }]

        marker = bot.schema_variants_marker(records)

        self.assertEqual(records, bot.parse_schema_variants_marker(marker))

    def test_variant_metadata_requires_one_canonical_primary(self) -> None:
        entry = {
            "game_id": "123",
            "schema_file": "files/123/UserGameStatsSchema_123.bin",
            "schema_files": [
                {
                    "variant_id": "default",
                    "primary": True,
                    "schema_file": "files/123/UserGameStatsSchema_123.bin",
                    "note_zh": "原版",
                    "note_en": "Original",
                },
                {
                    "variant_id": "beta",
                    "primary": True,
                    "schema_file": "files/123/beta/UserGameStatsSchema_123.bin",
                    "note_zh": "测试版",
                    "note_en": "Beta",
                },
            ],
        }

        with self.assertRaisesRegex(ValueError, "只能包含一个"):
            bot.validated_entry_schema_variants(entry)

    def test_targeted_save_preserves_other_variants(self) -> None:
        original_nodes = schema_nodes(achievement_node("OLD"))
        updated_nodes = schema_nodes(achievement_node("NEW"))
        original_data = bot.serialize(original_nodes)
        updated_data = bot.serialize(updated_nodes)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            library_index, "REPO_ROOT", Path(tmp)
        ), mock.patch.object(schema_package, "FILES_ROOT", Path(tmp) / "files"):
            root = Path(tmp)
            primary = root / "files/123/UserGameStatsSchema_123.bin"
            beta = root / "files/123/beta/UserGameStatsSchema_123.bin"
            primary.parent.mkdir(parents=True)
            beta.parent.mkdir(parents=True)
            primary.write_bytes(original_data)
            beta.write_bytes(original_data)
            existing = {
                "schema_file": "files/123/UserGameStatsSchema_123.bin",
                "schema_files": [
                    {"variant_id": "default", "primary": True, "schema_file": "files/123/UserGameStatsSchema_123.bin", "note_zh": "原版", "note_en": "Original"},
                    {"variant_id": "beta", "primary": False, "schema_file": "files/123/beta/UserGameStatsSchema_123.bin", "note_zh": "测试版", "note_en": "Beta"},
                ],
            }
            rows = bot.achievement_rows(updated_nodes, ["schinese"])
            package = bot.ValidatedSchemaPackage([
                bot.ValidatedSchemaVariant("default", True, "", "", updated_data, updated_nodes, rows, {"schinese": 1})
            ], False, ["schinese"])

            effective, records = bot.save_schema_package(package, "123", existing, target_variant_id="beta")

            self.assertEqual(updated_data, beta.read_bytes())
            self.assertEqual(original_data, primary.read_bytes())
            self.assertEqual("beta", effective[0].variant_id)
            self.assertEqual(["default", "beta"], [record["variant_id"] for record in records])

    def test_full_manifest_save_removes_obsolete_variant(self) -> None:
        nodes = schema_nodes(achievement_node())
        data = bot.serialize(nodes)
        rows = bot.achievement_rows(nodes, ["schinese"])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            library_index, "REPO_ROOT", Path(tmp)
        ), mock.patch.object(schema_package, "FILES_ROOT", Path(tmp) / "files"):
            root = Path(tmp)
            primary = root / "files/123/UserGameStatsSchema_123.bin"
            beta = root / "files/123/beta/UserGameStatsSchema_123.bin"
            primary.parent.mkdir(parents=True)
            beta.parent.mkdir(parents=True)
            primary.write_bytes(data)
            beta.write_bytes(data)
            existing = {
                "schema_file": "files/123/UserGameStatsSchema_123.bin",
                "schema_files": [
                    {"variant_id": "default", "primary": True, "schema_file": "files/123/UserGameStatsSchema_123.bin"},
                    {"variant_id": "beta", "primary": False, "schema_file": "files/123/beta/UserGameStatsSchema_123.bin"},
                ],
            }
            package = bot.ValidatedSchemaPackage([
                bot.ValidatedSchemaVariant("default", True, "原版", "Original", data, nodes, rows, {"schinese": 1}),
                bot.ValidatedSchemaVariant("stable", False, "稳定版", "Stable", data, nodes, rows, {"schinese": 1}),
            ], True, ["schinese"])

            _effective, records = bot.save_schema_package(package, "123", existing)

            self.assertFalse(beta.exists())
            self.assertTrue((root / "files/123/stable/UserGameStatsSchema_123.bin").is_file())
            self.assertEqual(["default", "stable"], [record["variant_id"] for record in records])
