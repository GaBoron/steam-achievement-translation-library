from __future__ import annotations

import sys
import tempfile
import unittest
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


class RepositoryIntegrityTests(unittest.TestCase):
    def test_current_repository_has_no_integrity_errors(self) -> None:
        report = check_repository.check_repository()

        self.assertEqual([], report.errors)
        self.assertGreater(report.checked_entries, 0)
        self.assertGreaterEqual(report.checked_files, report.checked_entries)


if __name__ == "__main__":
    unittest.main()
