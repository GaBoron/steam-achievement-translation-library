from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import github_issue_guard as issue_guard  # noqa: E402
import library_submission_bot as bot  # noqa: E402
import translation_pr_maintenance as pr_maintenance  # noqa: E402


class IssueCommentAuthorizationTests(unittest.TestCase):
    def event(self, actor: str, association: str = "NONE") -> dict:
        return {
            "issue": {
                "number": 12,
                "state": "open",
                "user": {"login": "contributor"},
                "body": "### 游戏名\n\nOld name\n",
            },
            "comment": {
                "body": "/update name New name",
                "author_association": association,
                "user": {"login": actor},
            },
        }

    def test_unrelated_user_cannot_update_issue(self) -> None:
        with (
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "patch_issue_body") as patch_body,
        ):
            issue_guard.apply_issue_update("owner/repo", "token", self.event("stranger"))

        patch_body.assert_not_called()
        self.assertIn("投稿者或仓库维护者", comment.call_args.args[-1])

    def test_issue_author_can_update_issue(self) -> None:
        event = self.event("contributor")
        event["issue"]["labels"] = [{"name": "更新文件"}]
        with (
            mock.patch.object(issue_guard, "github_request", return_value=event["issue"]),
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "patch_issue_body") as patch_body,
        ):
            issue_guard.apply_issue_update("owner/repo", "token", event)

        patch_body.assert_called_once()
        self.assertIn("New name", patch_body.call_args.args[-1])
        self.assertIn("已更新 issue 描述", comment.call_args.args[-1])

    def test_collaborator_can_update_issue(self) -> None:
        self.assertTrue(issue_guard.comment_is_authorized(self.event("maintainer", "COLLABORATOR")))

    def test_doc_command_can_set_target_variant(self) -> None:
        event = self.event("contributor")
        event["issue"]["labels"] = [{"name": "更新文件"}]
        event["comment"]["body"] = "\n".join([
            "/update doc beta",
            "[UserGameStatsSchema_12.zip](https://github.com/user-attachments/example)",
        ])
        event["issue"]["body"] = "\n".join([
            "### 成就 schema ZIP",
            "",
            "old",
            "",
            "### 要更新的版本 ID",
            "",
            "_No response_",
        ])
        with (
            mock.patch.object(issue_guard, "github_request", return_value=event["issue"]),
            mock.patch.object(issue_guard, "comment_issue"),
            mock.patch.object(issue_guard, "patch_issue_body") as patch_body,
        ):
            issue_guard.apply_issue_update("owner/repo", "token", event)

        updated_body = patch_body.call_args.args[-1]
        self.assertIn("[UserGameStatsSchema_12.zip]", updated_body)
        self.assertIn("### 要更新的版本 ID\n\nbeta", updated_body)


class PullRequestCommentAuthorizationTests(unittest.TestCase):
    def event(self, actor: str, association: str = "NONE") -> dict:
        return {
            "issue": {
                "number": 34,
                "labels": [{"name": pr_maintenance.WAIT_FOR_UPDATE_LABEL}],
                "body": "\n".join([
                    "## Translation Library Submission",
                    "",
                    "- Contributors: @contributor",
                    "- Supported languages: schinese",
                ]),
            },
            "comment": {
                "body": "looks good",
                "author_association": association,
                "user": {"login": actor},
            },
        }

    def test_only_contributor_or_maintainer_clears_wait_label(self) -> None:
        with mock.patch.object(pr_maintenance, "remove_issue_label") as remove:
            pr_maintenance.clear_wait_for_update_from_comment("owner/repo", "token", self.event("stranger"))
            remove.assert_not_called()

            pr_maintenance.clear_wait_for_update_from_comment("owner/repo", "token", self.event("contributor"))
            remove.assert_called_once_with("owner/repo", "token", 34, pr_maintenance.WAIT_FOR_UPDATE_LABEL)

    def test_unrelated_user_cannot_trigger_pr_checkout(self) -> None:
        event = self.event("stranger")
        event["comment"]["body"] = "/update name Changed"
        with (
            mock.patch.object(pr_maintenance, "comment_issue") as comment,
            mock.patch.object(pr_maintenance, "github_request") as request,
            mock.patch.object(pr_maintenance, "checkout_pr_branch") as checkout,
        ):
            pr_maintenance.apply_pr_update("owner/repo", "token", event)

        request.assert_not_called()
        checkout.assert_not_called()
        self.assertIn("贡献者或仓库维护者", comment.call_args.args[-1])

    def test_bot_is_not_authorized_even_if_listed_as_contributor(self) -> None:
        event = self.event("github-actions[bot]", "MEMBER")
        self.assertFalse(pr_maintenance.comment_is_authorized(event))

    def test_outdated_reporter_is_authorized(self) -> None:
        event = self.event("reporter")
        event["issue"]["body"] = "\n".join([
            "## Outdated Translation Report",
            "",
            "- Reporter: @reporter",
            "- Current schema file: `files/123/UserGameStatsSchema_123.bin`",
            "- Current SHA-256: `abc`",
            "- Last library update: 2026-01-01T00:00:00Z",
        ])

        self.assertTrue(pr_maintenance.comment_is_authorized(event))
        metadata = pr_maintenance.parse_pr_metadata(event["issue"])
        self.assertEqual("files/123/UserGameStatsSchema_123.bin", metadata["schema_file"])
        self.assertEqual("abc", metadata["sha256"])
        self.assertEqual("2026-01-01T00:00:00Z", metadata["updated_at"])

    def test_pr_body_preserves_machine_readable_variant_metadata(self) -> None:
        records = [
            {
                "variant_id": "default",
                "primary": True,
                "schema_file": "files/123/UserGameStatsSchema_123.bin",
                "note_zh": "原版",
                "note_en": "Original",
                "file_size_bytes": 10,
                "sha256": "a" * 64,
                "achievement_count": 1,
            },
            {
                "variant_id": "beta",
                "primary": False,
                "schema_file": "files/123/beta/UserGameStatsSchema_123.bin",
                "note_zh": "测试版",
                "note_en": "Beta",
                "file_size_bytes": 11,
                "sha256": "b" * 64,
                "achievement_count": 1,
            },
        ]
        entry = {
            "game_name": "Game",
            "game_id": "123",
            "store_url": "https://store.steampowered.com/app/123/",
            "languages": ["schinese"],
            "schema_file": records[0]["schema_file"],
            "schema_files": records,
            "file_size_bytes": 10,
            "achievement_count": 1,
            "sha256": records[0]["sha256"],
            "contributors": ["contributor"],
            "submitted_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        rows = [{"api_name": "ACH", "schinese_name": "名称", "schinese_description": "描述"}]

        body = bot.build_submission_pr_body(
            kind="translation-contribution",
            entry=entry,
            coverage={"schinese": 1},
            rows=rows,
            languages=["schinese"],
        )
        metadata = pr_maintenance.parse_pr_metadata({"body": body, "labels": []})

        self.assertEqual(records, metadata["schema_files"])
        self.assertIn("## Schema Variants", body)

    def test_merged_translation_notifies_and_closes_matching_petitions(self) -> None:
        body = "\n".join([
            "## Translation Library Submission",
            "",
            "- Game name: Example Game",
            "- Steam app ID: `123`",
            "- Contributors: @contributor",
            "- Schema file: `files/123/UserGameStatsSchema_123.bin`",
        ])
        pr = {"body": body, "labels": [{"name": "翻译投稿"}]}
        matching = {
            "number": 90,
            "labels": [{"name": "翻译请愿"}],
            "body": "### Steam app ID\n\n123\n",
        }
        unrelated = {
            "number": 91,
            "labels": [{"name": "翻译请愿"}],
            "body": "### Steam app ID\n\n456\n",
        }
        with (
            mock.patch.object(pr_maintenance, "open_translation_petitions", return_value=[matching, unrelated]),
            mock.patch.object(pr_maintenance, "comment_issue_once") as comment_once,
            mock.patch.object(pr_maintenance, "close_issue") as close,
        ):
            notified = pr_maintenance.notify_fulfilled_translation_petitions(pr, "owner/repo", "token")

        self.assertEqual(1, notified)
        self.assertEqual(90, comment_once.call_args.args[2])
        self.assertIn("@contributor", comment_once.call_args.args[3])
        self.assertIn("现在可以下载了", comment_once.call_args.args[3])
        close.assert_called_once_with("owner/repo", "token", 90)

    def test_pr_finalization_runs_petition_notification(self) -> None:
        pr = {"number": 34, "body": "", "labels": []}
        event = {"pull_request": pr}
        with (
            mock.patch.object(pr_maintenance, "comment_issue_once"),
            mock.patch.object(pr_maintenance, "notify_fulfilled_translation_petitions") as notify,
            mock.patch.object(pr_maintenance, "delete_pr_branch"),
            mock.patch.object(pr_maintenance, "lock_issue"),
        ):
            pr_maintenance.finalize_merged_pr(event, "owner/repo", "token")

        notify.assert_called_once_with(pr, "owner/repo", "token")

    def test_legacy_multi_version_pr_updates_primary_variant_metadata(self) -> None:
        existing = {
            "game_id": "123",
            "schema_file": "files/123/UserGameStatsSchema_123.bin",
            "schema_files": [
                {
                    "variant_id": "default",
                    "primary": True,
                    "schema_file": "files/123/UserGameStatsSchema_123.bin",
                    "note_zh": "原版",
                    "note_en": "Original",
                    "file_size_bytes": 10,
                    "sha256": "a" * 64,
                    "achievement_count": 1,
                },
                {
                    "variant_id": "beta",
                    "primary": False,
                    "schema_file": "files/123/beta/UserGameStatsSchema_123.bin",
                    "note_zh": "测试版",
                    "note_en": "Beta",
                    "file_size_bytes": 11,
                    "sha256": "b" * 64,
                    "achievement_count": 1,
                },
            ],
        }
        meta = {
            "game_id": "123",
            "game_name": "Game",
            "store_url": "https://store.steampowered.com/app/123/",
            "languages": ["schinese"],
            "schema_file": existing["schema_file"],
            "schema_files": None,
            "achievement_count": "2",
            "sha256": "c" * 64,
            "source_issue": "",
            "contributors": ["contributor"],
            "submitted_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
        with (
            mock.patch.object(pr_maintenance, "load_index", return_value={"entries": [existing]}),
            mock.patch.object(pr_maintenance, "schema_file_size_bytes", return_value=12),
        ):
            entry = pr_maintenance.entry_from_metadata(meta)

        primary, beta = entry["schema_files"]
        self.assertEqual("c" * 64, primary["sha256"])
        self.assertEqual(2, primary["achievement_count"])
        self.assertEqual("b" * 64, beta["sha256"])

    def test_invalid_outdated_command_does_not_checkout_branch(self) -> None:
        event = self.event("reporter")
        event["comment"]["body"] = "/update doc"
        event["issue"]["body"] = "\n".join([
            "## Outdated Translation Report",
            "",
            "- Reporter: @reporter",
            "- Steam app ID: `123`",
        ])
        pr = dict(event["issue"], state="open")
        with (
            mock.patch.object(pr_maintenance, "github_request", return_value=pr),
            mock.patch.object(pr_maintenance, "checkout_pr_branch") as checkout,
            mock.patch.object(pr_maintenance, "comment_issue") as comment,
        ):
            pr_maintenance.apply_pr_update("owner/repo", "token", event)

        checkout.assert_not_called()
        self.assertIn("报告过期 PR 仅支持", comment.call_args.args[-1])

    def test_outdated_pr_rejects_file_and_id_mutations(self) -> None:
        allowed = pr_maintenance.UPDATE_COMMANDS_BY_KIND["outdated"]
        self.assertNotIn("doc", allowed)
        self.assertNotIn("id", allowed)
        self.assertEqual({"name", "store", "reason", "reference"}, allowed)

    def test_pr_revalidation_rejects_schema_without_achievements(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "empty.bin"
            path.write_bytes(b"\x08")
            relative = path.relative_to(ROOT).as_posix()

            with self.assertRaisesRegex(ValueError, "没有找到 Steam 成就"):
                pr_maintenance.validate_languages_for_schema(relative, ["schinese"])

    def test_app_id_change_renames_every_schema_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "files/123/UserGameStatsSchema_123.bin"
            beta = root / "files/123/beta/UserGameStatsSchema_123.bin"
            primary.parent.mkdir(parents=True)
            beta.parent.mkdir(parents=True)
            primary.write_bytes(b"primary")
            beta.write_bytes(b"beta")
            meta = {
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
                        "primary": False,
                        "schema_file": "files/123/beta/UserGameStatsSchema_123.bin",
                        "note_zh": "测试版",
                        "note_en": "Beta",
                    },
                ],
            }
            with (
                mock.patch.object(bot, "REPO_ROOT", root),
                mock.patch.object(bot, "FILES_ROOT", root / "files"),
                mock.patch.object(pr_maintenance, "ROOT", root),
                mock.patch.object(pr_maintenance, "FILES_ROOT", root / "files"),
            ):
                schema_file, records = pr_maintenance.rename_schema_variants("123", "456", meta)

            self.assertEqual("files/456/UserGameStatsSchema_456.bin", schema_file)
            self.assertIsNotNone(records)
            self.assertEqual(b"primary", (root / schema_file).read_bytes())
            self.assertEqual(b"beta", (root / "files/456/beta/UserGameStatsSchema_456.bin").read_bytes())
            self.assertFalse((root / "files/123").exists())


if __name__ == "__main__":
    unittest.main()
