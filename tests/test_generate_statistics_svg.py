from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import generate_statistics_svg as statistics_svg  # noqa: E402


class StatisticsTests(unittest.TestCase):
    def test_axis_ceiling_does_not_double_just_above_one_hundred(self) -> None:
        self.assertEqual(100, statistics_svg.nice_axis_max(100))
        self.assertEqual(125, statistics_svg.nice_axis_max(101))

    def test_pencil_curve_is_smooth_and_has_no_jagged_line_segments(self) -> None:
        path = statistics_svg.pencil_curve_path(
            [(0.0, 10.0), (10.0, 5.0), (20.0, 2.0)],
            seed=1,
        )

        self.assertTrue(path.startswith("M "))
        self.assertEqual(2, path.count(" C "))
        self.assertNotIn(" L ", path)

    def test_rough_bar_uses_four_gently_curved_sides(self) -> None:
        path = statistics_svg.rough_bar_path(10.0, 20.0, 100.0, 30.0, seed=1)

        self.assertEqual(4, path.count(" Q "))
        self.assertTrue(path.endswith(" Z"))

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
        self.assertIn("@font-face", rendered)
        self.assertIn("data:font/ttf;base64,", rendered)
        self.assertEqual(1, rendered.count('id="trend-line"'))
        self.assertEqual(1, rendered.count('id="vertical-axis-arrow"'))
        self.assertEqual(1, rendered.count('id="latest-value-arrow"'))
        self.assertIn('marker-end="url(#latest-arrowhead)"', rendered)
        self.assertNotIn('fill="#b9dff3"', rendered)
        self.assertEqual(2, rendered.count('class="contributor-bar"'))

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
