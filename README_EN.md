# Steam Achievement Translation Library

[简体中文](README.md) | English

This repository is the standalone Steam achievement translation data library split from `steam-achievement-localizer-skill`. It no longer hosts the Codex skill runtime, installer, packaging workflow, or usage docs. The default entry point is the Chinese README; this file is an auxiliary English summary.

## Layout

- `files/`: community-submitted `UserGameStatsSchema_<app_id>.bin` files.
- `index.json`: machine-readable index.
- `README.md`: primary Chinese index and project documentation.
- `CONTRIBUTING.md`: primary Chinese contribution guide.
- `workflow-scripts/`: GitHub Actions helpers for submission review and index maintenance.

Paths were flattened from the original `achievement-library/` subtree: `achievement-library/files/` became `files/`, and `achievement-library/index.json` became `index.json`.

## What was not migrated

Codex skill files such as `SKILL.md`, `VERSION`, `scripts/steam_bkv_tool.py`, skill installation docs, packaging assets, and skill release workflows are intentionally not part of this repository.
