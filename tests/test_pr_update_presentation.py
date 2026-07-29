from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import pr_comment_workflow  # noqa: E402


class PullRequestUpdatePresentationTests(unittest.TestCase):
    def test_pr_update_preserves_contributor_notes(self) -> None:
        notes = "#### 翻译思路\n- 使用官方术语\n\n#### 翻译来源\n- 人工校对"
        pr = {
            "number": 34,
            "state": "open",
            "labels": [{"name": "翻译投稿"}],
            "body": "\n".join([
                "## Translation Library Submission",
                "",
                "- Game name: Example Game",
                "- Steam app ID: `123`",
                "- Steam store URL: https://store.steampowered.com/app/123/",
                "- Contributors: @translator",
                "- Source issue: https://github.com/owner/repo/issues/12",
                "- Supported languages: schinese",
                "- Achievement count: 1",
                "- Schema file: `files/123/UserGameStatsSchema_123.bin`",
                "- File size: 1 KB",
                "- SHA-256: `abc`",
                "- Submitted at: 2026-01-01T00:00:00Z",
                "- Updated at: 2026-01-01T00:00:00Z",
                "",
                "## Contributor Notes",
                "",
                notes,
                "",
                "## Language Coverage",
                "",
                "- `schinese`: 1/1 achievements",
            ]),
        }
        event = {
            "issue": {"number": 34, "body": pr["body"], "labels": pr["labels"]},
            "comment": {
                "body": "/update name Renamed Game",
                "author_association": "MEMBER",
                "user": {"login": "maintainer"},
            },
        }
        entry = {
            "game_id": "123",
            "game_name": "Renamed Game",
            "store_url": "https://store.steampowered.com/app/123/",
            "contributors": ["translator"],
            "schema_file": "files/123/UserGameStatsSchema_123.bin",
            "achievement_count": 1,
            "sha256": "abc",
        }
        rows = [{"api_name": "ACH", "schinese_name": "名称", "schinese_description": "描述"}]

        with (
            mock.patch.object(pr_comment_workflow, "github_request", return_value=pr),
            mock.patch.object(pr_comment_workflow, "checkout_pr_branch", return_value="translation-library/issue-12"),
            mock.patch.object(pr_comment_workflow, "validate_metadata_variants", return_value=(rows, {"schinese": 1})),
            mock.patch.object(pr_comment_workflow, "validate_store_url"),
            mock.patch.object(pr_comment_workflow, "entry_from_metadata", return_value=entry),
            mock.patch.object(pr_comment_workflow, "variant_achievement_rows", return_value={"default": rows}),
            mock.patch.object(pr_comment_workflow, "build_submission_pr_body", return_value="rebuilt") as build_body,
            mock.patch.object(pr_comment_workflow, "commit_and_push", return_value=False),
            mock.patch.object(pr_comment_workflow, "update_pr_title_and_body"),
            mock.patch.object(pr_comment_workflow, "comment_issue"),
        ):
            pr_comment_workflow.apply_pr_update("owner/repo", "token", event)

        self.assertEqual(notes, build_body.call_args.kwargs["contributor_notes"])


if __name__ == "__main__":
    unittest.main()
