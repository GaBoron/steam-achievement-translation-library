from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow-scripts"))

import library_submission_bot as bot  # noqa: E402


def string_node(name: str, value: str) -> bot.Node:
    return bot.Node(1, name, value=value, raw_value=value.encode("utf-8"))


def achievement_node(api_name: str = "ACH_ONE") -> bot.Node:
    return bot.Node(
        0,
        "0",
        children=[
            string_node("name", api_name),
            bot.Node(
                0,
                "display",
                children=[
                    bot.Node(0, "name", children=[string_node("english", "Name"), string_node("schinese", "名称")]),
                    bot.Node(0, "desc", children=[string_node("english", "Description"), string_node("schinese", "描述")]),
                ],
            ),
        ],
    )


def schema_nodes(*achievements: bot.Node) -> list[bot.Node]:
    return [bot.Node(0, "root", children=[bot.Node(0, "bits", children=list(achievements))])]
