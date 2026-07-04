#!/usr/bin/env python3
"""Small guard used by GitHub Actions to ensure translation issues use the correct labels."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else {}
    labels = {label.get("name") for label in (event.get("issue") or {}).get("labels", []) if isinstance(label, dict)}
    if "translation-contribution" not in labels:
        raise SystemExit("This workflow only handles issues labeled translation-contribution.")


if __name__ == "__main__":
    main()
