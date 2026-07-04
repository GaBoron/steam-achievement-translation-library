# Contributing

Thank you for contributing to the Steam Achievement Translation Library. Chinese documentation and Chinese issue templates are the default entry point; this English guide is auxiliary.

## Submission flow

1. Search `README.md` and `index.json` for the Steam app ID to avoid duplicates.
2. Name the schema file `UserGameStatsSchema_<app_id>.bin`.
3. Zip exactly one schema file as `UserGameStatsSchema_<app_id>.zip`.
4. Open the Chinese translation contribution issue template and upload the ZIP.
5. The automation writes accepted files to `files/<app_id>/`, updates `index.json`, `README.md`, and `README_EN.md`, then prepares a review PR.

Do not submit Codex skill runtime files such as `SKILL.md`, `VERSION`, `scripts/steam_bkv_tool.py`, skill installer docs, packaging assets, or release workflows.
