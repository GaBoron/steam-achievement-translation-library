from __future__ import annotations

import sys
import tempfile
import unittest
import json
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import check_repository  # noqa: E402
import library_submission_bot as bot  # noqa: E402


def string_node(name: str, value: str) -> bot.Node:
    return bot.Node(1, name, value=value, raw_value=value.encode("utf-8"))


def achievement_node(api_name: str = "ACH_ONE") -> bot.Node:
    return bot.Node(
        0,
        "0",
        children=[
            string_node("name", api_name),
            bot.Node(
                0,
                "display",
                children=[
                    bot.Node(0, "name", children=[string_node("english", "Name"), string_node("schinese", "名称")]),
                    bot.Node(0, "desc", children=[string_node("english", "Description"), string_node("schinese", "描述")]),
                ],
            ),
        ],
    )


def schema_nodes(*achievements: bot.Node) -> list[bot.Node]:
    return [bot.Node(0, "root", children=[bot.Node(0, "bits", children=list(achievements))])]


class SchemaValidationTests(unittest.TestCase):
    def test_schema_roundtrip_and_language_coverage(self) -> None:
        nodes = schema_nodes(achievement_node())
        data = bot.serialize(nodes)

        base_rows = bot.validate_schema_structure(data, nodes)
        rows = bot.achievement_rows(nodes, ["schinese"])

        self.assertEqual(["ACH_ONE"], [row["api_name"] for row in base_rows])
        self.assertEqual({"schinese": 1}, bot.require_language_coverage(rows, ["schinese"]))

    def test_empty_official_english_description_is_allowed(self) -> None:
        rows = [{
            "api_name": "ACH",
            "english_name": "Hidden achievement",
            "english_description": "",
            "schinese_name": "隐藏成就",
            "schinese_description": "",
        }]

        coverage, missing = bot.language_coverage(rows, ["english", "schinese"])

        self.assertEqual(1, coverage["english"])
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

        with mock.patch.object(bot, "download_attachment", side_effect=fake_download):
            with self.assertRaisesRegex(ValueError, "上传文件名必须是"):
                bot.validate_schema_submission(attachment, None, "123", ["schinese"])

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
                bot,
                "download_attachment",
                side_effect=lambda _attachment, _token, destination: destination.write_bytes(archive_path.read_bytes()),
            ), self.assertRaisesRegex(ValueError, "语言覆盖不完整"):
                bot.validate_schema_package(attachment, None, "123", ["schinese"])

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
            bot, "REPO_ROOT", Path(tmp)
        ), mock.patch.object(bot, "FILES_ROOT", Path(tmp) / "files"):
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
            ], False)

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
            bot, "REPO_ROOT", Path(tmp)
        ), mock.patch.object(bot, "FILES_ROOT", Path(tmp) / "files"):
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
            ], True)

            _effective, records = bot.save_schema_package(package, "123", existing)

            self.assertFalse(beta.exists())
            self.assertTrue((root / "files/123/stable/UserGameStatsSchema_123.bin").is_file())
            self.assertEqual(["default", "stable"], [record["variant_id"] for record in records])


class RepositoryIntegrityTests(unittest.TestCase):
    def test_current_repository_has_no_integrity_errors(self) -> None:
        report = check_repository.check_repository()

        self.assertEqual([], report.errors)
        self.assertGreater(report.checked_entries, 0)
        self.assertGreaterEqual(report.checked_files, report.checked_entries)


if __name__ == "__main__":
    unittest.main()
