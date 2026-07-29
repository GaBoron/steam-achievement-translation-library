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


class IssueDuplicateCleanupTests(unittest.TestCase):
    @staticmethod
    def issue(
        number: int,
        game_id: str = "123",
        *,
        state: str = "open",
        kind: str = "translation-contribution",
        pull_request: bool = False,
    ) -> dict:
        kind_heading = {
            "translation-contribution": "### 成就 schema ZIP\n\n[file](url)",
            "update": "### 更新内容摘要\n\nupdated",
            "translation-petition": "### 需要翻译的成就 schema ZIP\n\n[file](url)",
            "outdated": "### 过期说明\n\noutdated",
        }[kind]
        issue = {
            "id": 1000 + number,
            "number": number,
            "state": state,
            "body": f"### Steam app ID\n\n{game_id}\n\n{kind_heading}\n",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
        }
        if pull_request:
            issue["pull_request"] = {"url": f"https://api.github.com/repos/owner/repo/pulls/{number}"}
        return issue

    def test_only_older_open_same_kind_same_id_issues_are_duplicates(self) -> None:
        current = self.issue(200)
        matching = self.issue(100)
        issues = [
            matching,
            self.issue(99, state="closed"),
            self.issue(98, game_id="456"),
            self.issue(97, kind="translation-petition"),
            self.issue(96, pull_request=True),
            self.issue(201),
            current,
        ]

        duplicates = issue_guard.older_open_duplicate_issues(current, issues)

        self.assertEqual([100], [issue["number"] for issue in duplicates])

    def test_opened_issue_closes_all_older_open_duplicates(self) -> None:
        current = self.issue(200)
        event = {"action": "opened", "issue": current}
        duplicates = [self.issue(100), self.issue(150)]
        with (
            mock.patch.object(issue_guard, "list_open_issues", return_value=duplicates),
            mock.patch.object(issue_guard, "revalidate_open_duplicate_issue", side_effect=duplicates),
            mock.patch.object(issue_guard, "close_duplicate_issue") as close,
            mock.patch.object(issue_guard, "comment_issue") as comment,
        ):
            closed = issue_guard.close_older_duplicate_issues("owner/repo", "token", event)

        self.assertEqual([100, 150], closed)
        self.assertEqual(
            [
                mock.call("owner/repo", "token", 100, current["id"]),
                mock.call("owner/repo", "token", 150, current["id"]),
            ],
            close.call_args_list,
        )
        self.assertEqual(2, comment.call_count)
        self.assertIn("#200", comment.call_args.args[-1])

    def test_duplicate_that_is_no_longer_open_is_not_closed(self) -> None:
        current = self.issue(200)
        duplicate = self.issue(100)
        with (
            mock.patch.object(issue_guard, "list_open_issues", return_value=[duplicate]),
            mock.patch.object(issue_guard, "revalidate_open_duplicate_issue", return_value=None),
            mock.patch.object(issue_guard, "close_duplicate_issue") as close,
            mock.patch.object(issue_guard, "comment_issue") as comment,
        ):
            closed = issue_guard.close_older_duplicate_issues(
                "owner/repo",
                "token",
                {"action": "opened", "issue": current},
            )

        self.assertEqual([], closed)
        close.assert_not_called()
        comment.assert_not_called()

    def test_revalidation_uses_latest_issue_state(self) -> None:
        current = self.issue(200)
        duplicate = self.issue(100)
        with mock.patch.object(issue_guard, "github_request", return_value=duplicate) as request:
            latest = issue_guard.revalidate_open_duplicate_issue("owner/repo", "token", current, 100)

        self.assertEqual(100, latest["number"])
        request.assert_called_once_with("GET", "owner/repo", "token", "/issues/100")

        duplicate["state"] = "closed"
        with mock.patch.object(issue_guard, "github_request", return_value=duplicate):
            latest = issue_guard.revalidate_open_duplicate_issue("owner/repo", "token", current, 100)

        self.assertIsNone(latest)

    def test_invalid_current_id_does_not_query_open_issues(self) -> None:
        current = self.issue(200, game_id="invalid")
        with mock.patch.object(issue_guard, "list_open_issues") as list_issues:
            closed = issue_guard.close_older_duplicate_issues(
                "owner/repo",
                "token",
                {"action": "opened", "issue": current},
            )

        self.assertEqual([], closed)
        list_issues.assert_not_called()

    def test_edited_or_reopened_issue_never_closes_duplicates(self) -> None:
        for action in ("edited", "reopened"):
            with self.subTest(action=action), mock.patch.object(issue_guard, "list_open_issues") as list_issues:
                closed = issue_guard.close_older_duplicate_issues(
                    "owner/repo",
                    "token",
                    {"action": action, "issue": self.issue(200)},
                )

            self.assertEqual([], closed)
            list_issues.assert_not_called()

    def test_duplicate_close_uses_new_issue_as_canonical(self) -> None:
        with mock.patch.object(issue_guard, "github_request") as request:
            issue_guard.close_duplicate_issue("owner/repo", "token", 100, 1200)

        request.assert_called_once_with(
            "PATCH",
            "owner/repo",
            "token",
            "/issues/100",
            {"state": "closed", "state_reason": "duplicate", "duplicate_issue_id": 1200},
            api_version="2026-03-10",
        )
