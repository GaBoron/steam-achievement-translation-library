from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import github_issue_guard as issue_guard  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
