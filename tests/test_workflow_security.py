import ast
import builtins
import symtable
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowSecurityTests(unittest.TestCase):
    def test_workflow_modules_have_no_unresolved_global_dependencies(self) -> None:
        unresolved: dict[str, list[str]] = {}
        for path in sorted((ROOT / "workflow-scripts").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            module_bindings = set(dir(builtins))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    module_bindings.add(node.name)
                elif isinstance(node, ast.Import):
                    module_bindings.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module_bindings.update(alias.asname or alias.name for alias in node.names)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        module_bindings.update(
                            child.id for child in ast.walk(target) if isinstance(child, ast.Name)
                        )

            missing: set[str] = set()

            def inspect_scope(scope: symtable.SymbolTable) -> None:
                if scope.get_type() != "module":
                    missing.update(
                        symbol.get_name()
                        for symbol in scope.get_symbols()
                        if symbol.is_referenced()
                        and symbol.is_global()
                        and symbol.get_name() not in module_bindings
                    )
                for child in scope.get_children():
                    inspect_scope(child)

            inspect_scope(symtable.symtable(source, str(path), "exec"))
            if missing:
                unresolved[path.relative_to(ROOT).as_posix()] = sorted(missing)

        self.assertEqual({}, unresolved)

    def test_python_modules_stay_below_modular_size_limit(self) -> None:
        python_files = [
            *sorted((ROOT / "workflow-scripts").glob("*.py")),
            *sorted((ROOT / "tests").glob("*.py")),
        ]
        oversized = {
            path.relative_to(ROOT).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
            for path in python_files
            if len(path.read_text(encoding="utf-8").splitlines()) > 600
        }

        self.assertEqual({}, oversized)

    def test_repository_checks_do_not_cancel_in_progress_runs(self) -> None:
        repository_checks = (
            ROOT / ".github" / "workflows" / "repository-checks.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("group: repository-checks-${{ github.ref }}", repository_checks)
        self.assertIn("cancel-in-progress: false", repository_checks)
        self.assertIn("--allow-unindexed-schema-files", repository_checks)
        self.assertIn("--allow-stale-index-metadata", repository_checks)
        self.assertIn("ALLOW_STALE_HUMAN_INDEXES", repository_checks)
        self.assertIn("--allow-stale-human-indexes", repository_checks)

    def test_direct_index_edits_regenerate_indexes_and_delete_removed_entry_files(self) -> None:
        repository_checks = (
            ROOT / ".github" / "workflows" / "repository-checks.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("id: index-maintenance-token", repository_checks)
        self.assertIn("workflow-scripts/index_maintenance.py", repository_checks)
        self.assertIn('git add -A -- index.json INDEX.md INDEX_EN.md files', repository_checks)
        self.assertIn('git push origin HEAD:main', repository_checks)

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

    def test_error_report_prs_use_isolated_review_artifacts(self) -> None:
        contribution = (ROOT / ".github" / "workflows" / "translation-contribution.yml").read_text(
            encoding="utf-8"
        )
        report_directory_anchor = ROOT / ".github" / "translation-reports" / ".gitkeep"

        self.assertIn(".github/translation-reports/**", contribution)
        self.assertTrue(
            report_directory_anchor.is_file(),
            "The optional report path must exist so translation-only PR creation can stage it safely.",
        )

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
        self.assertIn('gh pr merge "$PR_NUMBER" --auto --merge', merge_block)
        self.assertNotIn("--squash", merge_block)
        self.assertIn('MERGED="$(gh api', wait_block)
        self.assertIn('gh pr checks "$PR_NUMBER" --required', wait_block)
        self.assertIn("Required checks failed", wait_block)
        self.assertIn("sleep 10", wait_block)

    def test_translation_petitions_use_their_own_validation_job(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "translation-contribution.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("translation-petition-review:", workflow)
        self.assertIn("workflow-scripts/translation_petition_bot.py", workflow)
        issue_review = workflow[workflow.index("  issue-review:"):workflow.index("  translation-petition-review:")]
        self.assertIn("contains(github.event.issue.labels.*.name, '翻译投稿')", issue_review)
        self.assertIn("contains(github.event.issue.labels.*.name, '更新文件')", issue_review)
        self.assertIn("contains(github.event.issue.labels.*.name, '报告错误')", issue_review)
        self.assertIn("contains(github.event.issue.body, '### 成就 schema ZIP')", issue_review)
        self.assertIn("contains(github.event.issue.body, '### Uploaded achievement schema ZIP')", issue_review)
        self.assertNotIn("contains(github.event.issue.body, '### Achievement schema ZIP')", issue_review)
        self.assertIn("contains(github.event.issue.body, '### 错误类型')", issue_review)
        self.assertIn("contains(github.event.issue.body, '### Issue type')", issue_review)
        self.assertNotIn("contains(github.event.issue.labels.*.name, '自动化错误')", issue_review)
        self.assertNotIn("contains(github.event.issue.labels.*.name, '翻译请愿')", issue_review)
        self.assertNotIn("contains(github.event.issue.body, '### 需要翻译的成就 schema ZIP')", issue_review)
        self.assertNotIn("contains(github.event.issue.body, '### Achievement schema ZIP to translate')", issue_review)
        petition_job = workflow[workflow.index("  translation-petition-review:"):workflow.index("  pr-review-requested-changes:")]
        self.assertIn("contains(github.event.issue.body, '### 需要翻译的成就 schema ZIP')", petition_job)
        self.assertLess(
            petition_job.index("workflow-scripts/github_issue_guard.py"),
            petition_job.index("workflow-scripts/translation_petition_bot.py"),
        )

    def test_issue_templates_do_not_request_derived_metadata(self) -> None:
        template_root = ROOT / ".github" / "ISSUE_TEMPLATE"
        all_templates = [
            "translation_contribution_zh.yml",
            "translation_contribution_en.yml",
            "translation_update_zh.yml",
            "translation_update_en.yml",
            "translation_petition_zh.yml",
            "translation_petition_en.yml",
            "outdated_report_zh.yml",
            "outdated_report_en.yml",
        ]
        for filename in all_templates:
            with self.subTest(filename=filename):
                text = (template_root / filename).read_text(encoding="utf-8")
                self.assertNotIn("id: store_url", text)
        for filename in all_templates[:4]:
            with self.subTest(filename=filename):
                text = (template_root / filename).read_text(encoding="utf-8")
                self.assertNotIn("id: languages", text)

    def test_force_refresh_reuses_issue_review_and_app_authenticated_pr_pushes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "translation-contribution.yml").read_text(
            encoding="utf-8"
        )

        issue_review = workflow[workflow.index("  issue-review:"):workflow.index("  translation-petition-review:")]
        petition_job = workflow[workflow.index("  translation-petition-review:"):workflow.index("  pr-review-requested-changes:")]
        pr_comments = workflow[workflow.index("  pr-comment-maintenance:"):workflow.index("  issue-comment-maintenance:")]
        self.assertIn("github.event.comment.body == '/force-refresh'", issue_review)
        self.assertIn("github.event.comment.body == '/force-refresh'", petition_job)
        self.assertIn("id: pr-bot-token", pr_comments)
        self.assertIn("token: ${{ steps.pr-bot-token.outputs.token }}", pr_comments)


if __name__ == "__main__":
    unittest.main()
