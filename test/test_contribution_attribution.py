import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow-scripts"))
from contribution_attribution import github_commit_author, merge_commit_body


def user(login, user_id):
    return {"login": login, "id": user_id, "type": "User"}


class ContributionAttributionTests(unittest.TestCase):
    def test_only_usable_github_user_accounts_produce_a_git_author(self):
        self.assertEqual(
            github_commit_author(user("Game-Translator", 42)),
            "Game-Translator <42+Game-Translator@users.noreply.github.com>",
        )
        invalid_accounts = (None, user("line\nbreak", 42), user("Translator", 0),
                            user("ghost", 10137), {**user("robot", 42), "type": "Bot"})
        for invalid in invalid_accounts:
            with self.subTest(account=invalid):
                self.assertEqual(github_commit_author(invalid), "")

    @patch("contribution_attribution.github_request")
    def test_merge_uses_the_source_issue_and_actual_content_authors(self, request):
        event = {
            "pull_request": {
                "number": 12,
                "head": {"ref": "translation-library/update-11"},
                "body": "- Contributors: @PriorAuthor\nCloses #99",
            },
            "review": {"user": {"login": "Maintainer"}},
        }
        request.side_effect = [
            {"user": user("OriginalAuthor", 42)},
            [
                {"author": user("originalauthor", 42), "parents": [{}]},
                {"author": user("RevisionAuthor", 43), "parents": [{}]},
                {"author": user("SyncAuthor", 44), "parents": [{}, {}]},
                {"author": None, "parents": [{}]},
            ],
        ]
        self.assertEqual(
            merge_commit_body("owner/library", "example", event),
            "Automatically merged after approval by @Maintainer.\n\n"
            "Co-authored-by: OriginalAuthor <42+OriginalAuthor@users.noreply.github.com>\n"
            "Co-authored-by: RevisionAuthor <43+RevisionAuthor@users.noreply.github.com>",
        )
        self.assertEqual(request.call_args_list, [
            call("GET", "owner/library", "example", "/issues/11", allow_404=True),
            call("GET", "owner/library", "example", "/pulls/12/commits?per_page=100&page=1"),
        ])
