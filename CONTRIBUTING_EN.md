# Contributing

Thank you for contributing to the Steam Achievement Translation Library. Follow this guide so automation can validate the file and prepare a review PR.

## Before Opening An Issue

| Check | Requirement |
| --- | --- |
| Steam app ID | Search [INDEX_EN.md](INDEX_EN.md) or `index.json` to choose either a new submission or an update |
| File name | Use `UserGameStatsSchema_<app_id>.bin` |
| ZIP | Upload `UserGameStatsSchema_<app_id>.zip` containing exactly one matching `.bin` file |
| Languages | Select or enter only languages that have complete achievement names and descriptions |
| Game name | Use the Steam store name; if it is not Chinese, you may append a Chinese translation after a space |

## New Submissions

Use the "Submit Steam achievement translation" template when the Steam app ID is not in the accepted index. Automation checks the app ID, store URL, ZIP structure, schema parsing, unique achievement IDs, and language coverage before creating a PR.

## Updates

Use the "Update existing Steam achievement translation" template when the app ID already exists in `index.json`. Open PRs do not count as accepted entries. The uploaded file must differ from the current library file; otherwise automation rejects the issue. Accepted update PRs include added, deleted, and changed achievement IDs in the PR body.

## Outdated Reports

Use the "Report outdated achievement file" template when an accepted file may be stale but you do not have a replacement file yet. Include evidence such as game update dates, achievement count changes, local schema timestamps, missing achievements, or update notes.

## Rights

Only submit translations you are allowed to share. Original game content, achievement text, Steam schema content, and related files remain the property of their respective rights holders. Contributor-owned translation portions are handled under [LICENSE.md](LICENSE.md).
