#!/usr/bin/env python3
"""Maintenance helper for translation-library pull requests."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.json"


def main() -> None:
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    data["entries"] = sorted(data.get("entries", []), key=lambda e: (str(e.get("game_name", "")).casefold(), str(e.get("game_id", ""))))
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
