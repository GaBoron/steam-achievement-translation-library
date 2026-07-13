import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowSecurityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
