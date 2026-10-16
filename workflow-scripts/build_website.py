#!/usr/bin/env python3
"""Build the static GitHub Pages site without changing source data."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from website_build import ROOT, build_site


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site", help="A new or empty output directory")
    parser.add_argument("--refresh-covers", action="store_true", help="Refresh Steam image URLs; retain bundled URLs if Steam is unavailable")
    args = parser.parse_args()
    try:
        target, games, variants, size = build_site(args.output, refresh_covers=args.refresh_covers)
    except (OSError, UnicodeError, ValueError, EOFError, NotImplementedError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Website build failed: {exc}\n")
    print(f"Built {games} games and {variants} variants into {target} ({size:,} bytes).")


if __name__ == "__main__":
    main()
