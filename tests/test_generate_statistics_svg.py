from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import generate_statistics_svg as statistics_svg  # noqa: E402


class StatisticsTests(unittest.TestCase):
    def test_build_statistics_counts_unique_games_by_first_submission(self) -> None:
        index_data = {
            "entries": [
                {
                    "game_id": "20",
                    "contributor_id": "Beta",
                    "submitted_at": "2026-07-03T23:00:00Z",
                },
                {
                    "game_id": "10",
                    "contributor_id": "Alpha",
                    "submitted_at": "2026-07-01T12:00:00Z",
                },
                {
                    "game_id": "20",
                    "contributor_id": "Alpha",
                    "submitted_at": "2026-07-02T09:00:00Z",
                },
            ]
        }

        result = statistics_svg.build_statistics(index_data)

        self.assertEqual(
            (
                (statistics_svg.date(2026, 7, 1), 1),
                (statistics_svg.date(2026, 7, 2), 2),
            ),
            result.daily_totals,
        )
        self.assertEqual((("Alpha", 2), ("Beta", 1)), result.top_contributors)

    def test_contributor_ties_are_sorted_deterministically(self) -> None:
        index_data = {
            "entries": [
                {
                    "game_id": str(position),
                    "contributor_id": contributor,
                    "submitted_at": "2026-07-01T00:00:00Z",
                }
                for position, contributor in enumerate(("zeta", "Alpha", "beta"), start=1)
            ]
        }

        result = statistics_svg.build_statistics(index_data, contributor_limit=2)

        self.assertEqual((("Alpha", 1), ("beta", 1)), result.top_contributors)

    def test_rendered_svg_is_valid_and_contains_required_labels(self) -> None:
        statistics = statistics_svg.Statistics(
            daily_totals=(
                (statistics_svg.date(2026, 7, 1), 1),
                (statistics_svg.date(2026, 7, 2), 3),
            ),
            top_contributors=(("A&B", 2), ("Contributor", 1)),
        )

        rendered = statistics_svg.render_svg(statistics)
        root = ET.fromstring(rendered)

        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("最新：3 款", rendered)
        self.assertIn("A&amp;B", rendered)
        self.assertIn(">2 款<", rendered)

    def test_write_if_changed_avoids_rewriting_identical_output(self) -> None:
        output = ROOT / "docs" / "statistics" / ".test-statistics-output.svg"
        try:
            self.assertTrue(statistics_svg.write_if_changed(output, "<svg/>\n"))
            first_mtime = output.stat().st_mtime_ns
            self.assertFalse(statistics_svg.write_if_changed(output, "<svg/>\n"))
            self.assertEqual(first_mtime, output.stat().st_mtime_ns)
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
