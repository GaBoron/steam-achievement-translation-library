from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import github_issue_guard as issue_guard  # noqa: E402
import github_repository  # noqa: E402
import library_index  # noqa: E402
import library_submission_bot as bot  # noqa: E402
import pr_comment_workflow  # noqa: E402
import pr_finalization  # noqa: E402
import pr_git  # noqa: E402
import pr_metadata  # noqa: E402
import schema_package  # noqa: E402
import translation_pr_maintenance as pr_maintenance  # noqa: E402
from close_command import close_request_comment, parse_close_command  # noqa: E402


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
                "created_at": "2026-07-16T02:00:00Z",
                "author_association": association,
                "user": {"login": actor},
            },
        }

    def test_close_check_is_a_reason_not_confirmation(self) -> None:
        self.assertEqual(("request", "check", ""), parse_close_command("/close check"))
        self.assertEqual(("confirm", "", ""), parse_close_command("/close confirm"))

    def test_close_requires_a_reason(self) -> None:
        action, reason, error = parse_close_command("/close")

        self.assertEqual("", action)
        self.assertEqual("", reason)
        self.assertIn("必须填写关闭原因", error)

    def test_issue_close_request_only_allows_original_submitter(self) -> None:
        event = self.event("maintainer", "OWNER")
        event["comment"]["body"] = "/close no longer needed"
        with (
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "close_issue") as close,
        ):
            handled = issue_guard.handle_issue_close("owner/repo", "token", event)

        self.assertTrue(handled)
        close.assert_not_called()
        self.assertIn("原投稿者", comment.call_args.args[-1])

    def test_issue_close_request_replies_without_closing(self) -> None:
        event = self.event("contributor")
        event["comment"]["body"] = "/close 已有更完整的投稿"
        with (
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "close_issue") as close,
            mock.patch.object(issue_guard, "lock_issue") as lock,
        ):
            handled = issue_guard.handle_issue_close("owner/repo", "token", event)

        self.assertTrue(handled)
        close.assert_not_called()
        lock.assert_not_called()
        self.assertIn("尚未关闭", comment.call_args.args[-1])
        self.assertIn("/close confirm", comment.call_args.args[-1])

    def test_issue_close_confirmation_must_follow_bot_reply(self) -> None:
        event = self.event("contributor")
        event["comment"].update({"body": "/close confirm", "created_at": "2026-07-16T02:00:00Z"})
        acknowledgement = {
            "id": 101,
            "body": close_request_comment("contributor", "已有更完整的投稿", "issue"),
            "created_at": "2026-07-16T02:00:01Z",
            "user": {"login": "github-actions[bot]"},
        }
        event["comment"]["id"] = 100
        with (
            mock.patch.object(issue_guard, "issue_comments", return_value=[acknowledgement]),
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "close_issue") as close,
        ):
            issue_guard.handle_issue_close("owner/repo", "token", event)

        close.assert_not_called()
        self.assertIn("等待机器人确认回复", comment.call_args.args[-1])

    def test_issue_close_confirmation_without_request_is_rejected(self) -> None:
        event = self.event("contributor")
        event["comment"]["body"] = "/close confirm"
        with (
            mock.patch.object(issue_guard, "issue_comments", return_value=[]),
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "close_issue") as close,
            mock.patch.object(issue_guard, "lock_issue") as lock,
        ):
            issue_guard.handle_issue_close("owner/repo", "token", event)

        close.assert_not_called()
        lock.assert_not_called()
        self.assertIn("请先输入 `/close 关闭原因`", comment.call_args.args[-1])

    def test_issue_close_confirmation_closes_and_locks(self) -> None:
        event = self.event("contributor")
        event["comment"].update({"body": "/close confirm", "created_at": "2026-07-16T02:00:02Z"})
        acknowledgement = {
            "id": 100,
            "body": close_request_comment("contributor", "已有更完整的投稿", "issue"),
            "created_at": "2026-07-16T02:00:01Z",
            "user": {"login": "github-actions[bot]"},
        }
        event["comment"]["id"] = 101
        with (
            mock.patch.object(issue_guard, "issue_comments", return_value=[acknowledgement]),
            mock.patch.object(issue_guard, "comment_issue") as comment,
            mock.patch.object(issue_guard, "close_issue") as close,
            mock.patch.object(issue_guard, "lock_issue") as lock,
        ):
            issue_guard.handle_issue_close("owner/repo", "token", event)

        self.assertIn("已有更完整的投稿", comment.call_args.args[-1])
        close.assert_called_once_with("owner/repo", "token", 12)
        lock.assert_called_once_with("owner/repo", "token", 12)

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

    def test_issue_force_refresh_requires_authorization(self) -> None:
        event = self.event("stranger")
        event["comment"]["body"] = "/force-refresh"
        event["issue"]["labels"] = [{"name": "翻译投稿"}]
        with mock.patch.object(issue_guard, "comment_issue") as comment:
            handled = issue_guard.handle_issue_force_refresh("owner/repo", "token", event)

        self.assertTrue(handled)
        self.assertIn("投稿者或仓库维护者", comment.call_args.args[-1])

    def test_issue_author_can_force_refresh_open_submission(self) -> None:
        event = self.event("contributor")
        event["comment"]["body"] = "/force-refresh"
        event["issue"]["labels"] = [{"name": "翻译投稿"}]
        with mock.patch.object(issue_guard, "comment_issue") as comment:
            handled = issue_guard.handle_issue_force_refresh("owner/repo", "token", event)

        self.assertTrue(handled)
        self.assertIn("重新运行检查与校对流程", comment.call_args.args[-1])

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
