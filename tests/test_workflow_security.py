import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowSecurityTests(unittest.TestCase):
    def test_statistics_updates_use_repository_scoped_app_credentials(self) -> None:
        statistics = (ROOT / ".github" / "workflows" / "statistics-svg.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("id: statistics-token", statistics)
        self.assertIn("app-id: ${{ secrets.SATL_PR_BOT_APP_ID }}", statistics)
        self.assertIn("private-key: ${{ secrets.SATL_PR_BOT_PRIVATE_KEY }}", statistics)
        self.assertIn("repositories: steam-achievement-translation-library", statistics)
        self.assertIn("token: ${{ steps.statistics-token.outputs.token }}", statistics)

    def test_finalizers_use_repository_scoped_app_credentials(self) -> None:
        contribution = (ROOT / ".github" / "workflows" / "translation-contribution.yml").read_text(
            encoding="utf-8"
        )
        watchdog = (ROOT / ".github" / "workflows" / "translation-finalizer-watchdog.yml").read_text(
            encoding="utf-8"
        )

        self.assertGreaterEqual(contribution.count("id: finalizer-token"), 2)
        self.assertGreaterEqual(contribution.count("token: ${{ steps.finalizer-token.outputs.token }}"), 2)
        self.assertIn("id: finalizer-token", watchdog)
        self.assertIn("token: ${{ steps.finalizer-token.outputs.token }}", watchdog)

    def test_merge_remains_ruleset_gated_and_waits_before_finalizing(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "translation-contribution.yml").read_text(
            encoding="utf-8"
        )

        merge_start = workflow.index("      - name: Merge approved PR")
        wait_start = workflow.index("      - name: Wait for automatic merge", merge_start)
        finalizer_token_start = workflow.index("      - name: Generate short-lived finalizer token", wait_start)
        merge_block = workflow[merge_start:wait_start]
        wait_block = workflow[wait_start:finalizer_token_start]

        self.assertIn("GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}", merge_block)
        self.assertNotIn("steps.finalizer-token.outputs.token", merge_block)
        self.assertIn('MERGED="$(gh api', wait_block)
        self.assertIn("sleep 10", wait_block)

    def test_translation_petitions_use_their_own_validation_job(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "translation-contribution.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("translation-petition-review:", workflow)
        self.assertIn("workflow-scripts/translation_petition_bot.py", workflow)
        issue_review = workflow[workflow.index("  issue-review:"):workflow.index("  translation-petition-review:")]
        self.assertIn("!contains(github.event.issue.labels.*.name, '翻译请愿')", issue_review)
        petition_job = workflow[workflow.index("  translation-petition-review:"):workflow.index("  pr-review-requested-changes:")]
        self.assertIn("contains(github.event.issue.body, '### 需要翻译的成就 schema ZIP')", petition_job)
        self.assertLess(
            petition_job.index("workflow-scripts/github_issue_guard.py"),
            petition_job.index("workflow-scripts/translation_petition_bot.py"),
        )


if __name__ == "__main__":
    unittest.main()
