# Contributing

Thank you for contributing to the Steam Achievement Translation Library. Follow this guide so automation can validate the file and prepare a review PR.

## Before Opening An Issue

| Check | Requirement |
| --- | --- |
| Steam app ID | Search [INDEX_EN.md](INDEX_EN.md) or `index.json` to choose either a new submission or an update |
| File name | Use `UserGameStatsSchema_<app_id>.bin` |
| ZIP | Upload `UserGameStatsSchema_<app_id>.zip` containing exactly one matching `.bin` file |
| Languages | List every language code that has complete achievement names and descriptions; separate multiple codes with half-width commas |
| Game name | Use the Steam store name; if it is not Chinese, you may append a Chinese translation after a space |

## New Submissions

Use the "Submit Steam achievement translation" template when the Steam app ID is not in the accepted index. Automation checks the app ID, store URL, ZIP structure, schema parsing, unique achievement IDs, and language coverage before creating a PR.

## Updates

Use the "Update existing Steam achievement translation" template when the app ID already exists in `index.json`. Open PRs do not count as accepted entries. The uploaded file must differ from the current library file; otherwise automation rejects the issue. Accepted update PRs include added, deleted, and changed achievement IDs in the PR body.

## PR `/update` Commands

If validation fails while the issue is still open, you may edit field values in the issue body or comment `/update <type> <value>`; do not rename the `###` field headings. After automation creates a PR, the source issue is closed and locked. To change an open PR, comment one of these commands on the PR:

> [!IMPORTANT]
> `/update` must include a type. A bare `/update` comment does not update the file; automation replies with the exact error. Except for `doc`, every type also needs a value on the same line.

| Command | Effect |
| --- | --- |
| `/update doc` plus attachment | Replace the PR's `UserGameStatsSchema_<app_id>.bin`; attach `UserGameStatsSchema_<app_id>.zip` to the same comment |
| `/update id <Steam app ID>` | Change the Steam app ID and rename file paths for normal submission or update PRs |
| `/update name <game name>` | Change the game name |
| `/update store <Steam store URL>` | Change the store URL; the URL app ID must match the current app ID |
| `/update languages <codes>` | Replace the full language list; list every language that exists in the file and separate codes with half-width commas |
| `/update summary <summary>` | Change the update summary on an update PR |
| `/update reason <reason>` | Change the reason on an outdated-report PR |
| `/update reference <source>` | Change the reference on an outdated-report PR |

For file replacement, put the command and attachment in the same PR comment:

```markdown
/update doc
[UserGameStatsSchema_123456.zip](https://github.com/user-attachments/files/.../UserGameStatsSchema_123456.zip)
```

If the type is unsupported, a required value is missing, or `/update doc` has no ZIP attachment, automation comments with the specific error and leaves the PR unchanged.

Language updates are not incremental. `/update languages schinese, english` means the file contains only `schinese` and `english`; omitted languages are treated as absent.

When a maintainer requests changes, automation adds the `等待更新` label. A later PR comment removes that label automatically; `/update` comments also refresh the PR branch and body. Merged PR conversations are locked.

## Outdated Reports

Use the "Report outdated achievement file" template when an accepted file may be stale but you do not have a replacement file yet. Include evidence such as game update dates, achievement count changes, local schema timestamps, missing achievements, or update notes.

## Rights

Only submit translations you are allowed to share. Original game content, achievement text, Steam schema content, and related files remain the property of their respective rights holders. Contributor-owned translation portions are handled under [LICENSE.md](LICENSE.md).
