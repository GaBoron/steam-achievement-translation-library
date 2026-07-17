from __future__ import annotations

import argparse
import html
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX_PATH = ROOT / "index.json"
DEFAULT_OUTPUT_PATH = ROOT / "docs" / "statistics" / "library-statistics.svg"


@dataclass(frozen=True)
class Statistics:
    daily_totals: tuple[tuple[date, int], ...]
    top_contributors: tuple[tuple[str, int], ...]

    @property
    def latest_total(self) -> int:
        return self.daily_totals[-1][1]


def parse_submitted_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("submitted_at must be a non-empty ISO 8601 string")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid submitted_at value: {value!r}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_statistics(index_data: dict[str, Any], contributor_limit: int = 10) -> Statistics:
    entries = index_data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("index.json must contain a non-empty entries array")
    if contributor_limit < 1:
        raise ValueError("contributor_limit must be at least 1")

    first_submission_by_game: dict[str, date] = {}
    contribution_counts: Counter[str] = Counter()

    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"entry {position} must be an object")

        game_id = entry.get("game_id")
        if not isinstance(game_id, str) or not game_id.strip():
            raise ValueError(f"entry {position} has an invalid game_id")

        submitted_on = parse_submitted_at(entry.get("submitted_at")).date()
        previous = first_submission_by_game.get(game_id)
        if previous is None or submitted_on < previous:
            first_submission_by_game[game_id] = submitted_on

        contributor_id = entry.get("contributor_id")
        if not isinstance(contributor_id, str) or not contributor_id.strip():
            raise ValueError(f"entry {position} has an invalid contributor_id")
        contribution_counts[contributor_id.strip()] += 1

    submissions_per_day = Counter(first_submission_by_game.values())
    first_day = min(submissions_per_day)
    last_day = max(submissions_per_day)
    running_total = 0
    daily_totals: list[tuple[date, int]] = []
    current_day = first_day
    while current_day <= last_day:
        running_total += submissions_per_day[current_day]
        daily_totals.append((current_day, running_total))
        current_day += timedelta(days=1)

    ranked_contributors = sorted(
        contribution_counts.items(),
        key=lambda item: (-item[1], item[0].casefold(), item[0]),
    )[:contributor_limit]

    return Statistics(tuple(daily_totals), tuple(ranked_contributors))


def nice_axis_max(value: int) -> int:
    if value <= 0:
        return 1
    exponent = math.floor(math.log10(value))
    magnitude = 10**exponent
    fraction = value / magnitude
    if fraction <= 1:
        nice_fraction = 1
    elif fraction <= 2:
        nice_fraction = 2
    elif fraction <= 2.5:
        nice_fraction = 2.5
    elif fraction <= 5:
        nice_fraction = 5
    else:
        nice_fraction = 10
    return max(5, int(nice_fraction * magnitude))


def evenly_spaced_indices(length: int, count: int) -> tuple[int, ...]:
    if length <= count:
        return tuple(range(length))
    indices = {round(step * (length - 1) / (count - 1)) for step in range(count)}
    return tuple(sorted(indices))


def svg_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def path_from_points(points: list[tuple[float, float]], close: bool = False) -> str:
    if not points:
        return ""
    commands = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    commands.extend(f"L {x:.1f} {y:.1f}" for x, y in points[1:])
    if close:
        commands.append("Z")
    return " ".join(commands)


def render_svg(statistics: Statistics) -> str:
    width = 1440
    height = 760

    plot_left = 108.0
    plot_right = 682.0
    plot_top = 180.0
    plot_bottom = 650.0
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    axis_max = nice_axis_max(statistics.latest_total)
    trend_points: list[tuple[float, float]] = []
    trend_count = len(statistics.daily_totals)
    for index, (_, total) in enumerate(statistics.daily_totals):
        x = plot_left if trend_count == 1 else plot_left + (index / (trend_count - 1)) * plot_width
        y = plot_bottom - (total / axis_max) * plot_height
        trend_points.append((x, y))

    area_points = [(plot_left, plot_bottom), *trend_points, (plot_right, plot_bottom)]
    latest_x, latest_y = trend_points[-1]

    svg: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "  <title id=\"title\">Steam 成就翻译库收录统计</title>",
        (
            "  <desc id=\"desc\">左侧为累计收录游戏数量趋势折线图，"
            "右侧为贡献者贡献量前十名横向条形图。</desc>"
        ),
        "  <defs>",
        "    <filter id=\"paper\" x=\"-5%\" y=\"-5%\" width=\"110%\" height=\"110%\">",
        "      <feTurbulence type=\"fractalNoise\" baseFrequency=\"0.72\" numOctaves=\"3\" seed=\"17\" result=\"noise\"/>",
        "      <feColorMatrix in=\"noise\" type=\"matrix\" values=\"0 0 0 0 0.84 0 0 0 0 0.80 0 0 0 0 0.70 0 0 0 0.10 0\" result=\"grain\"/>",
        "      <feBlend in=\"SourceGraphic\" in2=\"grain\" mode=\"multiply\"/>",
        "    </filter>",
        "    <filter id=\"roughen\" x=\"-4%\" y=\"-4%\" width=\"108%\" height=\"108%\">",
        "      <feTurbulence type=\"fractalNoise\" baseFrequency=\"0.018 0.085\" numOctaves=\"1\" seed=\"9\" result=\"noise\"/>",
        "      <feDisplacementMap in=\"SourceGraphic\" in2=\"noise\" scale=\"2.1\" xChannelSelector=\"R\" yChannelSelector=\"G\"/>",
        "    </filter>",
        "    <pattern id=\"blue-hatch\" width=\"10\" height=\"10\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(12)\">",
        "      <rect width=\"10\" height=\"10\" fill=\"#cfe8f8\"/>",
        "      <path d=\"M 1 10 L 7 0 M 7 10 L 13 0\" stroke=\"#6baed6\" stroke-width=\"1.5\" opacity=\"0.72\"/>",
        "    </pattern>",
        "    <pattern id=\"mint-hatch\" width=\"10\" height=\"10\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(12)\">",
        "      <rect width=\"10\" height=\"10\" fill=\"#d8f0e2\"/>",
        "      <path d=\"M 1 10 L 7 0 M 7 10 L 13 0\" stroke=\"#70b995\" stroke-width=\"1.5\" opacity=\"0.72\"/>",
        "    </pattern>",
        "    <pattern id=\"peach-hatch\" width=\"10\" height=\"10\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(12)\">",
        "      <rect width=\"10\" height=\"10\" fill=\"#ffe2bd\"/>",
        "      <path d=\"M 1 10 L 7 0 M 7 10 L 13 0\" stroke=\"#e9a947\" stroke-width=\"1.5\" opacity=\"0.72\"/>",
        "    </pattern>",
        "    <pattern id=\"lilac-hatch\" width=\"10\" height=\"10\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(12)\">",
        "      <rect width=\"10\" height=\"10\" fill=\"#e8dcf5\"/>",
        "      <path d=\"M 1 10 L 7 0 M 7 10 L 13 0\" stroke=\"#a98ac8\" stroke-width=\"1.5\" opacity=\"0.72\"/>",
        "    </pattern>",
        "    <pattern id=\"rose-hatch\" width=\"10\" height=\"10\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(12)\">",
        "      <rect width=\"10\" height=\"10\" fill=\"#f9d8df\"/>",
        "      <path d=\"M 1 10 L 7 0 M 7 10 L 13 0\" stroke=\"#d88095\" stroke-width=\"1.5\" opacity=\"0.72\"/>",
        "    </pattern>",
        "    <pattern id=\"sand-hatch\" width=\"10\" height=\"10\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(12)\">",
        "      <rect width=\"10\" height=\"10\" fill=\"#eee8d6\"/>",
        "      <path d=\"M 1 10 L 7 0 M 7 10 L 13 0\" stroke=\"#aaa184\" stroke-width=\"1.5\" opacity=\"0.72\"/>",
        "    </pattern>",
        "    <style>",
        "      .hand { font-family: 'Segoe Print', 'Comic Sans MS', 'Microsoft YaHei', 'Noto Sans SC', sans-serif; fill: #242424; }",
        "      .title { font-size: 34px; font-weight: 700; letter-spacing: 1px; }",
        "      .label { font-size: 20px; font-weight: 600; }",
        "      .small { font-size: 17px; }",
        "      .ink { fill: none; stroke: #252525; stroke-linecap: round; stroke-linejoin: round; }",
        "    </style>",
        "  </defs>",
        "  <rect width=\"1440\" height=\"760\" fill=\"#fbf7ec\" filter=\"url(#paper)\"/>",
        "  <g filter=\"url(#roughen)\">",
        "    <path d=\"M 54 25 C 36 36 31 61 32 96 L 38 681 C 38 716 55 733 87 735 L 675 731 C 699 730 710 711 710 679 L 704 75 C 703 43 686 27 654 27 Z\" fill=\"#fffdf7\" fill-opacity=\"0.82\" stroke=\"#262626\" stroke-width=\"4\"/>",
        "    <path d=\"M 757 28 C 738 42 733 63 734 96 L 739 682 C 740 716 758 733 789 734 L 1380 730 C 1403 728 1411 709 1409 678 L 1404 75 C 1402 45 1384 28 1354 29 Z\" fill=\"#fffdf7\" fill-opacity=\"0.82\" stroke=\"#262626\" stroke-width=\"4\"/>",
        "  </g>",
        "  <g class=\"ink\" stroke-width=\"3\" filter=\"url(#roughen)\">",
        "    <rect x=\"70\" y=\"56\" width=\"58\" height=\"50\" rx=\"3\"/>",
        "    <path d=\"M 80 94 L 92 79 L 103 88 L 119 66 M 112 66 L 120 65 L 119 74\"/>",
        "    <path d=\"M 82 100 L 120 100\" stroke-width=\"1.5\"/>",
        "  </g>",
        "  <text x=\"150\" y=\"94\" class=\"hand title\">收录游戏数量趋势</text>",
        "  <path d=\"M 660 54 L 665 66 L 678 67 L 668 75 L 671 88 L 660 81 L 649 88 L 652 75 L 642 67 L 655 66 Z\" fill=\"#d9edf9\" stroke=\"#2b80bd\" stroke-width=\"3\" stroke-linejoin=\"round\" filter=\"url(#roughen)\"/>",
        "  <g class=\"ink\" stroke-width=\"3\" filter=\"url(#roughen)\">",
        "    <path d=\"M 775 64 L 787 82 L 804 69 L 817 83 L 829 63 L 824 99 L 785 99 Z\"/>",
        "    <circle cx=\"774\" cy=\"60\" r=\"3\" fill=\"#fffdf7\"/>",
        "    <circle cx=\"805\" cy=\"63\" r=\"3\" fill=\"#fffdf7\"/>",
        "    <circle cx=\"831\" cy=\"59\" r=\"3\" fill=\"#fffdf7\"/>",
        "    <path d=\"M 787 105 Q 805 110 823 105\"/>",
        "  </g>",
        "  <text x=\"858\" y=\"94\" class=\"hand title\">贡献者贡献量排行</text>",
        "  <g stroke=\"#3588c4\" stroke-width=\"4\" stroke-linecap=\"round\" filter=\"url(#roughen)\">",
        "    <path d=\"M 1360 61 L 1355 78\"/>",
        "    <path d=\"M 1375 60 L 1368 80\"/>",
        "    <path d=\"M 1387 72 L 1377 85\"/>",
        "  </g>",
        "  <text x=\"75\" y=\"151\" class=\"hand label\">数量（款）</text>",
    ]

    tick_count = 5
    for tick in range(tick_count + 1):
        value = round(axis_max * tick / tick_count)
        y = plot_bottom - (tick / tick_count) * plot_height
        if tick > 0:
            svg.append(
                f'  <path d="M {plot_left:.1f} {y:.1f} C 250 {y - 1.2:.1f} 515 {y + 1.0:.1f} {plot_right:.1f} {y:.1f}" '
                'fill="none" stroke="#b8bdba" stroke-width="1.4" stroke-dasharray="6 9" opacity="0.65"/>'
            )
        svg.append(
            f'  <text x="{plot_left - 20:.1f}" y="{y + 7:.1f}" text-anchor="end" class="hand label">{value}</text>'
        )

    svg.extend(
        [
            "  <g class=\"ink\" stroke-width=\"3.2\" filter=\"url(#roughen)\">",
            f"    <path d=\"M {plot_left:.1f} {plot_top - 8:.1f} C {plot_left - 2:.1f} 330 {plot_left + 2:.1f} 510 {plot_left:.1f} {plot_bottom:.1f}\"/>",
            f"    <path d=\"M {plot_left:.1f} {plot_bottom:.1f} C 270 {plot_bottom + 2:.1f} 500 {plot_bottom - 2:.1f} {plot_right + 8:.1f} {plot_bottom:.1f}\"/>",
            f"    <path d=\"M {plot_right + 1:.1f} {plot_bottom - 9:.1f} L {plot_right + 10:.1f} {plot_bottom:.1f} L {plot_right + 1:.1f} {plot_bottom + 9:.1f}\"/>",
            "  </g>",
            f'  <path d="{path_from_points(area_points, close=True)}" fill="#b9dff3" opacity="0.34"/>',
            f'  <path d="{path_from_points(trend_points)}" fill="none" stroke="#6aaed6" stroke-width="8" opacity="0.28" stroke-linecap="round" stroke-linejoin="round" filter="url(#roughen)"/>',
            f'  <path d="{path_from_points(trend_points)}" fill="none" stroke="#242424" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round" filter="url(#roughen)"/>',
        ]
    )

    for x, y in trend_points:
        svg.append(
            f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="5.4" fill="#fffdf7" stroke="#242424" stroke-width="3" filter="url(#roughen)"/>'
        )

    for index in evenly_spaced_indices(trend_count, 5):
        day, _ = statistics.daily_totals[index]
        x, _ = trend_points[index]
        svg.extend(
            [
                f'  <path d="M {x:.1f} {plot_bottom - 6:.1f} L {x:.1f} {plot_bottom + 7:.1f}" stroke="#242424" stroke-width="2.4" stroke-linecap="round" filter="url(#roughen)"/>',
                f'  <text x="{x:.1f}" y="{plot_bottom + 37:.1f}" text-anchor="middle" class="hand small">{day:%m/%d}</text>',
            ]
        )

    annotation_x = 493
    annotation_y = 145
    arrow_target_y = max(plot_top - 4, latest_y - 7)
    svg.extend(
        [
            f'  <text x="{annotation_x}" y="{annotation_y}" class="hand label">最新：{statistics.latest_total} 款</text>',
            f'  <path d="M 620 149 Q 642 151 {latest_x - 13:.1f} {arrow_target_y:.1f}" fill="none" stroke="#242424" stroke-width="2.5" stroke-linecap="round" filter="url(#roughen)"/>',
            f'  <path d="M {latest_x - 21:.1f} {arrow_target_y - 3:.1f} L {latest_x - 12:.1f} {arrow_target_y:.1f} L {latest_x - 16:.1f} {arrow_target_y + 8:.1f}" fill="none" stroke="#242424" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>',
            f'  <path d="M {latest_x - 4:.1f} {latest_y - 19:.1f} L {latest_x - 1:.1f} {latest_y - 29:.1f} M {latest_x + 8:.1f} {latest_y - 16:.1f} L {latest_x + 16:.1f} {latest_y - 24:.1f} M {latest_x + 14:.1f} {latest_y - 7:.1f} L {latest_x + 25:.1f} {latest_y - 8:.1f}" stroke="#e2aa15" stroke-width="3" stroke-linecap="round"/>',
        ]
    )

    bar_left = 1045.0
    bar_max_width = 245.0
    row_start = 157.0
    row_step = 52.0
    bar_height = 32.0
    largest_contribution = statistics.top_contributors[0][1]
    patterns = ("blue-hatch", "mint-hatch", "peach-hatch", "lilac-hatch", "rose-hatch", "sand-hatch")

    svg.append(
        f'  <path d="M {bar_left - 8:.1f} 145 C {bar_left - 10:.1f} 300 {bar_left - 6:.1f} 520 {bar_left - 8:.1f} 684" '
        'fill="none" stroke="#242424" stroke-width="3" stroke-linecap="round" filter="url(#roughen)"/>'
    )

    for rank, (contributor, count) in enumerate(statistics.top_contributors, start=1):
        y = row_start + (rank - 1) * row_step
        bar_width = max(8.0, (count / largest_contribution) * bar_max_width)
        pattern = patterns[(rank - 1) % len(patterns)]
        rank_fill = "#ffe28a" if rank == 1 else "#fffdf7"
        name_size = 20 if len(contributor) <= 16 else 17
        svg.extend(
            [
                f'  <circle cx="774" cy="{y + bar_height / 2:.1f}" r="16" fill="{rank_fill}" stroke="#242424" stroke-width="2.5" filter="url(#roughen)"/>',
                f'  <text x="774" y="{y + bar_height / 2 + 7:.1f}" text-anchor="middle" class="hand label">{rank}</text>',
                f'  <text x="1018" y="{y + bar_height / 2 + 7:.1f}" text-anchor="end" class="hand" font-size="{name_size}px" font-weight="600">{svg_text(contributor)}</text>',
                f'  <rect x="{bar_left:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="3" fill="url(#{pattern})" stroke="#242424" stroke-width="2.5" filter="url(#roughen)"/>',
                f'  <text x="{bar_left + bar_width + 15:.1f}" y="{y + bar_height / 2 + 7:.1f}" class="hand label">{count} 款</text>',
            ]
        )

    svg.extend(
        [
            "  <path d=\"M 1330 680 L 1335 692 L 1348 693 L 1338 701 L 1341 714 L 1330 707 L 1319 714 L 1322 701 L 1312 693 L 1325 692 Z\" fill=\"#ffe28a\" stroke=\"#242424\" stroke-width=\"2.5\" stroke-linejoin=\"round\" filter=\"url(#roughen)\"/>",
            "  <path d=\"M 1247 714 Q 1280 724 1308 696\" fill=\"none\" stroke=\"#456\" stroke-width=\"2\" stroke-dasharray=\"7 7\" stroke-linecap=\"round\"/>",
            "</svg>",
            "",
        ]
    )
    return "\n".join(svg)


def load_index(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the README statistics SVG from index.json.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH, help="Path to index.json.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to the generated SVG.")
    args = parser.parse_args()

    statistics = build_statistics(load_index(args.index))
    changed = write_if_changed(args.output, render_svg(statistics))
    state = "updated" if changed else "already up to date"
    print(
        f"{args.output}: {state} "
        f"({statistics.latest_total} games, {len(statistics.top_contributors)} ranked contributors)."
    )


if __name__ == "__main__":
    main()
