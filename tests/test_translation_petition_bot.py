from __future__ import annotations

import sys
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import github_issue_guard as issue_guard  # noqa: E402
import library_submission_bot as library_bot  # noqa: E402
import translation_petition_bot as petition_bot  # noqa: E402


def string_node(name: str, value: str) -> library_bot.Node:
    return library_bot.Node(1, name, value=value, raw_value=value.encode("utf-8"))


def valid_schema() -> bytes:
    achievement = library_bot.Node(
        0,
        "0",
        children=[
            string_node("name", "ACH_ONE"),
            library_bot.Node(
                0,
                "display",
                children=[
                    library_bot.Node(0, "name", children=[string_node("english", "Name")]),
                    library_bot.Node(0, "desc", children=[string_node("english", "Description")]),
                ],
            ),
        ],
    )
    return library_bot.serialize([
        library_bot.Node(0, "root", children=[library_bot.Node(0, "bits", children=[achievement])])
    ])


def petition_issue(filename: str = "UserGameStatsSchema_123.zip") -> dict:
    return {
        "number": 7,
        "labels": [{"name": "翻译请愿"}],
        "body": "\n".join([
            "### 游戏名",
            "",
            "Example Game",
            "",
            "### Steam app ID",
            "",
            "123",
            "",
            "### Steam 商店地址",
            "",
            "https://store.steampowered.com/app/123/",
            "",
            "### 希望翻译到的语言",
            "",
            "schinese, japanese",
            "",
            "### 需要翻译的成就 schema ZIP",
            "",
            f"[{filename}](https://github.com/user-attachments/assets/example)",
        ]),
    }


class TranslationPetitionValidationTests(unittest.TestCase):
    def test_guard_infers_translation_petition_from_form_heading(self) -> None:
        issue = petition_issue()
        issue["labels"] = []

        self.assertEqual("translation-petition", issue_guard.infer_issue_kind(issue))

    def test_valid_zip_with_one_matching_bin_is_recognized(self) -> None:
        def fake_download(_attachment, _token, destination: Path) -> None:
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("UserGameStatsSchema_123.bin", valid_schema())

        with mock.patch.object(petition_bot, "download_attachment", side_effect=fake_download):
            result = petition_bot.validate_petition(petition_issue(), "token")

        self.assertTrue(result["ok"])
        self.assertEqual("123", result["game_id"])
        self.assertEqual(1, result["achievement_count"])
        self.assertEqual(["schinese", "japanese"], result["target_languages"])

    def test_filename_must_match_app_id(self) -> None:
        result = petition_bot.validate_petition(petition_issue("UserGameStatsSchema_456.zip"), "token")

        self.assertFalse(result["ok"])
        self.assertIn("UserGameStatsSchema_123.zip", "\n".join(result["errors"]))

    def test_zip_must_contain_exactly_one_matching_bin(self) -> None:
        def fake_download(_attachment, _token, destination: Path) -> None:
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("UserGameStatsSchema_123.bin", valid_schema())
                archive.writestr("notes.txt", "extra")

        with mock.patch.object(petition_bot, "download_attachment", side_effect=fake_download):
            result = petition_bot.validate_petition(petition_issue(), "token")

        self.assertFalse(result["ok"])
        self.assertIn("必须且只能包含一个 schema", "\n".join(result["errors"]))

    def test_success_acknowledgement_is_idempotent(self) -> None:
        result = {
            "ok": True,
            "errors": [],
            "game_name": "Example Game",
            "game_id": "123",
            "target_languages": ["schinese"],
            "achievement_count": 1,
        }
        with (
            mock.patch.object(petition_bot, "validate_petition", return_value=result),
            mock.patch.object(petition_bot, "comment_issue_once") as comment_once,
        ):
            petition_bot.handle_petition({"issue": petition_issue()}, "owner/repo", "token")

        comment_once.assert_called_once()
        self.assertIn("翻译请愿已收到", comment_once.call_args.args[3])
        self.assertEqual(petition_bot.RECEIVED_MARKER, comment_once.call_args.args[4])


if __name__ == "__main__":
    unittest.main()
